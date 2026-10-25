#!/usr/bin/env python3
"""Deterministic combination tournaments with transactional match-level resume."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import Counter, defaultdict
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import shlex
import signal
import sqlite3
import subprocess
import sys
import threading
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def load_config(path):
    cfg = json.loads(Path(path).read_text())
    names = [b['name'] for b in cfg['bots']]
    if len(names) != len(set(names)) or not names:
        raise ValueError('Bot names must be unique and nonempty')
    if not cfg['seeds'] or len(set(cfg['seeds'])) != len(cfg['seeds']):
        raise ValueError('Seeds must be unique and nonempty')
    for mode in cfg['modes']:
        if mode not in (2, 4, 8) or mode > len(names):
            raise ValueError('Modes must be 2, 4, or 8 and have enough registered bots')
    if len(set(cfg['modes'])) != len(cfg['modes']):
        raise ValueError('Modes must be unique')
    if cfg['width'] % 4 or cfg['height'] % 2:
        raise ValueError('Use width divisible by 4 and height divisible by 2 for 2/4/8-player maps')
    if cfg['turns'] <= 0 or cfg.get('timeout', 120) <= 0:
        raise ValueError('Turns and timeout must be positive')
    for bot in cfg['bots']:
        if not isinstance(bot['command'], list) or not all(isinstance(v, str) for v in bot['command']):
            raise ValueError('Bot commands must be nonempty argv lists')
        if not bot['command'] or not bot.get('sources'):
            raise ValueError('Each bot needs command and sources for provenance')
    return cfg


def schedule(cfg):
    names = [b['name'] for b in cfg['bots']]
    for mode in cfg['modes']:
        for combo in itertools.combinations(names, mode):
            for seed in cfg['seeds']:
                for rotation in range(mode if cfg.get('rotate_seats', False) else 1):
                    seats = combo[rotation:] + combo[:rotation]
                    spec = {'mode': mode, 'seed': seed, 'rotation': rotation, 'seats': seats}
                    yield hashlib.sha256(canonical(spec).encode()).hexdigest()[:20], spec


def provenance(cfg):
    paths = {cfg.get('engine', 'build/halite'), cfg['rules'], 'lab/arena.py', 'lab/launch.py'}
    for bot in cfg['bots']:
        paths.update(bot['sources'])
    return {path: digest(ROOT/path) for path in sorted(paths)}


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS matches(
            id TEXT PRIMARY KEY, spec TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, result TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS attempts(
            match_id TEXT, number INTEGER, status TEXT, directory TEXT, error TEXT,
            PRIMARY KEY(match_id, number));
    ''')
    return db


def prepare(db, cfg):
    manifest = canonical({'config': cfg, 'sha256': provenance(cfg)})
    old = db.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()
    if old and old['value'] != manifest:
        raise ValueError('Config, engine, or bot sources changed. Create a new run directory to avoid mixing results.')
    if not old:
        with db:
            db.execute("INSERT INTO metadata VALUES('manifest', ?)", (manifest,))
            db.executemany('INSERT INTO matches(id,spec) VALUES(?,?)', ((mid, canonical(spec)) for mid, spec in schedule(cfg)))
    with db:
        db.execute("UPDATE attempts SET status='interrupted',error='Coordinator stopped before recording completion' WHERE status='running'")
        db.execute("UPDATE matches SET status='pending',error='Recovered unfinished attempt' WHERE status='running'")
    return json.loads(manifest)


def stop_process(proc):
    # The engine creates separate process groups for bot shells. Track descendants
    # before terminating the parent so a timed-out match does not leave bots running.
    children = []
    pending = [proc.pid]
    while pending:
        pid = pending.pop()
        try:
            ids = [int(s) for s in Path(f'/proc/{pid}/task/{pid}/children').read_text().split()]
        except (FileNotFoundError, ProcessLookupError):
            ids = []
        children.extend(ids)
        pending.extend(ids)
    for pid in reversed(children):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def play(cfg, spec, directory, stopped):
    directory.mkdir(parents=True)
    bots = {b['name']: b for b in cfg['bots']}
    cmd = [str(ROOT/cfg.get('engine', 'build/halite')), '--results-as-json', '--no-compression',
           '--width', str(cfg['width']), '--height', str(cfg['height']), '--seed', str(spec['seed']),
           '--turn-limit', str(cfg['turns']), '--constants-file', str(ROOT/cfg['rules']),
           '--replay-directory', str(directory)]
    cmd += [shlex.join(bots[name]['command']) for name in spec['seats']]
    (directory/'match.json').write_text(json.dumps({'spec': spec, 'argv': cmd}, indent=2))
    guarded_cmd = [sys.executable, str(ROOT/'lab/launch.py'), str(os.getpid()), *cmd]
    proc = subprocess.Popen(guarded_cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    deadline = time.monotonic() + cfg.get('timeout', 120)
    error = None
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=min(0.25, max(0.0001, deadline-time.monotonic())))
            break
        except subprocess.TimeoutExpired:
            if stopped.is_set() or time.monotonic() > deadline:
                error = 'interrupted' if stopped.is_set() else 'match timeout'
                stop_process(proc)
                stdout, stderr = proc.communicate()
                break
    (directory/'stdout.json').write_text(stdout)
    (directory/'stderr.log').write_text(stderr)
    if error:
        raise RuntimeError(error)
    if proc.returncode:
        raise RuntimeError(f'Engine exited {proc.returncode}: {stderr[-1500:]}')
    result = json.loads(stdout)
    if any(result.get('terminated', {}).values()):
        raise RuntimeError('Bot terminated; inspect per-player error logs')
    if len(result.get('stats', {})) != spec['mode']:
        raise RuntimeError('Incomplete player results')
    replay_path = Path(result['replay'])
    replay = json.loads(replay_path.read_text())
    if not replay.get('full_frames') or len(replay.get('players', [])) != spec['mode']:
        raise RuntimeError('Replay missing frames or players')
    result['replay_sha256'] = digest(replay_path)
    return result


def report(db, directory):
    counts = dict(Counter(row['status'] for row in db.execute('SELECT status FROM matches')))
    totals = defaultdict(lambda: {'games': 0, 'wins': 0, 'score': 0, 'rank': 0})
    for row in db.execute("SELECT spec,result FROM matches WHERE status='complete'"):
        spec, result = json.loads(row['spec']), json.loads(row['result'])
        for seat, name in enumerate(spec['seats']):
            stats = result['stats'][str(seat)]
            total = totals[(spec['mode'], name)]
            total['games'] += 1
            total['score'] += stats['score']
            total['rank'] += stats['rank']
            total['wins'] += stats['rank'] == 1
    standings = []
    for (mode, bot), total in sorted(totals.items()):
        n = total['games']
        standings.append({'mode': mode, 'bot': bot, 'games': n, 'win_rate': total['wins']/n,
                          'mean_score': total['score']/n, 'mean_rank': total['rank']/n})
    output = {'matches': counts, 'standings': standings}
    with tempfile.NamedTemporaryFile(mode='w', dir=directory, prefix='.summary-', suffix='.tmp', delete=False) as stream:
        json.dump(output, stream, indent=2)
        tmp = Path(stream.name)
    tmp.replace(directory/'summary.json')
    return output


def run(cfg, directory, jobs=2, max_attempts=2, limit=None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'coordinator.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another coordinator already owns this run directory')
        db = connect(directory/'arena.sqlite3')
        manifest = prepare(db, cfg)
        (directory/'manifest.json').write_text(json.dumps(manifest, indent=2))
        # Retain the exact binaries and declared sources, not just their digests.
        artifacts = directory/'artifacts'
        artifacts.mkdir(exist_ok=True)
        for path, expected in manifest['sha256'].items():
            target = artifacts/expected
            if not target.exists():
                payload = (ROOT/path).read_bytes()
                if hashlib.sha256(payload).hexdigest() != expected:
                    raise ValueError(f'Source changed while starting run: {path}')
                target.write_bytes(payload)
        stopped = threading.Event()
        previous = {}
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                previous[sig] = signal.signal(sig, lambda *_: stopped.set())
        submitted = 0
        try:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                active = {}
                while True:
                    while not stopped.is_set() and len(active) < jobs and (limit is None or submitted < limit):
                        row = db.execute("SELECT * FROM matches WHERE status IN ('pending','failed') AND attempts < ? ORDER BY attempts,id LIMIT 1", (max_attempts,)).fetchone()
                        if row is None:
                            break
                        attempt = row['attempts'] + 1
                        dest = directory/'matches'/row['id']/f'attempt-{attempt}'
                        with db:
                            db.execute("UPDATE matches SET status='running',attempts=? WHERE id=?", (attempt, row['id']))
                            db.execute('INSERT INTO attempts VALUES(?,?,?,?,NULL)', (row['id'], attempt, 'running', str(dest)))
                        future = pool.submit(play, cfg, json.loads(row['spec']), dest, stopped)
                        active[future] = (row['id'], attempt)
                        submitted += 1
                    if not active:
                        break
                    done, _ = wait(active, timeout=0.3, return_when=FIRST_COMPLETED)
                    for future in done:
                        mid, attempt = active.pop(future)
                        try:
                            result = canonical(future.result())
                            status, error = 'complete', None
                        except Exception as exc:
                            result, status, error = None, 'failed', str(exc)
                        with db:
                            db.execute('UPDATE matches SET status=?,result=?,error=? WHERE id=?', (status, result, error, mid))
                            db.execute('UPDATE attempts SET status=?,error=? WHERE match_id=? AND number=?', (status, error, mid, attempt))
                        print(f'{mid} attempt={attempt} {status}' + (f': {error}' if error else ''), flush=True)
                        report(db, directory)
            return report(db, directory)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    plan = sub.add_parser('plan')
    plan.add_argument('config')
    launch = sub.add_parser('run')
    launch.add_argument('config')
    launch.add_argument('--out', required=True)
    launch.add_argument('--jobs', type=int, default=2)
    launch.add_argument('--max-attempts', type=int, default=2)
    launch.add_argument('--limit', type=int)
    status = sub.add_parser('status')
    status.add_argument('directory')
    args = parser.parse_args()
    if args.action == 'status':
        directory = Path(args.directory)
        db = connect(directory/'arena.sqlite3')
        print(json.dumps(report(db, directory), indent=2))
        return
    cfg = load_config(args.config)
    if args.action == 'plan':
        counts = Counter(spec['mode'] for _, spec in schedule(cfg))
        print(json.dumps({'by_mode': dict(counts), 'total': sum(counts.values())}, indent=2))
    else:
        if args.jobs < 1 or args.max_attempts < 1 or (args.limit is not None and args.limit < 1):
            parser.error('jobs, max-attempts, and limit must be positive')
        summary = run(cfg, args.out, args.jobs, args.max_attempts, args.limit)
        print(json.dumps(summary, indent=2))
        if summary['matches'].get('failed') or summary['matches'].get('pending'):
            raise SystemExit(1)


if __name__ == '__main__':
    main()
