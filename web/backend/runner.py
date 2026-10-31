"""One local coordinator; each bot runs as a restricted native process."""

import fcntl
import ctypes
from functools import partial
import gzip
import hashlib
import json
import logging
import multiprocessing
import os
from pathlib import Path
import resource
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from . import settings as S
from .db import connect, initialize, now
from .storage import disk_check
from .eligibility import CPP_ONLY
from .scheduler import match_eligible
from . import analytics, contests
from .builds import prepare, BotBuildError

log = logging.getLogger("halite3.runner")
STOP = False


def heartbeat():
    with connect() as db:
        db.execute(
            "INSERT INTO runners VALUES('local',?,'process-v2') ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,version=excluded.version",
            (now(),),
        )


def claim(workers=1, seats=8, reserved_seats=0):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        expired = db.execute(
            "SELECT id,attempts,max_attempts FROM matches WHERE status='running' AND lease_until<?",
            (now(),),
        ).fetchall()
        for item in expired:
            db.execute(
                "UPDATE matches SET status=?,lease_token=NULL,lease_until=NULL,error='执行器中断，等待重试' WHERE id=?",
                (
                    "queued" if item["attempts"] < item["max_attempts"] else "failed",
                    item["id"],
                ),
            )
            db.execute(
                "UPDATE attempts SET status='interrupted',error='执行器中断',finished_at=? WHERE match_id=? AND number=? AND status='running'",
                (now(), item["id"], item["attempts"]),
            )
        running = db.execute(
            "SELECT COUNT(*),COALESCE(SUM(mode),0) FROM matches WHERE status='running'"
        ).fetchone()
        if running[0] >= workers:
            return None
        # Select the head of the fair queue before applying the seat limit. A large
        # match must not starve behind a continuous stream of smaller matches.
        row = db.execute(
            "SELECT m.*,j.config_json FROM matches m JOIN jobs j ON j.id=m.job_id LEFT JOIN users u ON u.id=m.owner_id WHERE m.status='queued' AND m.attempts<m.max_attempts ORDER BY COALESCE(u.last_served,0),m.created_at,m.rowid LIMIT 1"
        ).fetchone()
        if not row:
            return None
        if max(running[1], reserved_seats) + row["mode"] > seats:
            return None
        item = dict(row)
        token = uuid.uuid4().hex
        attempt = item["attempts"] + 1
        db.execute(
            "UPDATE matches SET status='running',attempts=?,lease_token=?,lease_until=?,started_at=? WHERE id=?",
            (attempt, token, now() + S.LEASE_SECONDS, now(), item["id"]),
        )
        db.execute(
            "INSERT INTO attempts(match_id,number,status,created_at) VALUES(?,?,?,?)",
            (item["id"], attempt, "running", now()),
        )
        if item["owner_id"]:
            db.execute(
                "UPDATE users SET last_served=? WHERE id=?",
                (time.time_ns(), item["owner_id"]),
            )
        item.update(attempts=attempt, lease_token=token)
        return item


def units_for(match):
    return [
        f"{S.scope_prefix('bot')}-{match['id']}-{match['attempts']}-{i}"
        for i in range(match["mode"])
    ]


def stop_units(names):
    if names:
        subprocess.run(
            ["systemctl", "--user", "stop", *[name + ".scope" for name in names]],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=25,
        )


def parent_death(parent, sig):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, sig, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_PDEATHSIG) failed")
    if os.getppid() != parent:
        os.kill(os.getpid(), sig)


def engine_limits(parent):
    parent_death(parent, signal.SIGKILL)
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2, 64 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_match(match):
    workspace = S.DATA / "work" / f"{match['id']}-{match['attempts']}"
    workspace.mkdir(parents=True, mode=0o700)
    participants = json.loads(match["seat_json"])
    configuration = json.loads(match["config_json"])
    # Jobs created before per-mode setups keep their single map and time limit.
    configuration = {
        "seconds": S.MAX_GAME_SECONDS,
        **configuration,
        **configuration.get("setups", {}).get(str(match["mode"]), {}),
        **configuration.get("setups_by_seed", {}).get(f"{match['mode']}:{match['seed']}", {}),
    }
    names = units_for(match)
    process = None
    temporary = None
    logs = {
        "match_id": match["id"],
        "attempt": match["attempts"],
        "players": [],
        "stdout": "",
        "stderr": "",
    }
    try:
        with connect() as db:
            if not match_eligible(db, match["seat_json"]):
                raise BotBuildError(CPP_ONLY)
        commands = []
        for i, seat in enumerate(participants):
            directory, artifact = prepare(seat, cancelled=lambda: STOP)
            launch = workspace / f"player-{i}.json"
            argv = (
                ["/bot/bot"]
                if artifact["language"] == "cpp"
                else ["/usr/bin/python3", "-B", "-u", "/bot/bot.py"]
            )
            launch.write_text(
                json.dumps(
                    {
                        "unit": names[i],
                        "source_dir": str(directory),
                        "argv": argv,
                        "runtime": configuration["seconds"] + 5,
                    }
                )
            )
            commands.append(
                shlex.join(
                    [sys.executable, str(S.ROOT / "runner/sandbox.py"), str(launch)]
                )
            )
        rules = workspace / "rules.json"
        rules.write_text(json.dumps(configuration["rules"]))
        argv = [
            str(S.ENGINE),
            "--results-as-json",
            "--no-compression",
            "--width",
            str(configuration["width"]),
            "--height",
            str(configuration["height"]),
            "--turn-limit",
            str(configuration["turns"]),
            "--seed",
            str(configuration.get("map_seed", match["seed"])),
            "-c",
            str(rules),
            "-i",
            str(workspace),
            *commands,
        ]
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            preexec_fn=partial(engine_limits, os.getpid()),
        )
        deadline = time.monotonic() + configuration["seconds"]
        last_heartbeat = 0
        while True:
            if STOP or time.monotonic() > deadline:
                raise RuntimeError(
                    "执行器停止，比赛等待重试。"
                    if STOP
                    else f"整场比赛超过 {configuration['seconds']} 秒。"
                )
            try:
                stdout, stderr = process.communicate(timeout=1)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() - last_heartbeat >= 4:
                    last_heartbeat = time.monotonic()
                    with connect() as db:
                        db.execute(
                            "UPDATE matches SET lease_until=? WHERE id=? AND lease_token=? AND status='running'",
                            (
                                now() + S.LEASE_SECONDS,
                                match["id"],
                                match["lease_token"],
                            ),
                        )
        logs["stdout"] = stdout[-32768:]
        logs["stderr"] = stderr[-32768:]
        if process.returncode:
            raise RuntimeError(f"引擎退出码 {process.returncode}。")
        raw = json.loads(stdout)
        for i in range(match["mode"]):
            text = ""
            name = raw.get("error_logs", {}).get(str(i))
            if name:
                path = Path(name)
                if path.is_relative_to(workspace) and path.is_file():
                    text = path.read_text(errors="replace")[-32768:]
            logs["players"].append(
                {
                    "name": participants[i]["name"],
                    "version": participants[i]["version"],
                    "stderr": text,
                }
            )
            if any(
                marker in text
                for marker in [
                    "Failed to connect to bus",
                    "Failed to start transient scope",
                    "bwrap:",
                ]
            ):
                raise RuntimeError("Bot 进程隔离或资源限制启动失败。")
        if len(raw.get("stats", {})) != match["mode"] or any(
            s.get("rank", 0) < 1 for s in raw["stats"].values()
        ):
            raise RuntimeError("引擎返回了不完整的结果。")
        replay_path = Path(raw["replay"])
        if (
            not replay_path.is_relative_to(workspace)
            or replay_path.stat().st_size > 64 * 1024**2
        ):
            raise RuntimeError("回放路径或大小无效。")
        replay = json.loads(replay_path.read_text())
        for i, player in enumerate(replay["players"]):
            player["name"] = f"{participants[i]['name']} v{participants[i]['version']}"
        result = {
            "stats": raw["stats"],
            "terminated": raw.get("terminated", {}),
            "engine_sha256": hashlib.sha256(S.ENGINE.read_bytes()).hexdigest(),
            "rules": configuration["rules"],
            "protocol": "halite3-lab-v1",
            "turns": len(replay["full_frames"]) - 2,
        }
        key = f"replays/{match['id']}.json.gz"
        temporary = S.DATA / f"{key}.{match['lease_token']}.tmp"
        with gzip.open(temporary, "wt", compresslevel=5, encoding="utf-8") as stream:
            json.dump(replay, stream, separators=(",", ":"))
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not owns(db, match):
                temporary.unlink(missing_ok=True)
                return False
            temporary.replace(S.DATA / key)
            (S.DATA / "logs" / f"{match['id']}.json").write_text(
                json.dumps(logs, ensure_ascii=False)
            )
            db.execute(
                "UPDATE matches SET status='complete',result_json=?,replay_key=?,finished_at=?,lease_until=NULL,lease_token=NULL,error=NULL WHERE id=? AND lease_token=?",
                (json.dumps(result), key, now(), match["id"], match["lease_token"]),
            )
            try:
                analytics.record(db, match["id"], replay)
            except Exception:
                log.exception("analytics_failed id=%s", match["id"])
            db.execute(
                "UPDATE attempts SET status='complete',finished_at=?,log_key=? WHERE match_id=? AND number=?",
                (now(), f"logs/{match['id']}.json", match["id"], match["attempts"]),
            )
        log.info("match_complete id=%s attempt=%s", match["id"], match["attempts"])
        return True
    except Exception as exc:
        error = str(exc)[:500]
        logs["error"] = error
        logkey = f"logs/{match['id']}-attempt-{match['attempts']}.json"
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not owns(db, match):
                return False
            (S.DATA / logkey).write_text(json.dumps(logs, ensure_ascii=False))
            (S.DATA / "logs" / f"{match['id']}.json").write_text(
                json.dumps(logs, ensure_ascii=False)
            )
            retry = match["attempts"] < match["max_attempts"] and not isinstance(
                exc, BotBuildError
            )
            db.execute(
                "UPDATE matches SET status=?,error=?,lease_token=NULL,lease_until=NULL,finished_at=? WHERE id=? AND lease_token=?",
                (
                    "queued" if retry else "failed",
                    error,
                    now(),
                    match["id"],
                    match["lease_token"],
                ),
            )
            db.execute(
                "UPDATE attempts SET status=?,error=?,log_key=?,finished_at=? WHERE match_id=? AND number=?",
                (
                    "interrupted" if STOP else "failed",
                    error,
                    logkey,
                    now(),
                    match["id"],
                    match["attempts"],
                ),
            )
        log.warning(
            "match_failed id=%s attempt=%s error=%s",
            match["id"],
            match["attempts"],
            error,
        )
        return False
    finally:
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
        stop_units(names)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        # Source directories were read-only for the unprivileged container uid.
        for path in workspace.rglob("*"):
            if path.is_dir():
                path.chmod(0o700)
        shutil.rmtree(workspace, ignore_errors=True)


def owns(db, match):
    return db.execute(
        "SELECT 1 FROM matches WHERE id=? AND lease_token=? AND status='running'",
        (match["id"], match["lease_token"]),
    ).fetchone() is not None


def recover(match):
    """Only call after the worker exited and its sandboxes have been stopped."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if not owns(db, match):
            return
        db.execute(
            "UPDATE matches SET status=?,lease_token=NULL,lease_until=NULL,error='执行器中断，等待重试' WHERE id=?",
            ("queued" if match["attempts"] < match["max_attempts"] else "failed", match["id"]),
        )
        db.execute(
            "UPDATE attempts SET status='interrupted',error='执行器中断',finished_at=? WHERE match_id=? AND number=? AND status='running'",
            (now(), match["id"], match["attempts"]),
        )


def request_stop(*_):
    global STOP
    STOP = True


def worker(match, parent):
    global STOP
    STOP = False
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    parent_death(parent, signal.SIGTERM)
    run_match(match)


def maintain(workers, renew=True):
    # The coordinator renews leases even while children wait for a cold build.
    # Reap before claiming replacements so crashed children cannot publish late.
    for pid, (process, match) in list(workers.items()):
        if process.is_alive() and renew:
            with connect() as db:
                db.execute(
                    "UPDATE matches SET lease_until=? WHERE id=? AND lease_token=? AND status='running'",
                    (now() + S.LEASE_SECONDS, match["id"], match["lease_token"]),
                )
        elif not process.is_alive():
            process.join()
            stop_units(units_for(match))
            recover(match)
            del workers[pid]
            process.close()


def shutdown(workers):
    for process, _ in workers.values():
        if process.is_alive():
            process.terminate()
    deadline = time.monotonic() + 15
    for process, match in workers.values():
        process.join(timeout=max(0, deadline - time.monotonic()))
        if process.is_alive():
            process.kill()
            process.join()
        stop_units(units_for(match))
        recover(match)
        process.close()


def cleanup():
    cutoff = now() - S.RETENTION_DAYS * 86400
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE expires_at<?", (now(),))
        db.execute("DELETE FROM api_tokens WHERE expires_at<?", (now(),))
        db.execute("DELETE FROM rate_limits WHERE reset_at<?", (now(),))
        rows = db.execute(
            # Contest replays stay private until the results are published, then become public; keep them.
            "SELECT id,replay_key FROM matches WHERE finished_at<? AND replay_key IS NOT NULL AND public=0 AND job_id NOT IN (SELECT id FROM jobs WHERE contest_id IS NOT NULL)",
            (cutoff,),
        ).fetchall()
        for row in rows:
            (S.DATA / row["replay_key"]).unlink(missing_ok=True)
            db.execute("UPDATE matches SET replay_key=NULL WHERE id=?", (row["id"],))
    # Public ranked replays are retained; global disk backpressure still applies.


def main():
    global STOP
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    initialize()
    with (S.DATA / "runner.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        subprocess.run(
            [
                "systemctl",
                "--user",
                "stop",
                f"{S.scope_prefix('bot')}-*.scope",
                f"{S.scope_prefix('build')}-*.scope",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        with connect() as db:
            db.execute("UPDATE matches SET lease_until=0 WHERE status='running'")
        context = multiprocessing.get_context("spawn")
        workers = {}
        last_cleanup = last_tick = last_renew = 0
        log.info("runner_started workers=%s seats=%s", S.RUNNER_WORKERS, S.RUNNER_SEATS)
        try:
            while not STOP:
                try:
                    renew = now() - last_renew >= 4
                    if renew:
                        heartbeat()
                        last_renew = now()
                    maintain(workers, renew=renew)
                    if now() - last_cleanup > 3600:
                        cleanup()
                        last_cleanup = now()
                    if now() - last_tick >= 15:
                        contests.tick()
                        last_tick = now()
                    disk_check()
                    while not STOP and len(workers) < S.RUNNER_WORKERS:
                        match = claim(
                            S.RUNNER_WORKERS, S.RUNNER_SEATS,
                            reserved_seats=sum(item[1]["mode"] for item in workers.values()),
                        )
                        if not match:
                            break
                        process = context.Process(target=worker, args=(match, os.getpid()))
                        try:
                            process.start()
                        except Exception:
                            recover(match)
                            raise
                        workers[process.pid] = (process, match)
                    time.sleep(0.1 if workers else 2)
                except Exception:
                    log.exception("runner_error")
                    time.sleep(1)
        finally:
            shutdown(workers)
            with connect() as db:
                db.execute("DELETE FROM runners WHERE id='local'")


if __name__ == "__main__":
    main()
