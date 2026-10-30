"""Compare identical frozen example-bot games in fresh, isolated arenas.

Run with the service Python and HALITE_ENGINE set; no production data is read.
Artifacts stay in a new directory provided as the single positional argument.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import builds, runner, settings as S
from backend.db import connect, initialize
from backend.scheduler import snapshot, version_info


def fixture(directory):
    S.DATA = directory
    initialize()
    payload = (S.ROOT / "examples/cpp/main.cpp").read_bytes()
    key = "blobs/example.cpp"
    (directory / key).write_bytes(payload)
    with connect() as db:
        db.execute("INSERT INTO users(id,username,display_name,password_hash,created_at) VALUES('bench','bench','bench','disabled',0)")
        db.execute("INSERT INTO bots(id,owner_id,name,created_at) VALUES('example','bench','example',0)")
        db.execute("INSERT INTO versions(id,bot_id,version,object_key,sha256,filename,size,language,created_at) VALUES('example','example','1',?,?, 'main.cpp',?,'cpp',0)",
                   (key, hashlib.sha256(payload).hexdigest(), len(payload)))
        players = {id: snapshot(version_info(db, id, 'bench')) for id in ('example', 'builtin-raider-v1')}
        db.execute("INSERT INTO jobs(id,owner_id,name,config_json,created_at) VALUES('bench','bench','bench',?,0)",
                   (json.dumps({'setups': {str(k): v for k, v in S.MODE_SETUPS.items()}}),))
        for index, (mode, seed) in enumerate(( (2,11), (2,29), (4,11), (4,29), (8,11), (8,29) )):
            seats = [players['example']] * (mode - 1) + [players['builtin-raider-v1']]
            db.execute("INSERT INTO matches(id,job_id,owner_id,mode,seed,seat_json,created_at) VALUES(?,'bench','bench',?,?,?,0)",
                       (str(index), mode, seed, json.dumps(seats)))
    for seat in players.values():
        builds.prepare(seat)
    return {id: seat['sha256'] for id, seat in players.items()}


def run(directory, workers):
    fingerprints = fixture(directory)
    unit = f"halite3-benchmark-{uuid.uuid4().hex[:12]}"
    env = dict(os.environ, HALITE_DATA_DIR=str(directory), HALITE_RUNNER_WORKERS=str(workers),
               HALITE_RUNNER_SEATS='8', HALITE_MIN_DISK_FREE='0')
    log = (directory / 'coordinator.log').open('w')
    command = ['systemd-run', '--user', '--scope', '--quiet', f'--unit={unit}',
               '-p', 'CPUQuota=160%', '-p', 'MemoryMax=1G', '-p', 'TasksMax=256',
               sys.executable, '-m', 'backend.runner']
    process = subprocess.Popen(command, cwd=S.ROOT, env=env, stdout=log, stderr=log, start_new_session=True)
    started = time.monotonic()
    peak_running = peak_seats = peak_memory = 0
    health = []
    last_sample = 0
    cgroup = Path(f'/sys/fs/cgroup/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/app.slice')
    try:
        while time.monotonic() - started < 900:
            if process.poll() is not None:
                raise RuntimeError(f'coordinator exited {process.returncode}, see {directory / "coordinator.log"}')
            with connect() as db:
                rows = [dict(row) for row in db.execute('SELECT * FROM matches ORDER BY rowid')]
            running = [row for row in rows if row['status'] == 'running']
            peak_running = max(peak_running, len(running))
            peak_seats = max(peak_seats, sum(row['mode'] for row in running))
            if time.monotonic() - last_sample >= 1:
                last_sample = time.monotonic()
                paths = [cgroup / (unit + '.scope') / 'memory.current']
                paths += list(cgroup.glob(f'{S.scope_prefix("bot")}-*.scope/memory.current'))
                memory = 0
                for path in paths:
                    try:
                        memory += int(path.read_text())
                    except FileNotFoundError:
                        pass
                peak_memory = max(peak_memory, memory)
                before = time.monotonic()
                try:
                    with urllib.request.urlopen('http://127.0.0.1:18383/api/health', timeout=3) as response:
                        health.append({'ok': json.load(response)['ok'], 'seconds': time.monotonic() - before})
                except Exception as exc:
                    health.append({'ok': False, 'error': str(exc)})
            if all(row['status'] in ('complete', 'failed') for row in rows):
                break
            time.sleep(0.1)
        else:
            raise TimeoutError('benchmark exceeded 900 seconds')
        elapsed = time.monotonic() - started
        games = []
        for row in rows:
            result = json.loads(row['result_json'] or '{}')
            games.append({'mode': row['mode'], 'seed': row['seed'], 'status': row['status'], 'attempts': row['attempts'],
                          'terminated': result.get('terminated'), 'turns': result.get('turns'),
                          'stats': result.get('stats'), 'engine_sha256': result.get('engine_sha256'), 'error': row['error']})
        return {'workers': workers, 'seconds': elapsed, 'peak_running': peak_running, 'peak_seats': peak_seats,
                'sampled_peak_memory_bytes': peak_memory, 'health': health, 'sources': fingerprints, 'games': games}
    finally:
        os.killpg(process.pid, signal.SIGTERM) if process.poll() is None else None
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            subprocess.run(['systemctl','--user','stop', unit + '.scope'], check=True, timeout=30)
            process.wait(timeout=10)
        log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(mode=0o700)  # Refuse existing paths, including the live arena.
    results = []
    for workers in (1, 2):
        result = run(root / str(workers), workers)
        results.append(result)
        (root / 'results.json').write_text(json.dumps(results, indent=2))
        print(json.dumps({key: result[key] for key in ('workers', 'seconds', 'peak_running', 'peak_seats', 'sampled_peak_memory_bytes')}), flush=True)
    assert all(game['status'] == 'complete' and game['attempts'] == 1 and not any(game['terminated'].values()) for result in results for game in result['games'])
    assert results[0]['sources'] == results[1]['sources']
    assert results[0]['games'] == results[1]['games'], 'parallel execution changed deterministic results'
    assert results[1]['peak_running'] == 2 and results[1]['peak_seats'] <= 8
    assert all(sample['ok'] for result in results for sample in result['health'])
    print(f"Speedup: {results[0]['seconds'] / results[1]['seconds']:.3f}x", flush=True)


if __name__ == '__main__':
    main()
