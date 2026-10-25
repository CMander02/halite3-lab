import itertools
import json
import uuid
from fastapi import HTTPException
from . import settings as S
from .db import connect, now
from .storage import disk_check


def version_info(db, version_id, user_id, owned=False):
    row = db.execute(
        "SELECT v.*,b.name,b.owner_id,b.builtin,u.display_name AS author FROM versions v JOIN bots b ON b.id=v.bot_id LEFT JOIN users u ON u.id=b.owner_id WHERE v.id=? AND (b.owner_id=? OR (?=0 AND b.builtin=1))",
        (version_id, user_id, int(owned)),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Bot 版本不存在或无权访问。")
    return dict(row)


def snapshot(row):
    return {
        key: row[key]
        for key in [
            "id",
            "bot_id",
            "name",
            "version",
            "sha256",
            "filename",
            "object_key",
            "owner_id",
            "builtin",
            "author",
            "language",
        ]
    }


def public_seat(seat):
    return {
        key: value
        for key, value in seat.items()
        if key not in ("object_key", "owner_id")
    }


def create_job(user_id, name, version_ids, modes, seeds, rotate=False, ranked=False):
    disk_check()
    if (
        not version_ids
        or len(version_ids) != len(set(version_ids))
        or len(version_ids) > 10
    ):
        raise HTTPException(400, "请选择 2 至 10 个不同版本。")
    if (
        not seeds
        or len(seeds) > 10
        or len(set(seeds)) != len(seeds)
        or any(
            not isinstance(s, int) or isinstance(s, bool) or not 0 <= s <= 2**32 - 1
            for s in seeds
        )
    ):
        raise HTTPException(400, "地图种子应为 1 至 10 个不同的无符号整数。")
    if (
        not modes
        or len(set(modes)) != len(modes)
        or any(mode not in (2, 4, 8) or mode > len(version_ids) for mode in modes)
    ):
        if not ranked:
            raise HTTPException(400, "比赛人数支持 2、4、8，需要足够的参赛版本。")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        versions = [version_info(db, vid, user_id, owned=ranked) for vid in version_ids]
        if ranked:
            candidate = versions[0]
            prior = db.execute(
                "SELECT id FROM jobs WHERE kind='ranked' AND candidate_id=?",
                (candidate["id"],),
            ).fetchone()
            if prior:
                return prior["id"]
            opponents = [
                version_info(db, vid, user_id)
                for vid in ["builtin-baseline-v1", "builtin-raider-v1"]
            ]
            configurations = [
                ([snapshot(candidate), snapshot(opponent)], seed, rotation)
                for opponent in opponents
                for seed in [11, 29, 47]
                for rotation in [0, 1]
            ]
            name = f"排名评测 · {candidate['name']} {candidate['version']}"
            config = {
                "season": S.SEASON,
                "rules": S.RULES,
                "turns": 200,
                "width": 32,
                "height": 32,
                "modes": [2],
                "seeds": [11, 29, 47],
                "rotate_seats": True,
            }
        else:
            configurations = []
            for mode in modes:
                for combo in itertools.combinations(versions, mode):
                    for seed in seeds:
                        for rotation in range(mode if rotate else 1):
                            configurations.append(
                                ([snapshot(v) for v in combo], seed, rotation)
                            )
            config = {
                "rules": S.RULES,
                "turns": 200,
                "width": 32,
                "height": 32,
                "modes": modes,
                "seeds": seeds,
                "rotate_seats": rotate,
            }
        count = len(configurations)
        if count > S.MAX_MATCHES_PER_JOB:
            raise HTTPException(
                400,
                f"本次 {count} 场，单任务上限 {S.MAX_MATCHES_PER_JOB} 场，请减少地图或座位轮换。",
            )
        today = db.execute(
            "SELECT COUNT(*) FROM matches WHERE owner_id=? AND created_at>=?",
            (user_id, now() - 86400),
        ).fetchone()[0]
        if today + count > S.MAX_MATCHES_PER_DAY:
            raise HTTPException(
                429, f"每用户 24 小时内最多 {S.MAX_MATCHES_PER_DAY} 场。"
            )
        unfinished = db.execute(
            "SELECT COUNT(DISTINCT job_id) FROM matches WHERE owner_id=? AND status IN ('queued','running')",
            (user_id,),
        ).fetchone()[0]
        if unfinished >= 3:
            raise HTTPException(429, "最多同时保留 3 个未完成任务。")
        job_id = str(uuid.uuid4())
        created = now()
        db.execute(
            "INSERT INTO jobs(id,owner_id,name,kind,candidate_id,config_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                job_id,
                user_id,
                name[:80],
                "ranked" if ranked else "private",
                versions[0]["id"] if ranked else None,
                json.dumps(config),
                created,
            ),
        )
        for participants, seed, rotation in configurations:
            seats = participants[rotation:] + participants[:rotation]
            db.execute(
                "INSERT INTO matches(id,job_id,owner_id,mode,seed,seat_json,public,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    job_id,
                    user_id,
                    len(seats),
                    seed,
                    json.dumps(seats),
                    int(ranked),
                    created,
                ),
            )
        return job_id


def match_dict(row):
    item = dict(row)
    item["seats"] = [public_seat(s) for s in json.loads(item.pop("seat_json"))]
    item["result"] = (
        json.loads(item.pop("result_json")) if item.get("result_json") else None
    )
    item["has_replay"] = bool(item.pop("replay_key", None))
    for key in ["owner_id", "lease_token", "lease_until"]:
        item.pop(key, None)
    return item


def get_match(db, match_id, user_id):
    row = db.execute(
        "SELECT m.*,j.name AS job_name,j.kind FROM matches m JOIN jobs j ON j.id=m.job_id WHERE m.id=? AND (m.public=1 OR m.owner_id=?)",
        (match_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "对局不存在或无权访问。")
    return row


def job_dict(db, row):
    item = dict(row)
    item.pop("owner_id", None)
    item["config"] = json.loads(item.pop("config_json"))
    counts = dict(
        db.execute(
            "SELECT status,COUNT(*) FROM matches WHERE job_id=? GROUP BY status",
            (item["id"],),
        ).fetchall()
    )
    item["counts"] = counts
    item["total"] = sum(counts.values())
    item["status"] = (
        "running"
        if counts.get("running") or counts.get("queued")
        else "failed"
        if counts.get("failed")
        else "cancelled"
        if counts.get("cancelled")
        else "complete"
    )
    return item
