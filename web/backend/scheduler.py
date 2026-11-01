import itertools
import json
import math
import uuid
from fastapi import HTTPException
from . import settings as S
from .db import connect, now
from .storage import disk_check
from .eligibility import CPP_ONLY, eligible
from .security import is_admin


def require_eligible(versions):
    if any(not eligible(v) for v in versions):
        raise HTTPException(400, CPP_ONLY)


def match_eligible(db, seat_json):
    # Resolve old snapshots against version metadata, including snapshots which
    # predate the language field. Never rewrite the immutable seats.
    seats = json.loads(seat_json)
    for seat in seats:
        row = db.execute(
            "SELECT v.*,b.builtin,b.owner_id FROM versions v JOIN bots b ON b.id=v.bot_id WHERE v.id=?",
            (seat["id"],),
        ).fetchone()
        if not row or not eligible(row):
            return False
    return bool(seats)


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
    # The author id is public (it only addresses the author's avatar).
    item = {
        key: value
        for key, value in seat.items()
        if key not in ("object_key", "owner_id")
    }
    item["author_id"] = seat.get("owner_id")
    return item


# Automatic 4 / 8-player benchmark that runs next to every #0 submission (CMA-271).
# #0 itself stays the fixed 12-game 1v1 benchmark; these games are a separate public job.
MULTI_KIND = "ranked-multi"
MULTI_SEEDS = [11, 29, 47]
MULTI_POOL = 9  # opponents: baseline, raider and the best-rated current #0 bots


def multiplayer_pool(db, candidate):
    """Opponents for the multiplayer benchmark: the two builtins plus the best-rated
    (global ELO) latest #0 submission of every other listed C++ bot."""
    from .contests import current_entries
    from .rating import ratings

    pool = [dict(db.execute(
        "SELECT v.*,b.name,b.owner_id,b.builtin,NULL AS author FROM versions v JOIN bots b ON b.id=v.bot_id WHERE v.id=?",
        (vid,),
    ).fetchone()) for vid in ["builtin-baseline-v1", "builtin-raider-v1"]]
    contest = db.execute("SELECT * FROM contests WHERE number=0").fetchone()
    entries = current_entries(db, contest) if contest else set()
    if entries:
        marks = ",".join("?" * len(entries))
        rows = [dict(r) for r in db.execute(
            f"""SELECT v.*,b.name,b.owner_id,b.builtin,u.display_name AS author FROM contest_entries e
            JOIN versions v ON v.id=e.version_id JOIN bots b ON b.id=v.bot_id LEFT JOIN users u ON u.id=b.owner_id
            WHERE e.id IN ({marks}) AND b.id!=? AND b.builtin=0 AND v.listed=1 AND v.archived=0""",
            (*entries, candidate["bot_id"]),
        )]
        rated = ratings(db)
        rows = [r for r in rows if eligible(r)]
        rows.sort(key=lambda r: (-rated.get(r["id"], {}).get("elo", float("-inf")), -r["created_at"], r["id"]))
        pool += rows[: MULTI_POOL - len(pool)]
    return pool


def multiplayer_games(candidate, pool):
    """(seats, seed) for the multiplayer benchmark, every table with the candidate in
    each seat once. 4 players: the pool cut into triples twice (in order, then
    interleaved), so each opponent sits in two tables with different partners; each
    table plays two of the three maps. 8 players (needs seven opponents): one table
    per map, each leaving out a different window of the pool."""
    n, games = len(pool), []

    def rotations(players, seed):
        for r in range(len(players)):
            games.append((players[r:] + players[:r], seed))

    if n >= 3:
        orders = [pool, [pool[i] for start in range(3) for i in range(start, n, 3)]]
        tables = [[order[(g * 3 + i) % n] for i in range(3)] for order in orders for g in range(math.ceil(n / 3))]
        for g, table in enumerate(tables):
            for seed in MULTI_SEEDS:
                if seed != MULTI_SEEDS[g % 3]:
                    rotations([candidate, *table], seed)
    if n >= 7:
        for g, seed in enumerate(MULTI_SEEDS):
            left_out = {(g * n // 3 + i) % n for i in range(n - 7)}
            rotations([candidate, *(p for i, p in enumerate(pool) if i not in left_out)], seed)
    return games


def create_job(user_id, name, version_ids, modes, seeds, rotate=False, ranked=False):
    disk_check()
    # The admin has no usage quotas (version / seed counts, per-job, daily and concurrent limits).
    with connect() as db:
        admin = is_admin(db, user_id)
    if (
        not version_ids
        or len(version_ids) != len(set(version_ids))
        or (len(version_ids) > 10 and not admin)
    ):
        raise HTTPException(400, "请选择 2 至 10 个不同版本。")
    if (
        not seeds
        or (len(seeds) > 10 and not admin)
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
        require_eligible(versions)
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
            pool = [snapshot(v) for v in multiplayer_pool(db, candidate)]
            multi = multiplayer_games(snapshot(candidate), pool)
        else:
            # Count before enumerating, so an oversized request fails fast.
            limit = S.ADMIN_MAX_MATCHES_PER_JOB if admin else S.MAX_MATCHES_PER_JOB
            planned = len(seeds) * sum(math.comb(len(versions), mode) * (mode if rotate else 1) for mode in modes)
            if planned > limit:
                raise HTTPException(400, f"本次 {planned} 场，单任务上限 {limit} 场，请减少地图或座位轮换。")
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
                # Per-mode overrides of the fields above, frozen into the job.
                "setups": {str(mode): S.MODE_SETUPS[mode] for mode in modes},
            }
        count = len(configurations) + (len(multi) if ranked else 0)
        if not admin:
            today = db.execute(
                "SELECT COUNT(*) FROM matches WHERE owner_id=? AND created_at>=?",
                (user_id, now() - 86400),
            ).fetchone()[0]
            if today + count > S.MAX_MATCHES_PER_DAY:
                raise HTTPException(
                    429, f"每用户 24 小时内最多 {S.MAX_MATCHES_PER_DAY} 场。"
                )
            # The multiplayer benchmark rides along with its #0 job and is not counted separately.
            unfinished = db.execute(
                "SELECT COUNT(DISTINCT m.job_id) FROM matches m JOIN jobs j ON j.id=m.job_id WHERE m.owner_id=? AND m.status IN ('queued','running') AND j.kind!=?",
                (user_id, MULTI_KIND),
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
        if ranked and multi:
            multi_id = str(uuid.uuid4())
            setups = {str(mode): S.MODE_SETUPS[mode] for mode in sorted({len(seats) for seats, _ in multi})}
            db.execute(
                "INSERT INTO jobs(id,owner_id,name,kind,candidate_id,config_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (
                    multi_id,
                    user_id,
                    f"多人评测 · {candidate['name']} {candidate['version']}"[:80],
                    MULTI_KIND,
                    candidate["id"],
                    json.dumps({
                        "season": S.SEASON, "rules": S.RULES, "turns": 200, "width": 32, "height": 32,
                        "modes": [int(m) for m in setups], "seeds": MULTI_SEEDS, "rotate_seats": True,
                        "opponents": [v["id"] for v in pool],
                        "setups": setups,
                    }),
                    created,
                ),
            )
            for seats, seed in multi:
                db.execute(
                    "INSERT INTO matches(id,job_id,owner_id,mode,seed,seat_json,public,created_at) VALUES(?,?,?,?,?,?,1,?)",
                    (str(uuid.uuid4()), multi_id, user_id, len(seats), seed, json.dumps(seats), created),
                )
        if ranked:
            from .contests import attach_ranked

            attach_ranked(db)  # every benchmark run is a submission to contest #0
        return job_id


def match_dict(row):
    item = dict(row)
    if item['status'] in ('remote_queued', 'remote_running'):
        item['status'] = item['status'].removeprefix('remote_')
        item['execution_host'] = 'txcloud'
    config = json.loads(item.pop('job_config_json', '{}'))
    setup = config.get('setups_by_seed', {}).get(f"{item['mode']}:{item['seed']}", {})
    if 'map_seed' in setup:
        item['seed'] = setup['map_seed']
        item['scenario'] = setup.get('scenario')
    item["execution"] = dict(turn_timeout_ms=config.get("turn_timeout_ms",2000),
                             bot_cpu_percent=config.get("bot_cpu_percent",35),
                             batch=config.get("execution_batch","legacy2000"))
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
        "SELECT m.*,j.name AS job_name,j.kind,j.config_json AS job_config_json FROM matches m JOIN jobs j ON j.id=m.job_id WHERE m.id=? AND (m.public=1 OR m.owner_id=?)",
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
    for remote, local in [('remote_queued', 'queued'), ('remote_running', 'running')]:
        if remote in counts:
            counts[local] = counts.get(local, 0) + counts.pop(remote)
    item["counts"] = counts
    item["retryable"] = bool(counts.get("failed")) and all(
        match_eligible(db, r["seat_json"])
        for r in db.execute("SELECT seat_json FROM matches WHERE job_id=? AND status='failed'", (item["id"],))
    )
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
