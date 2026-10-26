"""One local coordinator; each bot runs as a restricted native process."""

import fcntl
import gzip
import hashlib
import json
import logging
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
from . import analytics
from .builds import prepare, BotBuildError

log = logging.getLogger("halite3.runner")
STOP = False


def heartbeat():
    with connect() as db:
        db.execute(
            "INSERT INTO runners VALUES('local',?,'process-v1') ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,version=excluded.version",
            (now(),),
        )


def claim():
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
        if db.execute("SELECT 1 FROM matches WHERE status='running'").fetchone():
            return None
        row = db.execute(
            "SELECT m.*,j.config_json FROM matches m JOIN jobs j ON j.id=m.job_id LEFT JOIN users u ON u.id=m.owner_id WHERE m.status='queued' AND m.attempts<m.max_attempts ORDER BY COALESCE(u.last_served,0),m.created_at,m.rowid LIMIT 1"
        ).fetchone()
        if not row:
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
        f"halite3-bot-{match['id'][:8]}-{match['attempts']}-{i}"
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


def engine_limits():
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
    }
    names = units_for(match)
    process = None
    logs = {
        "match_id": match["id"],
        "attempt": match["attempts"],
        "players": [],
        "stdout": "",
        "stderr": "",
    }
    try:
        commands = []
        for i, seat in enumerate(participants):
            directory, artifact = prepare(seat)
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
            str(match["seed"]),
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
            preexec_fn=engine_limits,
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
                    heartbeat()
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
        temporary = S.DATA / f"{key}.tmp"
        with gzip.open(temporary, "wt", compresslevel=5, encoding="utf-8") as stream:
            json.dump(replay, stream, separators=(",", ":"))
        temporary.replace(S.DATA / key)
        (S.DATA / "logs" / f"{match['id']}.json").write_text(
            json.dumps(logs, ensure_ascii=False)
        )
        with connect() as db:
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
        (S.DATA / logkey).write_text(json.dumps(logs, ensure_ascii=False))
        (S.DATA / "logs" / f"{match['id']}.json").write_text(
            json.dumps(logs, ensure_ascii=False)
        )
        with connect() as db:
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
        # Source directories were read-only for the unprivileged container uid.
        for path in workspace.rglob("*"):
            if path.is_dir():
                path.chmod(0o700)
        shutil.rmtree(workspace, ignore_errors=True)


def cleanup():
    cutoff = now() - S.RETENTION_DAYS * 86400
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE expires_at<?", (now(),))
        db.execute("DELETE FROM api_tokens WHERE expires_at<?", (now(),))
        db.execute("DELETE FROM rate_limits WHERE reset_at<?", (now(),))
        rows = db.execute(
            "SELECT id,replay_key FROM matches WHERE finished_at<? AND replay_key IS NOT NULL AND public=0",
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

        def stop(*_):
            global STOP
            STOP = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        subprocess.run(
            [
                "systemctl",
                "--user",
                "stop",
                "halite3-bot-*.scope",
                "halite3-build-*.scope",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        last_cleanup = 0
        while not STOP:
            try:
                heartbeat()
                if now() - last_cleanup > 3600:
                    cleanup()
                    last_cleanup = now()
                disk_check()
                match = claim()
                if match:
                    run_match(match)
                else:
                    time.sleep(2)
            except Exception:
                log.exception("runner_error")
                time.sleep(5)
        with connect() as db:
            db.execute("DELETE FROM runners WHERE id='local'")


if __name__ == "__main__":
    main()
