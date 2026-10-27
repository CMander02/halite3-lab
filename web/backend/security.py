import hashlib
import secrets
from urllib.parse import urlsplit
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException, Request, Response
from . import settings as S
from .db import connect, now

PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
COOKIE = "__Host-halite3" if S.ORIGIN.startswith("https://") else "halite3-dev"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def rate_limit(request, category, limit, seconds, identity="", exempt=False):
    if exempt:
        return
    # The origin only listens on loopback; cloudflared supplies the connecting IP.
    ip = (
        request.headers.get("cf-connecting-ip")
        if request.client and request.client.host in ("127.0.0.1", "::1")
        else None
    )
    ip = ip or (request.client.host if request.client else "unknown")
    key = digest(f"{category}:{ip}:{identity}:{now() // seconds}")
    with connect() as db:
        row = db.execute(
            "INSERT INTO rate_limits(key,hits,reset_at) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET hits=hits+1 RETURNING hits",
            (key, now() + seconds),
        ).fetchone()
    if row["hits"] > limit:
        raise HTTPException(
            429, "请求过于频繁，请稍后再试。", headers={"Retry-After": str(seconds)}
        )


def csrf(request):
    if request.headers.get("authorization", "").startswith("Bearer "):
        return
    origin = request.headers.get("origin")
    allowed = {S.ORIGIN}
    if S.ORIGIN.startswith("http://127.0.0.1"):
        allowed.add("http://127.0.0.1:5183")
    if origin not in allowed:
        raise HTTPException(403, "请求来源校验失败。")


def user_for(request: Request, required=True):
    header = request.headers.get("authorization", "")
    bearer = header[7:] if header.startswith("Bearer ") else None
    value = bearer or request.cookies.get(COOKIE)
    row = None
    if value:
        with connect() as db:
            if bearer:
                row = db.execute(
                    "SELECT u.id,u.username,u.display_name,u.avatar_version,u.is_admin FROM users u JOIN api_tokens t ON t.user_id=u.id WHERE t.token_hash=? AND t.expires_at>? AND u.disabled_at IS NULL",
                    (digest(value), now()),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT u.id,u.username,u.display_name,u.avatar_version,u.is_admin FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>? AND u.disabled_at IS NULL",
                    (digest(value), now()),
                ).fetchone()
    if row:
        user = dict(row)
        user["is_admin"] = bool(user["is_admin"])
        return user
    if required:
        raise HTTPException(401, "请先登录。")
    return None


def set_session(response: Response, user_id, old=None):
    value = secrets.token_urlsafe(32)
    with connect() as db:
        if old:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(old),))
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?,?)",
            (digest(value), user_id, now() + 7 * 86400, now()),
        )
    response.set_cookie(
        COOKIE,
        value,
        max_age=7 * 86400,
        secure=S.ORIGIN.startswith("https://"),
        httponly=True,
        samesite="lax",
        path="/",
    )


def verify_password(stored, password):
    try:
        return PASSWORDS.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def is_admin(db, user_id):
    row = db.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    return bool(row and row["is_admin"])


def admin_for(request: Request):
    user = user_for(request)
    if not user["is_admin"]:
        raise HTTPException(403, "仅管理员可以访问。")
    return user
