"""Contests: admin-run competitions with a submission window, a target-bot bench and a final round on hidden maps.

The lifecycle is derived from the stored times, never stored itself:

  draft      not published; only the administrator sees it
  upcoming   published and visible (from visible_at); submissions not open yet
  open       open_at <= now < close_at. Every submission plays the bench: the
             contest's target bots on the public maps. The bench gives a
             provisional ELO against a shared yardstick; submissions never meet
             each other yet, so nobody can tune against a rival's live bot.
  closed     submissions are over. The final evaluation runs every finalist
             (each user's picked or latest submission) against every other
             finalist and the targets, on the public and the hidden maps.
  finished   final results are published: standings are frozen, every contest
             game becomes public, and only then do they enter the global ELO.

Users can play the targets locally on the public maps (downloads + rules). What
only the cloud gives is the final round: the other contestants' bots, the hidden
maps, one sandbox and time limit for everyone, and the model / effort correction.
"""
import itertools
import json
import math
import random
import re
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from . import catalog as C
from . import contest_docs as D
from . import settings as S
from .db import connect, now
from .rating import attribution, fit_matches
from .scheduler import snapshot
from .security import admin_for, rate_limit, user_for
from .storage import disk_check

router = APIRouter()

MODES = (2, 4, 8)
LANGUAGES = ("cpp",)  # bots are C++17 only (eligibility.CPP_ONLY)
# Bench seat rotations per mode: 1v1 swaps seats, 4p visits every seat, 8p two offsets.
BENCH_ROTATIONS = {2: 2, 4: 4, 8: 2}
# Fields that decide what a bench game is; frozen once submissions open so every
# submission is measured on the same yardstick.
BENCH_FIELDS = ("modes", "public_maps", "targets", "languages", "bench_rotate")
FINAL_FIELDS = ("hidden_maps", "final_rounds")
# Job kinds per stage; contest #0's submissions are the legacy 'ranked' benchmark jobs.
STAGE_KINDS = {"bench": ("contest-bench", "ranked"), "final": ("contest-final", "contest-final")}

SCHEMA = """
CREATE TABLE IF NOT EXISTS contests(
    id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
    visible_at INTEGER, open_at INTEGER NOT NULL, close_at INTEGER NOT NULL,
    published INTEGER NOT NULL DEFAULT 0, config_json TEXT NOT NULL,
    final_job_id TEXT, final_started_at INTEGER, finalized_at INTEGER, standings_json TEXT,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS contest_entries(
    id TEXT PRIMARY KEY, contest_id TEXT NOT NULL REFERENCES contests(id),
    user_id TEXT NOT NULL REFERENCES users(id), version_id TEXT NOT NULL REFERENCES versions(id),
    seq INTEGER NOT NULL, job_id TEXT REFERENCES jobs(id), note TEXT NOT NULL DEFAULT '',
    picked INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
    UNIQUE(contest_id,user_id,seq), UNIQUE(contest_id,version_id));
CREATE INDEX IF NOT EXISTS contest_entries_user ON contest_entries(contest_id,user_id);
"""


PRACTICE_SLUG = "test-0"
FOREVER = 4102444800  # 2100-01-01: the practice contest never closes


def migrate(db):
    db.executescript(SCHEMA)
    if "contest_id" not in {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}:
        db.execute("ALTER TABLE jobs ADD COLUMN contest_id TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS jobs_contest ON jobs(contest_id,kind)")
    columns = {row["name"] for row in db.execute("PRAGMA table_info(contests)")}
    for name, kind in [("number", "INTEGER"), ("prompt", "TEXT NOT NULL DEFAULT ''"), ("rules", "TEXT NOT NULL DEFAULT ''")]:
        if name not in columns:
            db.execute(f"ALTER TABLE contests ADD COLUMN {name} {kind}")
    for row in db.execute("SELECT id FROM contests WHERE number IS NULL ORDER BY created_at").fetchall():
        db.execute("UPDATE contests SET number=(SELECT COALESCE(MAX(number),0)+1 FROM contests) WHERE id=?", (row["id"],))
    ensure_practice(db)
    attach_ranked(db)


def ensure_practice(db):
    """Contest #0: the standing test contest. It is the fixed 12-game benchmark
    (baseline + raider, 1v1, seeds 11 / 29 / 47, seats swapped) as a contest: no
    deadline, no final round, games public at once and counted in the global ELO."""
    if db.execute("SELECT 1 FROM contests WHERE number=0").fetchone():
        return
    first = db.execute("SELECT MIN(created_at) FROM jobs WHERE kind='ranked'").fetchone()[0] or now()
    config = {
        "modes": [2], "public_maps": {"2": [11, 29, 47]}, "hidden_maps": {"2": []},
        "targets": ["builtin-baseline-v1", "builtin-raider-v1"], "base_version_id": "builtin-baseline-v1",
        "downloads": ["builtin-baseline-v1", "builtin-raider-v1"], "languages": ["cpp"],
        "max_submissions": 200, "bench_rotate": True, "final_rounds": 1, "auto_final": False, "practice": True,
        "setups": {"2": S.MODE_SETUPS[2]},
    }
    db.execute(
        """INSERT INTO contests(id,number,slug,title,summary,description,visible_at,open_at,close_at,published,config_json,created_at,updated_at)
        VALUES(?,0,?,?,?,?,NULL,?,?,1,?,?,?)""",
        (str(uuid.uuid4()), PRACTICE_SLUG, "测试比赛",
         "常驻测试赛：随时提交，对阵 baseline 与 raider 各 6 场，成绩立即计入全局 ELO。",
         "原来的“参评 / 12 场固定评测”就是这场比赛。之前所有参评过的版本都已按提交时间收进来。\n"
         "这场比赛没有截止时间、没有隐藏地图和正式评测；对局立即公开，计入全局 ELO 和 Tier。",
         first, FOREVER, json.dumps(config), now(), now()),
    )


def attach_ranked(db):
    """File every 12-game benchmark job (kind='ranked') under contest #0 as a submission."""
    contest = db.execute("SELECT id FROM contests WHERE number=0").fetchone()
    if not contest:
        return
    jobs = db.execute(
        "SELECT id,owner_id,candidate_id,created_at FROM jobs WHERE kind='ranked' AND contest_id IS NULL ORDER BY created_at,rowid"
    ).fetchall()
    # #0's automatic 4 / 8-player runs belong to #0 too (its match list and multiplayer boards)
    db.execute("UPDATE jobs SET contest_id=? WHERE kind='ranked-multi' AND contest_id IS NULL", (contest["id"],))
    for job in jobs:
        db.execute("UPDATE jobs SET contest_id=? WHERE id=?", (contest["id"], job["id"]))
        if db.execute("SELECT 1 FROM contest_entries WHERE contest_id=? AND version_id=?", (contest["id"], job["candidate_id"])).fetchone():
            continue
        seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM contest_entries WHERE contest_id=? AND user_id=?",
                         (contest["id"], job["owner_id"])).fetchone()[0]
        db.execute(
            "INSERT INTO contest_entries(id,contest_id,user_id,version_id,seq,job_id,created_at) VALUES(?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), contest["id"], job["owner_id"], job["candidate_id"], seq, job["id"], job["created_at"]),
        )


# ---------------------------------------------------------------- lookups


def status(row, at=None):
    at = now() if at is None else at
    if row["finalized_at"]:
        return "finished"
    if not row["published"]:
        return "draft"
    if at < row["open_at"]:
        return "upcoming"
    if at < row["close_at"]:
        return "open"
    return "closed"


def visible(row, user):
    if user and user["is_admin"]:
        return True
    return bool(row["published"]) and (row["visible_at"] is None or now() >= row["visible_at"])


def load(db, key, user):
    row = db.execute("SELECT * FROM contests WHERE id=? OR slug=?", (key, key)).fetchone()
    if not row or not visible(row, user):
        raise HTTPException(404, "比赛不存在或尚未开放浏览。")
    return row


def version_rows(db, ids):
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = db.execute(
        f"""SELECT v.*,b.name,b.owner_id,b.builtin,u.display_name AS author,COALESCE(u.is_admin,0) AS owner_admin
        FROM versions v JOIN bots b ON b.id=v.bot_id LEFT JOIN users u ON u.id=b.owner_id WHERE v.id IN ({marks})""",
        list(ids),
    ).fetchall()
    return {row["id"]: row for row in rows}


def finalists(db, contest_id):
    """{user_id: entry} — each user's picked submission, else their latest one."""
    chosen = {}
    for row in db.execute(
        "SELECT * FROM contest_entries WHERE contest_id=? ORDER BY user_id,picked DESC,seq DESC", (contest_id,)
    ):
        chosen.setdefault(row["user_id"], row)
    return chosen


def current_entries(db, contest):
    """Entry ids that are ranked: each user's finalist, or in contest #0 (where people
    keep several different bots) the latest submission of every bot."""
    if not json.loads(contest["config_json"]).get("practice"):
        return {e["id"] for e in finalists(db, contest["id"]).values()}
    return {row["id"] for row in db.execute(
        """SELECT e.id FROM contest_entries e JOIN versions v ON v.id=e.version_id WHERE e.contest_id=? AND e.seq=(
        SELECT MAX(x.seq) FROM contest_entries x JOIN versions y ON y.id=x.version_id
        WHERE x.contest_id=e.contest_id AND x.user_id=e.user_id AND y.bot_id=v.bot_id)""", (contest["id"],))}


def admin_id(db):
    row = db.execute("SELECT id FROM users WHERE is_admin=1").fetchone()
    return row["id"] if row else None


# ---------------------------------------------------------------- schedules


def bench_games(config, candidate, targets):
    """(seats, seed) for one submission: the candidate against the targets on every public map."""
    opponents = [t for t in targets if t["id"] != candidate["id"]] or targets
    games = []
    for mode in config["modes"]:
        k = mode - 1
        if mode == 2:
            groups = [[o] for o in opponents]
        else:
            # Every target appears at least once; a short target list repeats to fill the seats.
            groups = [[opponents[(g * k + i) % len(opponents)] for i in range(k)] for g in range(math.ceil(len(opponents) / k))]
        rotations = BENCH_ROTATIONS[mode] if config.get("bench_rotate", True) else 1
        for group in groups:
            players = [candidate, *group]
            for seed in config["public_maps"][str(mode)]:
                for r in range(rotations):
                    shift = r * mode // rotations
                    games.append((players[shift:] + players[:shift], seed))
    return games


def final_games(config, contest_id, players, finalist_ids):
    """(seats, seed) for the final: 1v1 is a full double round robin on every map;
    4 / 8-player modes play `final_rounds` random groupings per map. Games without a
    finalist are skipped (target vs target says nothing about the contestants)."""
    rng = random.Random(contest_id)
    games = []
    for mode in config["modes"]:
        seeds = config["public_maps"][str(mode)] + config["hidden_maps"].get(str(mode), [])
        if mode == 2:
            for a, b in itertools.combinations(players, 2):
                if a["id"] in finalist_ids or b["id"] in finalist_ids:
                    for seed in seeds:
                        games += [([a, b], seed), ([b, a], seed)]
            continue
        # Fewer players than seats: targets fill the rest (a finalist never takes two seats).
        fillers = [p for p in players if p["id"] not in finalist_ids] or players
        for _ in range(config.get("final_rounds", 4)):
            for seed in seeds:
                order = players[:]
                rng.shuffle(order)
                for start in range(0, len(order), mode):
                    group = order[start:start + mode]
                    others = [p for p in players if p not in group]
                    rng.shuffle(others)
                    group += others[: mode - len(group)]
                    for i in range(mode - len(group)):
                        group.append(fillers[i % len(fillers)])
                    if any(p["id"] in finalist_ids for p in group):
                        games.append((group, seed))
    return games


def insert_job(db, *, owner_id, name, kind, contest, candidate_id, games, public=0):
    config = json.loads(contest["config_json"])
    job_id = str(uuid.uuid4())
    created = now()
    job_config = {
        "contest_id": contest["id"], "contest": contest["slug"], "stage": kind.removeprefix("contest-"),
        "rules": S.RULES, "turns": 200, "width": 32, "height": 32,
        "modes": config["modes"], "seeds": sorted({seed for _, seed in games}),
        "rotate_seats": config.get("bench_rotate", True), "setups": config["setups"],
    }
    db.execute(
        "INSERT INTO jobs(id,owner_id,name,kind,candidate_id,config_json,created_at,contest_id) VALUES(?,?,?,?,?,?,?,?)",
        (job_id, owner_id, name[:80], kind, candidate_id, json.dumps(job_config), created, contest["id"]),
    )
    for seats, seed in games:
        db.execute(
            "INSERT INTO matches(id,job_id,owner_id,mode,seed,seat_json,public,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), job_id, owner_id, len(seats), seed, json.dumps(seats), public, created),
        )
    return job_id


def target_snapshots(db, config):
    rows = version_rows(db, config["targets"])
    return [snapshot(dict(rows[vid])) for vid in config["targets"] if vid in rows]


def start_final(db, contest):
    """Queue the final evaluation (cancelling a previous attempt's queued games)."""
    config = json.loads(contest["config_json"])
    if contest["final_job_id"]:
        db.execute("UPDATE matches SET status='cancelled' WHERE job_id=? AND status='queued'", (contest["final_job_id"],))
    chosen = finalists(db, contest["id"])
    rows = version_rows(db, [e["version_id"] for e in chosen.values()])
    players = [snapshot(dict(rows[e["version_id"]])) for e in chosen.values()]
    finalist_ids = {p["id"] for p in players}
    players += [t for t in target_snapshots(db, config) if t["id"] not in finalist_ids]
    games = final_games(config, contest["id"], players, finalist_ids) if finalist_ids else []
    job_id = insert_job(db, owner_id=admin_id(db), name=f"正式评测 · {contest['title']}", kind="contest-final",
                        contest=contest, candidate_id=None, games=games)
    db.execute("UPDATE contests SET final_job_id=?,final_started_at=?,updated_at=? WHERE id=?",
               (job_id, now(), now(), contest["id"]))
    return job_id, len(games)


def finalize(db, contest):
    """Freeze the final standings and publish every game of the contest."""
    data = {"computed_at": now(), "final": compute(db, contest, "final"), "bench": compute(db, contest, "bench")}
    db.execute("UPDATE contests SET finalized_at=?,standings_json=?,updated_at=? WHERE id=?",
               (now(), json.dumps(data), now(), contest["id"]))
    db.execute("UPDATE matches SET public=1 WHERE job_id IN (SELECT id FROM jobs WHERE contest_id=?)", (contest["id"],))


def tick():
    """Called by the runner loop: start finals once the window closes and publish them when done."""
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM contests WHERE published=1 AND finalized_at IS NULL AND close_at<=?", (now(),)
        ).fetchall()
        for row in rows:
            if not json.loads(row["config_json"]).get("auto_final", True):
                continue
            if not row["final_job_id"]:
                start_final(db, row)
            elif not db.execute(
                "SELECT 1 FROM matches WHERE job_id=? AND status IN ('queued','running') LIMIT 1", (row["final_job_id"],)
            ).fetchone():
                finalize(db, row)


# ---------------------------------------------------------------- standings


def compute(db, contest, stage):
    """Standings per mode and overall for the bench or the final stage.

    Every row is one version (a submission or a target). Raw ELO is the same
    Bradley-Terry fit as the global board, over this contest stage only; the
    model / effort / harness correction is applied the same way."""
    config = json.loads(contest["config_json"])
    hidden = {int(mode): set(seeds) for mode, seeds in config["hidden_maps"].items()}
    # The final counts only the current final job: a restart discards the previous schedule.
    matches = db.execute(
        """SELECT m.mode,m.seed,m.seat_json,m.result_json FROM matches m JOIN jobs j ON j.id=m.job_id
        WHERE j.contest_id=? AND j.kind IN (?,?) AND (j.kind<>'contest-final' OR j.id=?) AND m.status='complete' AND m.result_json IS NOT NULL""",
        (contest["id"], *STAGE_KINDS[stage], contest["final_job_id"]),
    ).fetchall()
    entries = {row["version_id"]: row for row in db.execute("SELECT * FROM contest_entries WHERE contest_id=?", (contest["id"],))}
    targets = set(config["targets"])
    current = current_entries(db, contest)
    chosen = {vid for vid, e in entries.items() if e["id"] in current}
    catalog = C.load(db)
    info = version_rows(db, set(entries) | targets)
    users = {row["id"]: row for row in db.execute(
        "SELECT u.id,u.display_name,u.username FROM users u JOIN contest_entries e ON e.user_id=u.id WHERE e.contest_id=?", (contest["id"],))}

    def table(rows):
        versus = {}

        def record(a, b, score):
            if b in targets:
                cell = versus.setdefault(a, {}).setdefault(b, [0.0, 0])
                cell[0] += score
                cell[1] += 1

        fitted = fit_matches(rows, record)
        hidden_wins = {}
        for row in rows:
            if row["seed"] in hidden.get(row["mode"], ()):
                stats = json.loads(row["result_json"])["stats"]
                for index, seat in enumerate(json.loads(row["seat_json"])):
                    cell = hidden_wins.setdefault(seat["id"], [0, 0])
                    cell[0] += stats.get(str(index), {}).get("rank") == 1
                    cell[1] += 1
        result = []
        for vid, stats in fitted.items():
            version = info.get(vid)
            if not version:
                continue
            entry = entries.get(vid)
            is_target = vid in targets and not entry
            attr = None if is_target or version["builtin"] else attribution(version, catalog)
            correction = attr["correction"] if attr else 0.0
            owner = users.get(entry["user_id"]) if entry else None
            result.append({
                "version_id": vid, "bot_id": version["bot_id"], "bot_name": version["name"], "version": version["version"],
                "language": version["language"], "target": is_target,
                "entry_id": entry["id"] if entry else None, "seq": entry["seq"] if entry else None,
                "user_id": entry["user_id"] if entry else version["owner_id"],
                "author": owner["display_name"] if owner else version["author"],
                "current": vid in chosen,
                "games": stats["games"], "wins": stats["wins"], "win_rate": stats["wins"] / stats["games"],
                "avg_rank": stats["rank_sum"] / stats["games"], "mean_score": stats["score_sum"] / stats["games"],
                "elo": round(stats["elo"], 1), "elo_sd": round(stats["elo_sd"], 1),
                "correction": correction, "adjusted_elo": round(stats["elo"] - correction, 1),
                "attribution": {k: {"value": attr[k]["value"], "offset": attr[k]["offset"], "source": attr[k]["source"]} for k in C.KINDS}
                | {"correction": correction, "mismatch": attr["mismatch"]} if attr else None,
                "versus": {t: {"score": s, "games": g} for t, (s, g) in versus.get(vid, {}).items()},
                "hidden": {"wins": hidden_wins[vid][0], "games": hidden_wins[vid][1]} if vid in hidden_wins else None,
            })
        result.sort(key=lambda e: (-e["adjusted_elo"], -e["elo"], e["bot_name"]))
        rank = 0
        for item in result:
            # Ranked: each user's current submission. Targets and superseded submissions are reference rows.
            item["rank"] = None
            if item["current"]:
                rank += 1
                item["rank"] = rank
        return result

    data = {"overall": table(matches)}
    for mode in config["modes"]:
        data[str(mode)] = table([m for m in matches if m["mode"] == mode])
    if config.get("practice") and stage == "bench":
        # #0's 4 / 8-player runs get their own boards; "overall" stays the 12-game 1v1 benchmark.
        multi = db.execute(
            """SELECT m.mode,m.seed,m.seat_json,m.result_json FROM matches m JOIN jobs j ON j.id=m.job_id
            WHERE j.contest_id=? AND j.kind='ranked-multi' AND m.status='complete' AND m.result_json IS NOT NULL""",
            (contest["id"],),
        ).fetchall()
        for mode in sorted({m["mode"] for m in multi}):
            data[str(mode)] = table([m for m in multi if m["mode"] == mode])
    return data


def stage_progress(db, contest, stage):
    counts = dict(db.execute(
        """SELECT m.status,COUNT(*) FROM matches m JOIN jobs j ON j.id=m.job_id
        WHERE j.contest_id=? AND j.kind IN (?,?) AND (j.kind<>'contest-final' OR j.id=?) GROUP BY m.status""",
        (contest["id"], *STAGE_KINDS[stage], contest["final_job_id"]),
    ).fetchall())
    return {"counts": counts, "total": sum(counts.values())}


# ---------------------------------------------------------------- serialisation


def public_view(db, row, user, detail=False):
    config = json.loads(row["config_json"])
    admin = bool(user and user["is_admin"])
    state = status(row)
    users, entries = db.execute(
        "SELECT COUNT(DISTINCT user_id),COUNT(*) FROM contest_entries WHERE contest_id=?", (row["id"],)
    ).fetchone()
    item = {
        "id": row["id"], "number": row["number"], "slug": row["slug"], "title": row["title"], "summary": row["summary"], "status": state,
        "practice": bool(config.get("practice")),
        "visible_at": row["visible_at"], "open_at": row["open_at"], "close_at": row["close_at"],
        "published": bool(row["published"]), "final_started_at": row["final_started_at"], "finalized_at": row["finalized_at"],
        "modes": config["modes"], "participants": users, "submissions": entries,
        "max_submissions": config["max_submissions"], "languages": config["languages"],
    }
    if user:
        item["my_submissions"] = db.execute(
            "SELECT COUNT(*) FROM contest_entries WHERE contest_id=? AND user_id=?", (row["id"], user["id"])
        ).fetchone()[0]
    if not detail:
        return item
    reveal = admin or state == "finished"
    versions = version_rows(db, set(config["targets"]) | set(config["downloads"]) | ({config["base_version_id"]} - {None}))

    def describe(vid):
        v = versions.get(vid)
        return v and {"version_id": vid, "bot_name": v["name"], "version": v["version"], "language": v["language"],
                      "author": "平台基准" if v["builtin"] else v["author"], "builtin": bool(v["builtin"]),
                      "downloadable": vid in config["downloads"] or vid == config["base_version_id"], "notes": v["notes"]}

    item.update({
        "description": row["description"],
        "rules_text": D.rules_markdown(row, config),
        "prompt_text": D.prompt_markdown(row, config, S.ORIGIN),
        "maps": {
            str(mode): {
                **{k: config["setups"][str(mode)][k] for k in ("width", "height", "turns", "seconds")},
                "rules": config["setups"][str(mode)]["rules"],
                "public": config["public_maps"][str(mode)],
                "hidden": config["hidden_maps"].get(str(mode), []) if reveal else None,
                "hidden_count": len(config["hidden_maps"].get(str(mode), [])),
            }
            for mode in config["modes"]
        },
        "targets": [describe(v) for v in config["targets"] if describe(v)],
        "base": describe(config["base_version_id"]) if config["base_version_id"] else None,
        "downloads": [describe(v) for v in config["downloads"] if describe(v)],
        "bench_rotate": config.get("bench_rotate", True), "final_rounds": config.get("final_rounds", 4),
        "auto_final": config.get("auto_final", True),
        "bench_games": len(bench_games(config, {"id": "candidate"}, [{"id": t} for t in config["targets"]])),
        "progress": {"bench": stage_progress(db, row, "bench"), "final": stage_progress(db, row, "final")},
    })
    if admin:
        item["config"] = {k: v for k, v in config.items() if k != "setups"}
        item["prompt"], item["rules"] = row["prompt"], row["rules"]
        # Games the final would queue right now (current finalists + targets).
        players = [{"id": f"f{i}"} for i in range(len(finalists(db, row["id"])))]
        ids = {p["id"] for p in players}
        players += [{"id": t} for t in config["targets"]]
        item["final_games_estimate"] = len(final_games(config, row["id"], players, ids))
    return item


def entry_view(db, contest, entry, bench):
    version = version_rows(db, [entry["version_id"]]).get(entry["version_id"])
    counts = dict(db.execute("SELECT status,COUNT(*) FROM matches WHERE job_id=? GROUP BY status", (entry["job_id"],)).fetchall()) if entry["job_id"] else {}
    rows = {mode: next((r for r in table if r["version_id"] == entry["version_id"]), None) for mode, table in bench.items()}
    return {
        "id": entry["id"], "seq": entry["seq"], "version_id": entry["version_id"], "bot_id": version["bot_id"],
        "bot_name": version["name"], "version": version["version"], "language": version["language"],
        "note": entry["note"], "picked": bool(entry["picked"]), "created_at": entry["created_at"], "job_id": entry["job_id"],
        "counts": counts, "total": sum(counts.values()), "stats": rows,
    }


# ---------------------------------------------------------------- public API


@router.get("/api/contests")
def list_contests(request: Request):
    user = user_for(request, False)
    with connect() as db:
        rows = db.execute("SELECT * FROM contests ORDER BY number DESC").fetchall()
        return {"contests": [public_view(db, row, user) for row in rows if visible(row, user)]}


@router.get("/api/contests/{key}")
def contest_detail(key: str, request: Request):
    user = user_for(request, False)
    with connect() as db:
        return public_view(db, load(db, key, user), user, detail=True)


@router.get("/api/contests/{key}/standings")
def contest_standings(key: str, request: Request, stage: str = "bench"):
    user = user_for(request, False)
    if stage not in ("bench", "final"):
        raise HTTPException(400, "stage 只能是 bench 或 final。")
    with connect() as db:
        row = load(db, key, user)
        state = status(row)
        if row["standings_json"]:
            frozen = json.loads(row["standings_json"])
            return {"stage": stage, "final": True, "computed_at": frozen["computed_at"], "standings": frozen[stage]}
        if stage == "final" and not (user and user["is_admin"]):
            raise HTTPException(403, "正式评测结果在比赛结束后公布。")
        if state in ("draft", "upcoming") and not (user and user["is_admin"]):
            return {"stage": stage, "final": False, "computed_at": now(), "standings": {"overall": []}}
        return {"stage": stage, "final": False, "computed_at": now(), "standings": compute(db, row, stage)}


@router.get("/api/contests/{key}/entries")
def my_entries(key: str, request: Request):
    user = user_for(request)
    with connect() as db:
        row = load(db, key, user)
        frozen = json.loads(row["standings_json"]) if row["standings_json"] else None
        bench = frozen["bench"] if frozen else compute(db, row, "bench")
        final = frozen["final"] if frozen else None
        entries = db.execute(
            "SELECT * FROM contest_entries WHERE contest_id=? AND user_id=? ORDER BY seq DESC", (row["id"], user["id"])
        ).fetchall()
        current = current_entries(db, row)
        result = [entry_view(db, row, e, bench) | {"current": e["id"] in current} for e in entries]
        if final:
            for item in result:
                item["final"] = {mode: next((r for r in table if r["version_id"] == item["version_id"]), None) for mode, table in final.items()}
        return {"entries": result}


class EntryCreate(BaseModel):
    version_id: str
    note: str = Field(default="", max_length=500)


# Contest submissions are single, canonically named files.
CANONICAL = {"cpp": "bot.cpp", "python": "bot.py"}
LANGUAGE_NAMES = {"cpp": "C++17", "python": "Python"}


def check_entry(db, row, user, version=None):
    """Raise unless `user` may submit now (and, given a version row, submit that version).
    Returns the user's submission count so far."""
    config = json.loads(row["config_json"])
    if status(row) != "open":
        raise HTTPException(409, "比赛当前不在提交窗口内。")
    count = db.execute("SELECT COUNT(*) FROM contest_entries WHERE contest_id=? AND user_id=?", (row["id"], user["id"])).fetchone()[0]
    if count >= config["max_submissions"] and not user["is_admin"]:
        raise HTTPException(409, f"每人最多提交 {config['max_submissions']} 次，已用完。")
    if version is None:
        return count
    if not version or version["owner_id"] != user["id"]:
        raise HTTPException(404, "Bot 版本不存在或无权访问。")
    if version["archived"]:
        raise HTTPException(400, "已归档的版本不能提交。")
    if version["language"] not in config["languages"]:
        names = " / ".join(LANGUAGE_NAMES[x] for x in config["languages"])
        raise HTTPException(400, f"这场比赛只接受 {names}。")
    if version["filename"] != CANONICAL[version["language"]]:
        raise HTTPException(400, f"比赛只接受单文件 {CANONICAL[version['language']]}（这个版本上传的是 {version['filename']}）。")
    if db.execute("SELECT 1 FROM contest_entries WHERE contest_id=? AND version_id=?", (row["id"], version["id"])).fetchone():
        raise HTTPException(409, "这个版本已经提交过，请上传新版本后再提交。")
    return count


def owned(db, version_id):
    return db.execute(
        "SELECT v.*,b.name,b.owner_id,b.builtin,u.display_name AS author FROM versions v JOIN bots b ON b.id=v.bot_id JOIN users u ON u.id=b.owner_id WHERE v.id=?",
        (version_id,),
    ).fetchone()


def contest_for_entry(user, key):
    """The contest row, checked for an open window and remaining quota (before an upload)."""
    with connect() as db:
        row = load(db, key, user)
        check_entry(db, row, user)
        return row


def enter(user, key, version_id, note=""):
    """Submit one of the user's versions to a contest; returns the new entry."""
    disk_check()
    with connect() as db:
        row = load(db, key, user)
        practice = json.loads(row["config_json"]).get("practice")
        if practice:
            check_entry(db, row, user, owned(db, version_id))
    if practice:
        # Contest #0 is the fixed public benchmark: the ranked job files itself under #0.
        from .scheduler import create_job

        job_id = create_job(user["id"], "排名评测", [version_id], [2], [11, 29, 47], True, True)
        with connect() as db:
            entry = db.execute("SELECT * FROM contest_entries WHERE contest_id=? AND version_id=?", (row["id"], version_id)).fetchone()
            db.execute("UPDATE contest_entries SET note=? WHERE id=?", (note, entry["id"]))
            games = db.execute("SELECT COUNT(*) FROM matches WHERE job_id=?", (job_id,)).fetchone()[0]
        return {"id": entry["id"], "seq": entry["seq"], "job_id": job_id, "games": games, "version_id": version_id}
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = load(db, key, user)
        config = json.loads(row["config_json"])
        version = owned(db, version_id)
        count = check_entry(db, row, user, version)
        # A newer submission supersedes the queued bench games of the previous ones.
        db.execute(
            """UPDATE matches SET status='cancelled' WHERE status='queued' AND job_id IN
            (SELECT job_id FROM contest_entries WHERE contest_id=? AND user_id=?)""",
            (row["id"], user["id"]),
        )
        db.execute("UPDATE contest_entries SET picked=0 WHERE contest_id=? AND user_id=?", (row["id"], user["id"]))
        games = bench_games(config, snapshot(dict(version)), target_snapshots(db, config))
        seq = count + 1
        job_id = insert_job(db, owner_id=user["id"], name=f"{row['title']} · 第 {seq} 次提交 · {version['name']} {version['version']}",
                            kind="contest-bench", contest=row, candidate_id=version["id"], games=games)
        entry_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO contest_entries(id,contest_id,user_id,version_id,seq,job_id,note,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (entry_id, row["id"], user["id"], version["id"], seq, job_id, note, now()),
        )
    return {"id": entry_id, "seq": seq, "job_id": job_id, "games": len(games), "version_id": version_id}


@router.post("/api/contests/{key}/entries", status_code=201)
def submit(key: str, payload: EntryCreate, request: Request):
    """Submit an already uploaded version (see POST /api/contests/{key}/submit to upload bot.cpp directly)."""
    user = user_for(request)
    rate_limit(request, "contest-submit", 30, 3600, user["id"], exempt=user["is_admin"])
    return enter(user, key, payload.version_id, payload.note)


class Pick(BaseModel):
    entry_id: str


@router.put("/api/contests/{key}/pick")
def pick(key: str, payload: Pick, request: Request):
    user = user_for(request)
    with connect() as db:
        row = load(db, key, user)
        if status(row) != "open":
            raise HTTPException(409, "只能在提交窗口内选择参加正式评测的版本。")
        if not db.execute("SELECT 1 FROM contest_entries WHERE id=? AND contest_id=? AND user_id=?", (payload.entry_id, row["id"], user["id"])).fetchone():
            raise HTTPException(404, "提交记录不存在。")
        db.execute("UPDATE contest_entries SET picked=(id=?) WHERE contest_id=? AND user_id=?", (payload.entry_id, row["id"], user["id"]))
    return {"ok": True}


@router.get("/api/contests/{key}/downloads/{version_id}")
def download(key: str, version_id: str, request: Request):
    user = user_for(request, False)
    with connect() as db:
        row = load(db, key, user)
        config = json.loads(row["config_json"])
        if version_id not in config["downloads"] and version_id != config["base_version_id"]:
            raise HTTPException(404, "这个版本没有开放下载。")
        version = version_rows(db, [version_id]).get(version_id)
    if not version or not version["object_key"] or not (S.DATA / version["object_key"]).is_file():
        raise HTTPException(404, "文件不存在。")
    name = re.sub(r"[^A-Za-z0-9._-]", "_", f"{version['name']}-{version['version']}-{version['filename']}")[:120]
    return FileResponse(S.DATA / version["object_key"], filename=name, media_type="application/octet-stream")


@router.get("/api/contests/{key}/kit.zip")
def problem_kit(key: str, request: Request):
    """Problem kit: prompt, rules, protocol, public maps, reference bots, C++ starter and CLI."""
    user = user_for(request, False)
    with connect() as db:
        row = load(db, key, user)
        data = D.kit(db, row, json.loads(row["config_json"]), S.ORIGIN, version_rows)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="halite3-{row["slug"]}-kit.zip"'})


@router.get("/api/contests/{key}/prompt.md")
def problem_prompt(key: str, request: Request):
    """PROMPT.md followed by RULES.md, as one text an agent can read."""
    user = user_for(request, False)
    with connect() as db:
        row = load(db, key, user)
    config = json.loads(row["config_json"])
    return PlainTextResponse(D.prompt_markdown(row, config, S.ORIGIN) + "\n\n" + D.rules_markdown(row, config),
                             media_type="text/markdown; charset=utf-8")


@router.get("/api/contests/{key}/setup/{mode}")
def local_setup(key: str, mode: int, request: Request, rules_only: bool = False):
    """Map size, turns and rules of one mode, for running the same games locally
    (rules_only=true returns just the engine's -c rules file)."""
    user = user_for(request, False)
    with connect() as db:
        row = load(db, key, user)
    config = json.loads(row["config_json"])
    if mode not in config["modes"]:
        raise HTTPException(404, "这场比赛没有这个人数模式。")
    setup = config["setups"][str(mode)]
    if rules_only:
        return setup["rules"]
    return {"mode": mode, "width": setup["width"], "height": setup["height"], "turns": setup["turns"],
            "seconds": setup["seconds"], "rules": setup["rules"], "public_maps": config["public_maps"][str(mode)]}


# ---------------------------------------------------------------- administration


class ContestIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,39}$")
    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=20000)
    prompt: str = Field(default="", max_length=20000)
    rules: str = Field(default="", max_length=20000)
    visible_at: int | None = None
    open_at: int
    close_at: int
    published: bool = False
    modes: list[int]
    public_maps: dict[str, list[int]]
    hidden_maps: dict[str, list[int]] = {}
    targets: list[str]
    base_version_id: str | None = None
    downloads: list[str] = []
    languages: list[str] = ["cpp"]
    max_submissions: int = Field(default=20, ge=1, le=200)
    bench_rotate: bool = True
    final_rounds: int = Field(default=4, ge=1, le=20)
    auto_final: bool = True


def seeds_ok(seeds, limit):
    return len(seeds) <= limit and len(set(seeds)) == len(seeds) and all(
        isinstance(s, int) and not isinstance(s, bool) and 0 <= s <= 2**32 - 1 for s in seeds)


def validate(db, payload):
    if payload.open_at >= payload.close_at:
        raise HTTPException(400, "提交截止时间必须晚于开放时间。")
    if payload.visible_at is not None and payload.visible_at > payload.open_at:
        raise HTTPException(400, "开放浏览时间不能晚于提交开放时间。")
    modes = sorted(set(payload.modes))
    if not modes or any(m not in MODES for m in modes):
        raise HTTPException(400, "比赛人数从 1v1、4 人、8 人中至少选一种。")
    public, hidden = {}, {}
    for mode in modes:
        p = payload.public_maps.get(str(mode), [])
        h = payload.hidden_maps.get(str(mode), [])
        if not p or not seeds_ok(p, 10) or not seeds_ok(h, 10) or set(p) & set(h):
            raise HTTPException(400, f"{mode} 人模式：公开地图 1 至 10 个、隐藏地图最多 10 个，种子为不重复的无符号整数，两组不能重叠。")
        public[str(mode)], hidden[str(mode)] = p, h
    languages = [x for x in LANGUAGES if x in payload.languages]
    if not languages:
        raise HTTPException(400, "至少允许一种语言。")
    offered = list(dict.fromkeys(payload.targets))
    if not 1 <= len(offered) <= 8:
        raise HTTPException(400, "靶子 bot 需要 1 至 8 个。")
    extra = list(dict.fromkeys(payload.downloads))
    rows = version_rows(db, set(offered) | set(extra) | ({payload.base_version_id} - {None}))
    for vid in [*offered, *extra, *([payload.base_version_id] if payload.base_version_id else [])]:
        row = rows.get(vid)
        if not row or not (row["builtin"] or row["owner_admin"]):
            raise HTTPException(400, "靶子、基础 bot 和下载只能使用平台基准或管理员自己的版本。")
    return {
        "modes": modes, "public_maps": public, "hidden_maps": hidden, "targets": offered,
        "base_version_id": payload.base_version_id, "downloads": extra, "languages": languages,
        "max_submissions": payload.max_submissions, "bench_rotate": payload.bench_rotate,
        "final_rounds": payload.final_rounds, "auto_final": payload.auto_final,
        "setups": {str(mode): S.MODE_SETUPS[mode] for mode in modes},
    }


@router.get("/api/admin/contest-options")
def contest_options(request: Request):
    """Versions that can serve as targets, base bot or downloads: platform baselines and the admin's own."""
    user = admin_for(request)
    with connect() as db:
        rows = db.execute(
            """SELECT v.id,v.version,v.language,v.created_at,b.name,b.builtin FROM versions v JOIN bots b ON b.id=v.bot_id
            WHERE (b.builtin=1 OR b.owner_id=?) AND v.archived=0 ORDER BY b.builtin DESC,b.name,v.created_at DESC""",
            (user["id"],),
        ).fetchall()
    return {"versions": [dict(r) | {"builtin": bool(r["builtin"])} for r in rows], "setups": {str(m): S.MODE_SETUPS[m] for m in MODES}}


@router.post("/api/admin/contests", status_code=201)
def create_contest(payload: ContestIn, request: Request):
    admin_for(request)
    with connect() as db:
        config = validate(db, payload)
        contest_id = str(uuid.uuid4())
        try:
            db.execute(
                """INSERT INTO contests(id,number,slug,title,summary,description,prompt,rules,visible_at,open_at,close_at,published,config_json,created_at,updated_at)
                VALUES(?,(SELECT COALESCE(MAX(number),0)+1 FROM contests),?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (contest_id, payload.slug, payload.title.strip(), payload.summary, payload.description, payload.prompt, payload.rules,
                 payload.visible_at, payload.open_at, payload.close_at, int(payload.published), json.dumps(config), now(), now()),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(409, "比赛短名已被使用。")
            raise
    return {"id": contest_id}


@router.put("/api/admin/contests/{contest_id}")
def update_contest(contest_id: str, payload: ContestIn, request: Request):
    admin_for(request)
    with connect() as db:
        row = db.execute("SELECT * FROM contests WHERE id=?", (contest_id,)).fetchone()
        if not row:
            raise HTTPException(404, "比赛不存在。")
        if row["finalized_at"]:
            raise HTTPException(409, "比赛结果已公布，不能再修改。")
        old = json.loads(row["config_json"])
        config = validate(db, payload)
        if old.get("practice"):
            config["practice"], config["auto_final"] = True, False
        has_entries = db.execute("SELECT 1 FROM contest_entries WHERE contest_id=? LIMIT 1", (contest_id,)).fetchone()
        if has_entries or (row["published"] and now() >= row["open_at"]):
            changed = [k for k in BENCH_FIELDS if config[k] != old[k]]
            if changed:
                raise HTTPException(409, "提交开始后，人数模式、公开地图、靶子、语言和座位轮换不能再改（会让前后提交的成绩不可比）。")
            config["setups"] = old["setups"]
        if row["final_job_id"] and any(config[k] != old[k] for k in FINAL_FIELDS):
            raise HTTPException(409, "正式评测已经开始，隐藏地图和分组轮数不能再改；可以先重新开始正式评测。")
        try:
            db.execute(
                """UPDATE contests SET slug=?,title=?,summary=?,description=?,prompt=?,rules=?,visible_at=?,open_at=?,close_at=?,published=?,config_json=?,updated_at=?
                WHERE id=?""",
                (payload.slug, payload.title.strip(), payload.summary, payload.description, payload.prompt, payload.rules, payload.visible_at,
                 payload.open_at, payload.close_at, int(payload.published), json.dumps(config), now(), contest_id),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(409, "比赛短名已被使用。")
            raise
    return {"ok": True}


@router.delete("/api/admin/contests/{contest_id}")
def delete_contest(contest_id: str, request: Request):
    admin_for(request)
    with connect() as db:
        if db.execute("SELECT 1 FROM contest_entries WHERE contest_id=? LIMIT 1", (contest_id,)).fetchone():
            raise HTTPException(409, "已经有人提交的比赛不能删除，可以取消发布。")
        db.execute("DELETE FROM contests WHERE id=?", (contest_id,))
    return {"ok": True}


@router.post("/api/admin/contests/{contest_id}/final")
def admin_start_final(contest_id: str, request: Request):
    admin_for(request)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM contests WHERE id=?", (contest_id,)).fetchone()
        if not row:
            raise HTTPException(404, "比赛不存在。")
        if row["finalized_at"]:
            raise HTTPException(409, "比赛结果已公布。")
        if now() < row["close_at"]:
            raise HTTPException(409, "提交窗口还没结束。")
        job_id, games = start_final(db, row)
    return {"job_id": job_id, "games": games}


@router.post("/api/admin/contests/{contest_id}/finalize")
def admin_finalize(contest_id: str, request: Request):
    """Publish (or re-publish, after retrying failed games) the final standings."""
    admin_for(request)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM contests WHERE id=?", (contest_id,)).fetchone()
        if not row or not row["final_job_id"]:
            raise HTTPException(409, "正式评测还没有开始。")
        if db.execute("SELECT 1 FROM matches WHERE job_id=? AND status IN ('queued','running') LIMIT 1", (row["final_job_id"],)).fetchone():
            raise HTTPException(409, "正式评测还有对局未完成。")
        finalize(db, row)
    return {"ok": True}


@router.post("/api/admin/contests/{contest_id}/retry")
def admin_retry(contest_id: str, request: Request):
    """Requeue failed final games; the results are re-published once they finish."""
    admin_for(request)
    with connect() as db:
        row = db.execute("SELECT * FROM contests WHERE id=?", (contest_id,)).fetchone()
        if not row or not row["final_job_id"]:
            raise HTTPException(409, "正式评测还没有开始。")
        count = db.execute(
            "UPDATE matches SET status='queued',max_attempts=attempts+3,error=NULL WHERE job_id=? AND status='failed'",
            (row["final_job_id"],),
        ).rowcount
        if count:
            db.execute("UPDATE contests SET finalized_at=NULL,standings_json=NULL WHERE id=?", (contest_id,))
    return {"retried": count}
