"""Force worker and coordinator failure using only isolated example-bot games.

Uses the native systemd/Bubblewrap sandbox. Provide a new private directory;
set HALITE_ENGINE to the engine to verify. No production data is read.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB))
from benchmark_runner import fixture
from backend import settings as S
from backend.db import connect


def wait_for(predicate, timeout=100):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise TimeoutError('recovery check timed out')


def engines():
    found = {}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = (proc / 'cmdline').read_bytes().split(b'\0')
            if argv[0] != str(S.ENGINE).encode():
                continue
            work = Path(argv[argv.index(b'-i') + 1].decode())
            if work.parent == S.DATA / 'work':
                parent = int((proc / 'stat').read_text().split(') ')[1].split()[1])
                found[work.name] = (int(proc.name), parent)
        except (OSError, ValueError, IndexError):
            pass
    return found


def rows():
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT id,status,attempts,result_json FROM matches ORDER BY rowid')]


def main():
    parser = argparse.ArgumentParser(description='Exercise worker SIGKILL and coordinator SIGKILL in a fresh isolated arena.')
    parser.add_argument('directory', type=Path)
    directory = parser.parse_args().directory.resolve()
    directory.mkdir(mode=0o700)
    fixture(directory)
    with connect() as db:
        db.execute("DELETE FROM matches WHERE id NOT IN ('0','1')")
    env = dict(os.environ, HALITE_DATA_DIR=str(directory), HALITE_RUNNER_WORKERS='2', HALITE_RUNNER_SEATS='8', HALITE_MIN_DISK_FREE='0')
    log = (directory / 'coordinator.log').open('a')
    def start():
        return subprocess.Popen([sys.executable, '-m', 'backend.runner'], cwd=WEB, env=env, stdout=log, stderr=log, start_new_session=True)
    process = start()
    evidence = {}
    try:
        first = wait_for(lambda: engines() if len(engines()) == 2 else None)
        os.kill(first['0-1'][1], signal.SIGKILL)
        wait_for(lambda: rows()[0]['attempts'] == 2 and rows()[1]['attempts'] == 1 and '0-2' in engines())
        evidence['worker_crash'] = [{'id': row['id'], 'status': row['status'], 'attempts': row['attempts']} for row in rows()]
        assert not Path(f'/proc/{first["0-1"][0]}').exists(), 'dead worker left its engine alive'
        process.kill()
        process.wait(10)
        wait_for(lambda: not engines(), 15)
        evidence['coordinator_crash_engines_cleaned'] = True
        process = start()
        wait_for(lambda: all(row['status'] == 'complete' for row in rows()))
        final = rows()
        assert [row['attempts'] for row in final] == [3, 2], final
        assert all(not any(json.loads(row['result_json'])['terminated'].values()) for row in final)
        evidence['final'] = [{'id': row['id'], 'status': row['status'], 'attempts': row['attempts']} for row in final]
        with connect() as db:
            evidence['attempts'] = [dict(row) for row in db.execute('SELECT match_id,number,status FROM attempts ORDER BY match_id,number')]
        process.terminate()
        process.wait(30)
        assert not engines()
        namespace = S.scope_prefix('bot')
        scopes = subprocess.check_output(['systemctl', '--user', 'list-units', '--plain', '--no-legend', f'{namespace}-*.scope'], text=True)
        assert not scopes.strip(), scopes
        evidence['no_remaining_engines_or_bot_scopes'] = True
        (directory / 'recovery-evidence.json').write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence, indent=2))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(30)
        log.close()


if __name__ == '__main__':
    main()
