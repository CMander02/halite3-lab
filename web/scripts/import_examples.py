"""Import three real, already verified engine replays as explicitly labelled examples."""

from pathlib import Path
import gzip
import json
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.db import initialize, connect
from backend import settings as S


def main():
    initialize()
    for name, mode in [("duel", 2), ("ffa4", 4), ("ffa8", 8)]:
        source = S.PROJECT / "lab/runs" / f"{name}-release"
        if not (source / "arena.sqlite3").exists():
            continue
        rawdb = sqlite3.connect(source / "arena.sqlite3")
        row = rawdb.execute(
            "SELECT spec,result FROM matches WHERE status='complete' ORDER BY id LIMIT 1"
        ).fetchone()
        spec, result = map(json.loads, row)
        manifest = json.loads((source / "manifest.json").read_text())
        replayfile = Path(result["replay"])
        replay = json.loads(replayfile.read_text())
        created = int(replayfile.stat().st_mtime)
        mid = f"example-{name}"
        jid = f"examples-{name}"
        with connect() as db:
            if db.execute("SELECT 1 FROM matches WHERE id=?", (mid,)).fetchone():
                continue
            seats = []
            for i, namebot in enumerate(spec["seats"]):
                baseline = namebot.startswith("baseline")
                base = "baseline" if baseline else "raider"
                version = "1.0" if baseline else "1.1"
                if mode != 2:
                    version = "preset-" + namebot.rsplit("v", 1)[-1]
                code = f"lab/bots/{base}.py"
                seats.append(
                    {
                        "id": f"builtin-{base}-v1"
                        if mode == 2
                        else "example-" + namebot,
                        "bot_id": f"builtin-{base}",
                        "name": namebot,
                        "version": version,
                        "sha256": manifest["sha256"][code],
                        "filename": base + ".py",
                        "object_key": None,
                        "owner_id": None,
                        "builtin": 1,
                        "author": "平台基准",
                        "language": "python",
                    }
                )
                replay["players"][i]["name"] = f"{namebot} v{version}"
            key = f"replays/{mid}.json.gz"
            with gzip.open(
                S.DATA / key, "wt", compresslevel=5, encoding="utf-8"
            ) as stream:
                json.dump(replay, stream, separators=(",", ":"))
            config = dict(manifest["config"])
            config["rules"] = S.RULES
            db.execute(
                "INSERT INTO jobs(id,owner_id,name,kind,config_json,created_at) VALUES(?,NULL,?,?,?,?)",
                (jid, f"{mode} 人公开示例", "demo", json.dumps(config), created),
            )
            normalized = {
                "stats": result["stats"],
                "terminated": result.get("terminated", {}),
                "turns": len(replay["full_frames"]) - 2,
                "engine_sha256": manifest["sha256"]["build/halite"],
                "rules": S.RULES,
                "protocol": "halite3-lab-v1",
            }
            db.execute(
                "INSERT INTO matches(id,job_id,owner_id,mode,seed,seat_json,status,attempts,max_attempts,replay_key,result_json,public,created_at,finished_at) VALUES(?,?,NULL,?,?,?,'complete',1,3,?,?,1,?,?)",
                (
                    mid,
                    jid,
                    mode,
                    spec["seed"],
                    json.dumps(seats),
                    key,
                    json.dumps(normalized),
                    created,
                    created,
                ),
            )
            db.execute(
                "INSERT INTO attempts(match_id,number,status,created_at,finished_at) VALUES(?,1,'complete',?,?)",
                (mid, created, created),
            )
            print("Imported", mid)
        rawdb.close()


if __name__ == "__main__":
    main()
