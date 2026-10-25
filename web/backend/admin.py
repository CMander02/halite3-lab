"""Single site administrator: user management, ELO corrections and submission review."""
import json
import secrets
import shutil
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from . import catalog as C
from . import settings as S
from .db import connect, now
from .security import PASSWORDS, admin_for
from .submissions import redetect, submissions

router = APIRouter()

VERSION_COLUMNS = {
    "declared_model": "TEXT", "declared_effort": "TEXT", "declared_harness": "TEXT",
    "admin_model": "TEXT", "admin_effort": "TEXT", "admin_harness": "TEXT", "admin_note": "TEXT NOT NULL DEFAULT ''",
    "detection_json": "TEXT", "trace_key": "TEXT", "trace_filename": "TEXT", "trace_size": "INTEGER", "trace_sha256": "TEXT",
    "listed": "INTEGER NOT NULL DEFAULT 1", "archived": "INTEGER NOT NULL DEFAULT 0",
}


def migrate(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
    if "is_admin" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    if "disabled_at" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN disabled_at INTEGER")
    columns = {row["name"] for row in db.execute("PRAGMA table_info(versions)")}
    for name, kind in VERSION_COLUMNS.items():
        if name not in columns:
            db.execute(f"ALTER TABLE versions ADD COLUMN {name} {kind}")
    if "default_version_id" not in {row["name"] for row in db.execute("PRAGMA table_info(bots)")}:
        db.execute("ALTER TABLE bots ADD COLUMN default_version_id TEXT")
    C.seed(db)
    ensure_admin(db)


def ensure_admin(db):
    """Exactly one administrator: the account named by HALITE_ADMIN (default cmander)."""
    db.execute("UPDATE users SET is_admin=0 WHERE is_admin=1 AND username<>?", (S.ADMIN_USERNAME,))
    db.execute("UPDATE users SET is_admin=1,disabled_at=NULL WHERE username=?", (S.ADMIN_USERNAME,))
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_single_admin ON users(is_admin) WHERE is_admin=1")


@router.get("/api/admin/overview")
def overview(request: Request):
    admin_for(request)
    with connect() as db:
        counts = dict(db.execute("SELECT status,COUNT(*) FROM matches GROUP BY status").fetchall())
        users = db.execute("SELECT COUNT(*),SUM(disabled_at IS NOT NULL) FROM users").fetchone()
        runner = db.execute("SELECT last_seen FROM runners WHERE id='local'").fetchone()
        traces = db.execute("SELECT COUNT(*),COALESCE(SUM(trace_size),0) FROM versions WHERE trace_key IS NOT NULL").fetchone()
        mismatched = 0
        for item in submissions(db, "1=1", []):
            mismatched += bool(item["attribution"]["mismatch"])
    usage = shutil.disk_usage(S.DATA)
    return {"matches": counts, "users": users[0], "disabled": users[1] or 0,
            "runner_online": bool(runner and now() - runner["last_seen"] < 20),
            "disk_free": usage.free, "disk_total": usage.total, "traces": traces[0], "trace_bytes": traces[1],
            "mismatched": mismatched}


@router.get("/api/admin/users")
def users(request: Request):
    admin_for(request)
    with connect() as db:
        rows = db.execute("""SELECT u.id,u.username,u.display_name,u.created_at,u.is_admin,u.disabled_at,u.avatar_version,
            (SELECT COUNT(*) FROM bots b WHERE b.owner_id=u.id) AS bots,
            (SELECT COUNT(*) FROM versions v JOIN bots b ON b.id=v.bot_id WHERE b.owner_id=u.id) AS versions,
            (SELECT COUNT(*) FROM matches m WHERE m.owner_id=u.id) AS matches,
            (SELECT MAX(created_at) FROM sessions s WHERE s.user_id=u.id) AS last_login,
            (SELECT COUNT(*) FROM sessions s WHERE s.user_id=u.id AND s.expires_at>?) AS sessions,
            (SELECT COUNT(*) FROM api_tokens t WHERE t.user_id=u.id AND t.expires_at>?) AS tokens
            FROM users u ORDER BY u.is_admin DESC,u.created_at""", (now(), now())).fetchall()
    return {"users": [dict(r) | {"is_admin": bool(r["is_admin"])} for r in rows]}


def target_user(db, user_id):
    row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "用户不存在。")
    if row["is_admin"]:
        raise HTTPException(400, "不能对管理员账号执行此操作。")
    return row


def revoke(db, user_id):
    db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM api_tokens WHERE user_id=?", (user_id,))


class UserPatch(BaseModel):
    disabled: bool | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=40)


@router.patch("/api/admin/users/{user_id}")
def patch_user(user_id: str, payload: UserPatch, request: Request):
    admin_for(request)
    with connect() as db:
        target_user(db, user_id)
        if payload.disabled is not None:
            db.execute("UPDATE users SET disabled_at=? WHERE id=?", (now() if payload.disabled else None, user_id))
            if payload.disabled:
                revoke(db, user_id)
                # Queued private games of a disabled account are cancelled; public evaluations keep running.
                db.execute("UPDATE matches SET status='cancelled' WHERE owner_id=? AND status='queued' AND public=0", (user_id,))
        if payload.display_name and payload.display_name.strip():
            db.execute("UPDATE users SET display_name=? WHERE id=?", (payload.display_name.strip(), user_id))
    return {"ok": True}


@router.post("/api/admin/users/{user_id}/password")
def reset_password(user_id: str, request: Request):
    admin_for(request)
    password = "-".join(secrets.token_urlsafe(5) for _ in range(3))
    hashed = PASSWORDS.hash(password)
    with connect() as db:
        target_user(db, user_id)
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (hashed, user_id))
        revoke(db, user_id)
    return {"password": password}


@router.post("/api/admin/users/{user_id}/revoke")
def revoke_sessions(user_id: str, request: Request):
    admin_for(request)
    with connect() as db:
        target_user(db, user_id)
        revoke(db, user_id)
    return {"ok": True}


@router.get("/api/admin/catalog")
def full_catalog(request: Request):
    admin_for(request)
    with connect() as db:
        data = C.load(db)
    return {kind: list(data[kind].values()) for kind in C.KINDS}


class Entry(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    vendor: str = Field(default="", max_length=60)
    region: str = Field(default="", pattern=r"^(cn|us|other|)$")
    icon: str = Field(default="", pattern=r"^[a-z0-9-]{0,40}$")
    elo_offset: float = Field(ge=-1000, le=1000)
    patterns: list[str] = []
    enabled: bool = True
    sort: int = Field(default=0, ge=0, le=10000)


@router.put("/api/admin/catalog/{kind}/{entry_id}")
def put_entry(kind: str, entry_id: str, payload: Entry, request: Request):
    admin_for(request)
    if kind not in C.KINDS or not entry_id or len(entry_id) > 40 or not entry_id.replace("-", "").replace(".", "").isalnum():
        raise HTTPException(400, "类别或 ID 无效（ID 只用小写字母、数字、点和短横线）。")
    if not C.valid_patterns(payload.patterns):
        raise HTTPException(400, "识别规则需为最多 12 条有效的正则表达式。")
    if entry_id == C.UNKNOWN and not payload.enabled:
        raise HTTPException(400, "“未知”条目不能停用。")
    with connect() as db:
        db.execute(
            """INSERT INTO catalog(kind,id,name,vendor,region,icon,elo_offset,patterns,sort,enabled) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(kind,id) DO UPDATE SET name=excluded.name,vendor=excluded.vendor,region=excluded.region,icon=excluded.icon,
            elo_offset=excluded.elo_offset,patterns=excluded.patterns,sort=excluded.sort,enabled=excluded.enabled""",
            (kind, entry_id.lower(), payload.name, payload.vendor, payload.region, payload.icon, payload.elo_offset,
             json.dumps(payload.patterns), payload.sort, int(payload.enabled)),
        )
    return {"ok": True}


@router.get("/api/admin/submissions")
def all_submissions(request: Request):
    admin_for(request)
    with connect() as db:
        return {"submissions": submissions(db, "1=1", [], admin=True)}


class Attribution(BaseModel):
    model: str | None = None
    effort: str | None = None
    harness: str | None = None
    note: str = Field(default="", max_length=500)


@router.put("/api/admin/versions/{version_id}/attribution")
def set_attribution(version_id: str, payload: Attribution, request: Request):
    admin_for(request)
    with connect() as db:
        catalog = C.load(db)
        if not db.execute("SELECT 1 FROM versions v JOIN bots b ON b.id=v.bot_id WHERE v.id=? AND b.builtin=0", (version_id,)).fetchone():
            raise HTTPException(404, "版本不存在。")
        values = {}
        for kind in C.KINDS:
            value = getattr(payload, kind) or None
            if value and value not in catalog[kind]:
                raise HTTPException(400, f"未知的{kind}：{value}")
            values[kind] = value
        db.execute("UPDATE versions SET admin_model=?,admin_effort=?,admin_harness=?,admin_note=? WHERE id=?",
                   (values["model"], values["effort"], values["harness"], payload.note, version_id))
    return {"ok": True}


@router.post("/api/admin/versions/{version_id}/redetect")
def run_redetect(version_id: str, request: Request):
    admin_for(request)
    with connect() as db:
        result = redetect(db, version_id)
    if result is None:
        raise HTTPException(404, "这个版本没有对话轨迹。")
    return {"detection": result}
