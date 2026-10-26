"""Submissions: catalog, conversation traces, attribution, version management and the ELO board."""
import gzip
import hashlib
import json
import re
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import catalog as C
from . import settings as S
from .db import connect
from .detect import detect, unpack
from .rating import attribution, board
from .security import user_for

router = APIRouter()


def prepare_trace(data, filename):
    """Parse and detect an uploaded trace (CPU-bound; call from a worker thread)."""
    text = unpack(data, filename)
    with connect() as db:
        result = detect(C.load(db), text)
    raw = text.encode()
    packed = data if data[:2] == b"\x1f\x8b" else gzip.compress(raw, 6)
    return packed, {
        "trace_filename": filename[:120],
        "trace_size": len(raw),
        "trace_sha256": hashlib.sha256(raw).hexdigest(),
        "detection_json": json.dumps(result, ensure_ascii=False),
    }


def redetect(db, version_id):
    row = db.execute("SELECT trace_key,trace_filename FROM versions WHERE id=?", (version_id,)).fetchone()
    if not row or not row["trace_key"] or not (S.DATA / row["trace_key"]).is_file():
        return None
    text = unpack((S.DATA / row["trace_key"]).read_bytes(), row["trace_filename"] or "")
    result = detect(C.load(db), text)
    db.execute("UPDATE versions SET detection_json=? WHERE id=?", (json.dumps(result, ensure_ascii=False), version_id))
    return result


def ranked_status(db, version_id):
    job = db.execute("SELECT id,config_json FROM jobs WHERE kind='ranked' AND candidate_id=?", (version_id,)).fetchone()
    if not job:
        return None
    counts = dict(db.execute("SELECT status,COUNT(*) FROM matches WHERE job_id=? GROUP BY status", (job["id"],)).fetchall())
    total = sum(counts.values())
    item = {"job_id": job["id"], "counts": counts, "total": total, "complete": counts.get("complete", 0), "tier": None,
            "season": json.loads(job["config_json"]).get("season")}
    if total and counts.get("complete") == total:
        wins = 0
        for game in db.execute("SELECT seat_json,result_json FROM matches WHERE job_id=?", (job["id"],)):
            seats = json.loads(game["seat_json"])
            index = next(i for i, s in enumerate(seats) if s["id"] == version_id)
            wins += json.loads(game["result_json"])["stats"][str(index)]["rank"] == 1
        rate = wins / total
        item.update(wins=wins, win_rate=rate, tier="S" if rate >= 0.75 else "A" if rate >= 0.5 else "B" if rate >= 0.25 else "C")
    return item


SUBMISSION_SQL = """SELECT v.*,b.name AS bot_name,b.owner_id,b.default_version_id,u.username,u.display_name AS author
    FROM versions v JOIN bots b ON b.id=v.bot_id LEFT JOIN users u ON u.id=b.owner_id WHERE b.builtin=0 AND {where}
    ORDER BY v.created_at DESC,v.rowid DESC"""


def submissions(db, where, params, admin=False):
    catalog = C.load(db)
    elo = {e["version_id"]: e for e in board(db, include_hidden=True)}
    result = []
    for row in db.execute(SUBMISSION_SQL.format(where=where), params):
        entry = elo.get(row["id"])
        item = {
            "id": row["id"], "bot_id": row["bot_id"], "bot_name": row["bot_name"], "version": row["version"],
            "language": row["language"], "filename": row["filename"], "size": row["size"], "sha256": row["sha256"],
            "notes": row["notes"], "created_at": row["created_at"], "listed": bool(row["listed"]),
            "archived": bool(row["archived"]), "is_default": row["default_version_id"] == row["id"],
            "author": row["author"], "author_id": row["owner_id"], "username": row["username"],
            "trace": {"filename": row["trace_filename"], "size": row["trace_size"], "sha256": row["trace_sha256"]} if row["trace_key"] else None,
            "detection": json.loads(row["detection_json"]) if row["detection_json"] else None,
            "attribution": attribution(row, catalog),
            "ranked": ranked_status(db, row["id"]),
            "elo": {key: entry[key] for key in ("elo", "elo_sd", "adjusted_elo", "correction", "rank", "games", "wins", "win_rate")} if entry else None,
        }
        if admin:
            item["admin_note"] = row["admin_note"]
        result.append(item)
    return result


@router.get("/api/catalog")
def get_catalog():
    with connect() as db:
        data = C.load(db, enabled_only=True)
    return {kind: [{k: v for k, v in e.items() if k not in ("patterns", "kind")} for e in data[kind].values()] for kind in C.KINDS}


@router.get("/api/leaderboard/elo")
def elo_board():
    with connect() as db:
        entries = board(db)
    for entry in entries:
        if entry["attribution"]:
            entry["attribution"] = {k: {"value": v["value"], "offset": v["offset"], "source": v["source"]} if isinstance(v, dict) else v
                                    for k, v in entry["attribution"].items()}
    return {"entries": entries, "anchor": 1500}


@router.get("/api/me/submissions")
def my_submissions(request: Request):
    user = user_for(request)
    with connect() as db:
        return {"submissions": submissions(db, "b.owner_id=?", [user["id"]])}


def owned_version(db, version_id, user):
    row = db.execute(
        "SELECT v.*,b.owner_id FROM versions v JOIN bots b ON b.id=v.bot_id WHERE v.id=?", (version_id,)
    ).fetchone()
    if not row or (row["owner_id"] != user["id"] and not user["is_admin"]):
        raise HTTPException(404, "版本不存在或无权访问。")
    return row


class VersionPatch(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)
    listed: bool | None = None
    archived: bool | None = None


@router.patch("/api/versions/{version_id}")
def patch_version(version_id: str, payload: VersionPatch, request: Request):
    user = user_for(request)
    with connect() as db:
        row = owned_version(db, version_id, user)
        if row["owner_id"] != user["id"]:
            raise HTTPException(404, "版本不存在或无权访问。")
        for column in ("notes", "listed", "archived"):
            value = getattr(payload, column)
            if value is not None:
                db.execute(f"UPDATE versions SET {column}=? WHERE id=?", (int(value) if isinstance(value, bool) else value, version_id))
        if payload.archived:
            db.execute("UPDATE bots SET default_version_id=NULL WHERE id=? AND default_version_id=?", (row["bot_id"], version_id))
    return {"ok": True}


class BotPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=500)
    default_version_id: str | None = None
    clear_default: bool = False


@router.patch("/api/bots/{bot_id}")
def patch_bot(bot_id: str, payload: BotPatch, request: Request):
    user = user_for(request)
    with connect() as db:
        if not db.execute("SELECT 1 FROM bots WHERE id=? AND owner_id=?", (bot_id, user["id"])).fetchone():
            raise HTTPException(404, "Bot 不存在或无权访问。")
        if payload.default_version_id:
            if not db.execute("SELECT 1 FROM versions WHERE id=? AND bot_id=? AND archived=0", (payload.default_version_id, bot_id)).fetchone():
                raise HTTPException(400, "默认版本必须是这个 Bot 未归档的版本。")
            db.execute("UPDATE bots SET default_version_id=? WHERE id=?", (payload.default_version_id, bot_id))
        if payload.clear_default:
            db.execute("UPDATE bots SET default_version_id=NULL WHERE id=?", (bot_id,))
        if payload.description is not None:
            db.execute("UPDATE bots SET description=? WHERE id=?", (payload.description, bot_id))
        if payload.name is not None and payload.name.strip():
            try:
                db.execute("UPDATE bots SET name=? WHERE id=?", (payload.name.strip(), bot_id))
            except Exception:
                raise HTTPException(409, "已有同名 Bot。")
    return {"ok": True}


@router.get("/api/versions/{version_id}/trace")
def download_trace(version_id: str, request: Request):
    user = user_for(request)
    with connect() as db:
        row = owned_version(db, version_id, user)
    if not row["trace_key"] or not (S.DATA / row["trace_key"]).is_file():
        raise HTTPException(404, "这个版本没有上传对话轨迹。")
    name = re.sub(r"[^A-Za-z0-9._-]", "_", (row["trace_filename"] or "trace.jsonl").removesuffix(".gz"))[:80]
    return Response((S.DATA / row["trace_key"]).read_bytes(), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{version_id[:8]}-{name}.gz"'})


@router.get("/api/bots/{bot_id}/profile")
def bot_profile(bot_id: str, request: Request):
    """One bot: its versions in order with global ELO, benchmark tier and contest results.

    The owner and the admin see every version; everyone else sees the versions that
    are on public record (listed and rated globally, or entered in a contest)."""
    from .contests import compute, current_entries, status as contest_status

    user = user_for(request, False)
    with connect() as db:
        bot = db.execute(
            "SELECT b.*,u.display_name AS author,u.username FROM bots b LEFT JOIN users u ON u.id=b.owner_id WHERE b.id=?", (bot_id,)
        ).fetchone()
        if not bot:
            raise HTTPException(404, "Bot 不存在。")
        owner = bool(user and (user["id"] == bot["owner_id"] or user["is_admin"]))
        catalog = C.load(db)
        elo = {e["version_id"]: e for e in board(db, include_hidden=True)}
        rows = db.execute("SELECT * FROM versions WHERE bot_id=? ORDER BY created_at,rowid", (bot_id,)).fetchall()
        entries = {}
        for e in db.execute(
            """SELECT e.*,c.slug,c.title,c.finalized_at FROM contest_entries e JOIN contests c ON c.id=e.contest_id
            JOIN versions v ON v.id=e.version_id WHERE v.bot_id=? ORDER BY e.created_at""", (bot_id,)
        ):
            entries.setdefault(e["version_id"], []).append(e)
        tables, versions = {}, []
        for row in rows:
            rated = elo.get(row["id"])
            public = bool(bot["builtin"]) or (bool(row["listed"]) and not row["archived"] and (rated or row["id"] in entries))
            if not owner and not public:
                continue
            contests = []
            for e in entries.get(row["id"], []):
                if e["contest_id"] not in tables:
                    contest = db.execute("SELECT * FROM contests WHERE id=?", (e["contest_id"],)).fetchone()
                    frozen = json.loads(contest["standings_json"]) if contest["standings_json"] else None
                    tables[e["contest_id"]] = (contest, frozen["bench"] if frozen else compute(db, contest, "bench"),
                                               frozen["final"] if frozen else None,
                                               current_entries(db, contest))
                contest, bench, final, current = tables[e["contest_id"]]
                pick = lambda table: next(({k: r[k] for k in ("elo", "adjusted_elo", "games", "win_rate", "rank")}
                                           for r in table.get("overall", []) if r["version_id"] == row["id"]), None)
                contests.append({"contest_id": contest["id"], "slug": contest["slug"], "title": contest["title"],
                                 "status": contest_status(contest), "seq": e["seq"], "created_at": e["created_at"],
                                 "current": e["id"] in current,
                                 "bench": pick(bench), "final": pick(final) if final else None})
            attr = None if bot["builtin"] else attribution(row, catalog)
            versions.append({
                "id": row["id"], "version": row["version"], "language": row["language"], "notes": row["notes"],
                "created_at": row["created_at"], "archived": bool(row["archived"]), "listed": bool(row["listed"]),
                "is_default": bot["default_version_id"] == row["id"],
                "attribution": {k: {"value": attr[k]["value"], "offset": attr[k]["offset"], "source": attr[k]["source"]} for k in C.KINDS}
                | {"correction": attr["correction"], "mismatch": attr["mismatch"]} if attr else None,
                "ranked": ranked_status(db, row["id"]) if owner or public else None,
                "elo": {key: rated[key] for key in ("elo", "elo_sd", "adjusted_elo", "correction", "rank", "games", "wins", "win_rate", "avg_rank")} if rated else None,
                "contests": contests,
            })
        if not versions and not owner:
            raise HTTPException(404, "这个 Bot 还没有公开记录。")
    return {
        "bot": {"id": bot["id"], "name": bot["name"], "description": bot["description"], "builtin": bool(bot["builtin"]),
                "author": bot["author"], "author_id": bot["owner_id"], "username": bot["username"], "created_at": bot["created_at"],
                "owned": bool(user and user["id"] == bot["owner_id"]), "default_version_id": bot["default_version_id"]},
        "versions": versions,
    }
