import asyncio
from contextlib import asynccontextmanager
import gzip
import hashlib
import html
import json
import logging
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import uuid
from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    Response,
    UploadFile,
    File,
    Form,
    Query,
)
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from . import settings as S
from .db import connect, initialize, now
from . import admin, contests, profiles, submissions
from .security import (
    COOKIE,
    PASSWORDS,
    csrf,
    digest,
    rate_limit,
    set_session,
    user_for,
    verify_password,
)
from .storage import disk_check, validate_archive
from .catalog import load as load_catalog
from .submissions import prepare_trace
import zipfile
from .scheduler import create_job, get_match, job_dict, match_dict, version_info

AUTH_LIMIT = threading.BoundedSemaphore(2)
UPLOAD_SLOTS = asyncio.Semaphore(2)
DUMMY_HASH = PASSWORDS.hash("dummy-account-verification-only")
log = logging.getLogger("halite3")


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(
    title="Halite 3 Arena API",
    version="1.0",
    docs_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.include_router(profiles.router)
app.include_router(admin.router)
app.include_router(submissions.router)
app.include_router(contests.router)


@app.middleware("http")
async def protection(request, call_next):
    length = request.headers.get("content-length")
    if request.method in ("POST", "PUT", "PATCH"):
        if length is None:
            return JSONResponse(
                {"detail": "请使用带 Content-Length 的请求。"}, status_code=411
            )
        try:
            maximum = (
                S.MAX_UPLOAD + S.MAX_TRACE + 131072
                if request.headers.get("content-type", "").startswith("multipart/")
                else 65536
            )
            if int(length) > maximum or int(length) < 0:
                return JSONResponse({"detail": "请求内容过大。"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Content-Length 无效。"}, status_code=400)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        try:
            csrf(request)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://cloudflareinsights.com https://*.cloudflareinsights.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api/") and not request.url.path.startswith(
        "/api/avatars/"
    ):
        response.headers["Cache-Control"] = "no-store"
    return response


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(default="", max_length=40)


class BotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=500)


class TestCreate(BaseModel):
    name: str = Field(default="私人循环赛", min_length=1, max_length=80)
    version_ids: list[str] = []
    bot_ids: list[str] = []
    modes: list[int] = [2]
    seeds: list[int] = [11, 29, 47]
    rotate_seats: bool = False


class TokenCreate(BaseModel):
    name: str = Field(default="CLI", min_length=1, max_length=40)


@app.get("/api/docs", include_in_schema=False)
def api_docs():
    rows = []
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method, operation in operations.items():
            if method in ("get", "post", "put", "delete", "patch"):
                rows.append(
                    "<tr><td>"
                    + method.upper()
                    + "</td><td><code>"
                    + html.escape(path)
                    + "</code></td><td>"
                    + html.escape(operation.get("summary", ""))
                    + "</td></tr>"
                )
    content = (
        """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Halite 3 API 文档</title><style>body{font:14px/1.8 system-ui,sans-serif;color:#243b46;background:#f7f8fa;margin:0;padding:24px}main{max-width:1060px;margin:auto}a{color:#087f65}h1{font-size:28px}.scroll{overflow:auto;background:white;border:1px solid #e2e8ed;border-radius:7px}table{border-collapse:collapse;width:100%;text-align:left;white-space:nowrap}th,td{padding:12px 16px;border-bottom:1px solid #edf1f4}code,pre{font:12px/1.8 monospace}pre{overflow:auto;padding:18px;background:#edf4f1;border-radius:6px}p{color:#6b7f88}</style><main><a href="/">← 返回 Halite 3 Arena</a><h1>后端 API</h1><p>使用网页账号或 API Token 管理自己的 Bot 与测试。源码、私人任务和日志按账号授权。写操作需要同源 Cookie 或 Bearer Token。</p><p><a href="/api/openapi.json">下载完整 OpenAPI JSON</a> · <a href="https://github.com/CMander02/halite3-lab/tree/main/web">CLI 与 Bot 协议说明</a></p><pre>python3 web/client.py login\npython3 web/client.py upload MyBot.cpp --name my-cpp --version 1.0 --trace session.jsonl --model claude-opus-5-5 --effort high --harness claude-code --rank\npython3 web/client.py test --bots BOT_ID,builtin-baseline --seeds 11,29,47</pre><div class="scroll"><table><thead><tr><th>方法</th><th>路径</th><th>操作</th></tr></thead><tbody>"""
        + "".join(rows)
        + """</tbody></table></div></main></html>"""
    )
    return HTMLResponse(content)


@app.get("/api/health")
def health():
    with connect() as db:
        runner = db.execute("SELECT last_seen FROM runners WHERE id='local'").fetchone()
    return {
        "ok": True,
        "runner_online": bool(runner and now() - runner["last_seen"] < 20),
        "protocol": "halite3-lab-v1",
        "upload_limit": S.MAX_UPLOAD,
        "retention_days": S.RETENTION_DAYS,
    }


@app.get("/api/session")
def session(request: Request):
    return {"user": user_for(request, False)}


@app.post("/api/auth/register", status_code=201)
def register(payload: Credentials, request: Request, response: Response):
    username = payload.username.lower().strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,31}", username):
        raise HTTPException(
            400, "用户名使用 3 至 32 位小写字母、数字、下划线或短横线。"
        )
    rate_limit(request, "register", 20, 3600)
    with AUTH_LIMIT:
        hashed = PASSWORDS.hash(payload.password)
    user_id = str(uuid.uuid4())
    try:
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO users(id,username,display_name,password_hash,created_at,avatar_pattern) VALUES(?,?,?,?,?,?)",
                (
                    user_id,
                    username,
                    payload.display_name.strip() or username,
                    hashed,
                    now(),
                    profiles.new_pattern(db),
                ),
            )
            admin.ensure_admin(db)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "用户名已被使用。")
    set_session(response, user_id, request.cookies.get(COOKIE))
    return {
        "user": {
            "id": user_id,
            "username": username,
            "display_name": payload.display_name.strip() or username,
            "avatar_version": 0,
        }
    }


@app.post("/api/auth/login")
def login(payload: Credentials, request: Request, response: Response):
    username = payload.username.lower().strip()
    rate_limit(request, "login-ip", 20, 600)
    rate_limit(request, "login-user", 8, 600, username)
    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
    with AUTH_LIMIT:
        valid = verify_password(
            user["password_hash"] if user else DUMMY_HASH, payload.password
        )
    if not valid or not user:
        raise HTTPException(401, "用户名或密码不正确。")
    if user["disabled_at"]:
        raise HTTPException(403, "账号已被管理员停用。")
    set_session(response, user["id"], request.cookies.get(COOKIE))
    return {
        "user": {
            key: user[key]
            for key in ["id", "username", "display_name", "avatar_version"]
        }
    }


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    value = request.cookies.get(COOKIE)
    if value:
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(value),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/tokens")
def tokens(request: Request):
    user = user_for(request)
    with connect() as db:
        return {
            "tokens": [
                dict(r)
                for r in db.execute(
                    "SELECT id,name,created_at,expires_at FROM api_tokens WHERE user_id=? ORDER BY created_at DESC",
                    (user["id"],),
                )
            ]
        }


@app.post("/api/tokens", status_code=201)
def create_token(payload: TokenCreate, request: Request):
    user = user_for(request)
    value = "h3_" + secrets.token_urlsafe(32)
    token_id = str(uuid.uuid4())
    with connect() as db:
        if (
            db.execute(
                "SELECT COUNT(*) FROM api_tokens WHERE user_id=?", (user["id"],)
            ).fetchone()[0]
            >= 10
        ):
            raise HTTPException(409, "最多保存 10 个 API Token，请先撤销旧 Token。")
        db.execute(
            "INSERT INTO api_tokens(id,token_hash,user_id,name,created_at,expires_at) VALUES(?,?,?,?,?,?)",
            (
                token_id,
                digest(value),
                user["id"],
                payload.name,
                now(),
                now() + 30 * 86400,
            ),
        )
    return {"id": token_id, "token": value, "expires_at": now() + 30 * 86400}


@app.delete("/api/tokens/{token_id}")
def revoke_token(token_id: str, request: Request):
    user = user_for(request)
    with connect() as db:
        db.execute(
            "DELETE FROM api_tokens WHERE id=? AND user_id=?", (token_id, user["id"])
        )
    return {"ok": True}


def bot_model(bot):
    """Model behind a bot, for its icon: the default (else latest active) version's
    admin-confirmed model, then a confident detection, then the declaration,
    then any detection. None when nothing is known."""
    versions = bot["versions"]
    head = next((v for v in versions if v["id"] == bot.get("default_version_id")), None)
    head = head or next((v for v in versions if not v["archived"]), None) or (versions[0] if versions else None)
    if not head:
        return None
    detection = json.loads(head["detection_json"]) if head["detection_json"] else {}
    detected = detection.get("model") if detection.get("model") != "unknown" else None
    confident = detection.get("model_confidence") in ("medium", "high")
    declared = head["declared_model"] if head["declared_model"] != "unknown" else None
    return head["admin_model"] or (detected if confident else None) or declared or detected


@app.get("/api/bots")
def bots(request: Request):
    user = user_for(request, False)
    uid = user["id"] if user else None
    with connect() as db:
        rows = db.execute(
            "SELECT b.*,u.display_name AS author FROM bots b LEFT JOIN users u ON u.id=b.owner_id WHERE b.builtin=1 OR b.owner_id=? ORDER BY b.builtin,b.created_at DESC",
            (uid,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["owned"] = item.pop("owner_id") == uid and uid is not None
            item["versions"] = [
                dict(v)
                for v in db.execute(
                    "SELECT id,version,sha256,filename,size,notes,created_at,language,listed,archived,declared_model,declared_effort,declared_harness,trace_key IS NOT NULL AS has_trace,admin_model,detection_json FROM versions WHERE bot_id=? ORDER BY created_at DESC,rowid DESC",
                    (item["id"],),
                )
            ]
            item["model"] = bot_model(item)
            for v in item["versions"]:
                del v["admin_model"], v["detection_json"]
            result.append(item)
    return {"bots": result}


@app.post("/api/bots", status_code=201)
def create_bot(payload: BotCreate, request: Request):
    user = user_for(request)
    rate_limit(request, "bot-create", 30, 3600, user["id"])
    if not payload.name.strip():
        raise HTTPException(400, "请输入 Bot 名称。")
    bid = str(uuid.uuid4())
    try:
        with connect() as db:
            if (
                db.execute(
                    "SELECT COUNT(*) FROM bots WHERE owner_id=?", (user["id"],)
                ).fetchone()[0]
                >= 30
            ):
                raise HTTPException(409, "每个用户最多创建 30 个 Bot。")
            db.execute(
                "INSERT INTO bots(id,owner_id,name,description,created_at) VALUES(?,?,?,?,?)",
                (bid, user["id"], payload.name.strip(), payload.description, now()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "已有同名 Bot。")
    return {"id": bid}


@app.post("/api/bots/{bot_id}/versions", status_code=201)
async def upload_version(
    bot_id: str,
    request: Request,
    file: UploadFile = File(...),
    version: str = Form(...),
    notes: str = Form(""),
    trace: UploadFile | None = File(None),
    model: str = Form("unknown"),
    effort: str = Form("unknown"),
    harness: str = Form("unknown"),
    rank: bool = Form(False),
):
    async with UPLOAD_SLOTS:
        result = await store_version(bot_id, request, file, version, notes, trace, {"model": model, "effort": effort, "harness": harness})
    if rank:
        user = user_for(request)
        try:
            result["ranked_job_id"] = await run_in_threadpool(
                create_job, user["id"], "排名评测", [result["id"]], [2], [11, 29, 47], True, True
            )
        except HTTPException as exc:
            result["ranked_error"] = exc.detail
    return result


async def read_limited(file, limit, message):
    data = bytearray()
    while chunk := await file.read(65536):
        if len(data) + len(chunk) > limit:
            raise HTTPException(413, message)
        data.extend(chunk)
    return bytes(data)


async def store_version(bot_id, request, file, version, notes, trace=None, declared=None):
    user = user_for(request)
    declared = declared or {}
    rate_limit(request, "upload", 20, 3600, user["id"])
    disk_check()
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,31}", version)
        or len(notes) > 2000
    ):
        raise HTTPException(
            400, "版本标识使用 1 至 32 位字母、数字、点、短横线或下划线。"
        )
    with connect() as db:
        if not db.execute(
            "SELECT id FROM bots WHERE id=? AND owner_id=?", (bot_id, user["id"])
        ).fetchone():
            raise HTTPException(404, "Bot 不存在或无权访问。")
        catalog = load_catalog(db, enabled_only=True)
    for kind in ("model", "effort", "harness"):
        if declared.get(kind, "unknown") not in catalog[kind]:
            raise HTTPException(400, f"请选择有效的{ {'model': '模型', 'effort': '推理强度', 'harness': '平台'}[kind] }。")
    data = await read_limited(file, S.MAX_UPLOAD, "文件不能超过 5 MiB。")
    if not data:
        raise HTTPException(400, "文件不能为空。")
    trace_data = await read_limited(trace, S.MAX_TRACE, "对话轨迹不能超过 16 MiB（可先 gzip 压缩）。") if trace else b""
    if S.REQUIRE_TRACE and not trace_data:
        raise HTTPException(400, "请同时上传生成这个版本的对话轨迹（如 Claude Code / Codex 的会话 JSONL）。")
    prepared = None
    if trace_data:
        try:
            prepared = await run_in_threadpool(prepare_trace, trace_data, Path(trace.filename or "trace.jsonl").name)
        except (ValueError, OSError, zipfile.BadZipFile, EOFError) as exc:
            raise HTTPException(400, f"对话轨迹无法读取：{str(exc)[:160]}")
    filename = Path(file.filename or "bot.py").name
    try:
        language = await run_in_threadpool(validate_archive, bytes(data), filename)
    except Exception as exc:
        raise HTTPException(400, f"Bot 文件无效：{str(exc)[:180]}")
    vid = str(uuid.uuid4())
    extension = (
        ".zip"
        if filename.lower().endswith(".zip")
        else ".py"
        if language == "python"
        else ".cpp"
    )
    directory = S.DATA / "users" / user["id"] / "bots" / bot_id / "versions" / vid
    directory.mkdir(parents=True, mode=0o700)
    key = str((directory / ("source" + extension)).relative_to(S.DATA))
    path = S.DATA / key
    try:
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count, size = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(v.size),0) FROM versions v JOIN bots b ON b.id=v.bot_id WHERE b.owner_id=?",
                (user["id"],),
            ).fetchone()
            if count >= 200 or size + len(data) > S.MAX_USER_UPLOAD:
                raise HTTPException(409, "已达到 200 个版本或 256 MiB 源码配额。")
            path.write_bytes(data)
            db.execute(
                "INSERT INTO versions(id,bot_id,version,object_key,sha256,filename,size,notes,created_at,language,declared_model,declared_effort,declared_harness) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    vid,
                    bot_id,
                    version,
                    key,
                    hashlib.sha256(data).hexdigest(),
                    filename,
                    len(data),
                    notes,
                    now(),
                    language,
                    declared.get("model", "unknown"),
                    declared.get("effort", "unknown"),
                    declared.get("harness", "unknown"),
                ),
            )
            if prepared:
                packed, columns = prepared
                (directory / "trace.gz").write_bytes(packed)
                columns["trace_key"] = str((directory / "trace.gz").relative_to(S.DATA))
                db.execute(
                    "UPDATE versions SET " + ",".join(f"{k}=?" for k in columns) + " WHERE id=?",
                    [*columns.values(), vid],
                )
            latest = directory.parent.parent / "latest"
            temporary = directory.parent.parent / f".latest-{vid}"
            temporary.symlink_to(Path("versions") / vid)
            temporary.replace(latest)
    except BaseException as exc:
        path.unlink(missing_ok=True)
        (directory / "trace.gz").unlink(missing_ok=True)
        if isinstance(exc, sqlite3.IntegrityError):
            raise HTTPException(409, "此版本号已存在，版本内容不可覆盖。")
        raise
    return {
        "id": vid,
        "version": version,
        "language": language,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


@app.get("/api/versions/{version_id}/source")
def download_source(version_id: str, request: Request):
    user = user_for(request, False)
    with connect() as db:
        row = version_info(db, version_id, user["id"] if user else None)
    return FileResponse(
        S.DATA / row["object_key"],
        filename=row["filename"],
        media_type="application/octet-stream",
    )


@app.post("/api/tests", status_code=201)
def new_test(payload: TestCreate, request: Request):
    user = user_for(request)
    rate_limit(request, "test-create", 10, 3600, user["id"])
    version_ids = payload.version_ids
    if payload.bot_ids:
        if (
            version_ids
            or len(payload.bot_ids) > 10
            or len(set(payload.bot_ids)) != len(payload.bot_ids)
        ):
            raise HTTPException(400, "bot_ids 与 version_ids 二选一，且不能重复。")
        version_ids = []
        with connect() as db:
            for bot_id in payload.bot_ids:
                # The bot's default version if one is pinned, else its latest non-archived version.
                row = db.execute(
                    "SELECT v.id FROM versions v JOIN bots b ON b.id=v.bot_id WHERE b.id=? AND (b.owner_id=? OR b.builtin=1) AND v.archived=0 ORDER BY v.id=COALESCE(b.default_version_id,'') DESC,v.created_at DESC,v.rowid DESC LIMIT 1",
                    (bot_id, user["id"]),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "Bot 不存在、无版本或无权访问。")
                version_ids.append(row["id"])
    jid = create_job(
        user["id"],
        payload.name,
        version_ids,
        payload.modes,
        payload.seeds,
        payload.rotate_seats,
    )
    return {"id": jid}


@app.post("/api/versions/{version_id}/rank", status_code=201)
def ranked(version_id: str, request: Request):
    user = user_for(request)
    rate_limit(request, "rank-create", 10, 3600, user["id"])
    jid = create_job(
        user["id"], "排名评测", [version_id], [2], [11, 29, 47], True, True
    )
    return {"id": jid}


@app.get("/api/tests")
def jobs(request: Request, offset: int = Query(0, ge=0, le=100000)):
    user = user_for(request)
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM jobs WHERE owner_id=? ORDER BY created_at DESC,rowid DESC LIMIT 30 OFFSET ?",
            (user["id"], offset),
        ).fetchall()
        return {"jobs": [job_dict(db, row) for row in rows]}


@app.get("/api/tests/{job_id}")
def job_detail(job_id: str, request: Request):
    user = user_for(request)
    with connect() as db:
        row = db.execute(
            "SELECT * FROM jobs WHERE id=? AND owner_id=?", (job_id, user["id"])
        ).fetchone()
        if not row:
            raise HTTPException(404, "任务不存在或无权访问。")
        item = job_dict(db, row)
        item["matches"] = [
            match_dict(r)
            for r in db.execute(
                "SELECT m.*,j.kind,j.name AS job_name FROM matches m JOIN jobs j ON j.id=m.job_id WHERE m.job_id=? ORDER BY m.created_at,m.rowid",
                (job_id,),
            )
        ]
    return item


@app.post("/api/tests/{job_id}/retry")
def retry_job(job_id: str, request: Request):
    user = user_for(request)
    with connect() as db:
        if not db.execute(
            "SELECT 1 FROM jobs WHERE id=? AND owner_id=?", (job_id, user["id"])
        ).fetchone():
            raise HTTPException(404, "任务不存在或无权访问。")
        count = db.execute(
            "UPDATE matches SET status='queued',max_attempts=attempts+3,error=NULL WHERE job_id=? AND status='failed'",
            (job_id,),
        ).rowcount
    return {"retried": count}


@app.post("/api/tests/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    user = user_for(request)
    with connect() as db:
        if not db.execute(
            "SELECT 1 FROM jobs WHERE id=? AND owner_id=?", (job_id, user["id"])
        ).fetchone():
            raise HTTPException(404, "任务不存在或无权访问。")
        # Claimed games finish so results are not lost; queued games are cancelled.
        db.execute(
            "UPDATE matches SET status='cancelled' WHERE job_id=? AND status='queued'",
            (job_id,),
        )
    return {"ok": True}


@app.get("/api/matches")
def matches(
    request: Request,
    mode: int | None = None,
    version: str | None = None,
    offset: int = Query(0, ge=0, le=100000),
    scope: str = "all",
):
    user = user_for(request, False)
    uid = user["id"] if user else None
    if scope == "mine" and not user:
        raise HTTPException(401, "请先登录。")
    where = "m.owner_id=?" if scope == "mine" else "(m.public=1 OR m.owner_id=?)"
    params = [uid]
    if mode in (2, 4, 8):
        where += " AND m.mode=?"
        params.append(mode)
    if version:
        where += " AND EXISTS (SELECT 1 FROM json_each(m.seat_json) s WHERE json_extract(s.value,'$.id')=?)"
        params.append(version)
    with connect() as db:
        total = db.execute(
            f"SELECT COUNT(*) FROM matches m WHERE {where}", params
        ).fetchone()[0]
        rows = db.execute(
            f"SELECT m.*,j.kind,j.name AS job_name FROM matches m JOIN jobs j ON j.id=m.job_id WHERE {where} ORDER BY m.created_at DESC,m.rowid DESC LIMIT 30 OFFSET ?",
            params + [offset],
        ).fetchall()
    return {"matches": [match_dict(r) for r in rows], "total": total}


@app.get("/api/matches/{match_id}")
def match_detail(match_id: str, request: Request):
    user = user_for(request, False)
    with connect() as db:
        row = get_match(db, match_id, user["id"] if user else None)
        item = match_dict(row)
        item["can_view_logs"] = bool(user and row["owner_id"] == user["id"])
        item["players"] = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM match_players WHERE match_id=? ORDER BY seat",
                (match_id,),
            )
        ]
        item["attempt_history"] = [
            dict(r)
            for r in db.execute(
                "SELECT number,status,error,created_at,finished_at FROM attempts WHERE match_id=? ORDER BY number",
                (match_id,),
            )
        ]
    return item


@app.get("/api/matches/{match_id}/replay")
def replay(match_id: str, request: Request, download: bool = False):
    user = user_for(request, False)
    with connect() as db:
        row = get_match(db, match_id, user["id"] if user else None)
    if not row["replay_key"] or not (S.DATA / row["replay_key"]).is_file():
        raise HTTPException(404, "回放尚未生成或已超过保留期限。")
    path = S.DATA / row["replay_key"]
    headers = {"Content-Encoding": "gzip", "Vary": "Accept-Encoding"}
    if download:
        headers["Content-Disposition"] = (
            f'attachment; filename="halite3-{match_id}.hlt"'
        )
    return FileResponse(path, media_type="application/json", headers=headers)


@app.get("/api/matches/{match_id}/logs")
def match_logs(match_id: str, request: Request):
    user = user_for(request)
    with connect() as db:
        row = get_match(db, match_id, user["id"])
        if row["owner_id"] != user["id"]:
            raise HTTPException(404, "日志不存在或无权访问。")
    path = S.DATA / "logs" / f"{match_id}.json"
    if not path.exists():
        raise HTTPException(404, "日志尚未生成。")
    return FileResponse(path, media_type="application/json")


@app.get("/api/leaderboard")
def leaderboard():
    with connect() as db:
        rows = db.execute(
            "SELECT j.*,v.version,b.name AS bot_name,u.display_name AS author FROM jobs j JOIN versions v ON v.id=j.candidate_id JOIN bots b ON b.id=v.bot_id JOIN users u ON u.id=j.owner_id WHERE j.kind='ranked' ORDER BY j.created_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            config = json.loads(row["config_json"])
            if config.get("season") != S.SEASON:
                continue
            games = db.execute(
                "SELECT seat_json,result_json,status FROM matches WHERE job_id=?",
                (row["id"],),
            ).fetchall()
            if len(games) != 12 or any(g["status"] != "complete" for g in games):
                continue
            wins = 0
            score = 0
            for game in games:
                seats = json.loads(game["seat_json"])
                index = next(
                    i for i, s in enumerate(seats) if s["id"] == row["candidate_id"]
                )
                stats = json.loads(game["result_json"])["stats"][str(index)]
                wins += stats["rank"] == 1
                score += stats["score"]
            rate = wins / 12
            result.append(
                {
                    "version_id": row["candidate_id"],
                    "bot_name": row["bot_name"],
                    "version": row["version"],
                    "author": row["author"],
                    "author_id": row["owner_id"],
                    "games": 12,
                    "wins": wins,
                    "win_rate": rate,
                    "mean_score": score / 12,
                    "tier": "S"
                    if rate >= 0.75
                    else "A"
                    if rate >= 0.5
                    else "B"
                    if rate >= 0.25
                    else "C",
                    "job_id": row["id"],
                }
            )
    result.sort(key=lambda r: (-r["win_rate"], -r["mean_score"], r["bot_name"]))
    return {
        "season": S.SEASON,
        "entries": result,
        "required_games": 12,
        "seeds": [11, 29, 47],
    }


DIST = S.ROOT / "dist"
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "接口不存在。")
    if (
        path in ("favicon.svg", "sample-python.zip", "sample-cpp.zip")
        and (DIST / path).is_file()
    ):
        return FileResponse(DIST / path)
    if re.fullmatch(r"model-icons/[a-z0-9-]+\.svg", path) and (DIST / path).is_file():
        return FileResponse(DIST / path, headers={"Cache-Control": "public, max-age=86400"})
    if not (DIST / "index.html").exists():
        return JSONResponse({"detail": "前端尚未构建。"}, status_code=503)
    return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
