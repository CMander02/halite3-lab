"""User profiles: unique diagonal-symmetric pixel avatars, uploads, display names, statistics."""
import secrets
import struct
import time
from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from . import settings as S
from .analytics import COLUMNS
from .db import connect, now
from .security import COOKIE, PASSWORDS, digest, rate_limit, user_for, verify_password

router = APIRouter()
GRID = 8
BITS = GRID * (GRID + 1) // 2  # cells on and above the main diagonal
PALETTE = ['#1f4fff', '#0b2a99', '#3b6cff', '#1b3fcc', '#0f6bd6', '#2a3bd9', '#4458ff', '#16359f']
MAX_AVATAR = 256 * 1024


def _cells(bits):
    """Expand 36 bits into an 8x8 grid mirrored across the main diagonal."""
    grid = [[False] * GRID for _ in range(GRID)]
    index = 0
    for row in range(GRID):
        for col in range(row, GRID):
            on = bool(bits >> index & 1)
            grid[row][col] = grid[col][row] = on
            index += 1
    return grid


def _density_ok(bits):
    filled = sum(cell for row in _cells(bits) for cell in row)
    return 22 <= filled <= 42


def new_pattern(db):
    """Random pattern with pleasant density that no other user owns."""
    while True:
        bits = secrets.randbits(BITS)
        if not _density_ok(bits):
            continue
        pattern = f'{bits:09x}{secrets.randbelow(len(PALETTE))}'
        taken = db.execute('SELECT 1 FROM users WHERE substr(avatar_pattern,1,9)=?', (pattern[:9],)).fetchone()
        if not taken:
            return pattern


def svg(pattern):
    bits, color = int(pattern[:9], 16), PALETTE[int(pattern[9:] or 0) % len(PALETTE)]
    # 2-cell margin keeps the pattern inside the circular avatar crop
    rects = ''.join(f'<rect x="{c + 2}" y="{r + 2}" width="1" height="1"/>'
                    for r, row in enumerate(_cells(bits)) for c, on in enumerate(row) if on)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID + 4} {GRID + 4}" shape-rendering="crispEdges">'
            f'<rect width="{GRID + 4}" height="{GRID + 4}" fill="#f5f2e9"/><g fill="{color}">{rects}</g></svg>')


def migrate(db):
    columns = {row['name'] for row in db.execute('PRAGMA table_info(users)')}
    if 'avatar_pattern' not in columns:
        db.execute('ALTER TABLE users ADD COLUMN avatar_pattern TEXT')
        db.execute('ALTER TABLE users ADD COLUMN avatar_key TEXT')
        db.execute('ALTER TABLE users ADD COLUMN avatar_version INTEGER NOT NULL DEFAULT 0')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_avatar_pattern ON users(substr(avatar_pattern,1,9))')
    for row in db.execute('SELECT id FROM users WHERE avatar_pattern IS NULL').fetchall():
        db.execute('UPDATE users SET avatar_pattern=? WHERE id=?', (new_pattern(db), row['id']))
    db.execute('''CREATE TABLE IF NOT EXISTS match_players(
        match_id TEXT NOT NULL REFERENCES matches(id), seat INTEGER NOT NULL, version_id TEXT NOT NULL,
        bot_id TEXT, author_id TEXT, rank INTEGER, score INTEGER,
        kills INTEGER NOT NULL DEFAULT 0, deaths INTEGER NOT NULL DEFAULT 0, assists INTEGER NOT NULL DEFAULT 0,
        robbed INTEGER NOT NULL DEFAULT 0, lost INTEGER NOT NULL DEFAULT 0, delivered INTEGER NOT NULL DEFAULT 0,
        mined INTEGER NOT NULL DEFAULT 0, territory REAL NOT NULL DEFAULT 0, ships_built INTEGER NOT NULL DEFAULT 0,
        dropoffs INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(match_id,seat))''')
    # NULL marks rows recorded before vision existed; analytics.backfill recomputes them from the replay.
    if 'vision' not in {row['name'] for row in db.execute('PRAGMA table_info(match_players)')}:
        db.execute('ALTER TABLE match_players ADD COLUMN vision REAL')
    db.execute('CREATE INDEX IF NOT EXISTS match_players_version ON match_players(version_id)')
    (S.DATA / 'avatars').mkdir(exist_ok=True, mode=0o700)


def profile(row):
    return {'id': row['id'], 'username': row['username'], 'display_name': row['display_name'],
            'avatar_version': row['avatar_version'], 'has_custom_avatar': bool(row['avatar_key'])}


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


@router.post('/api/me/password')
def change_password(payload: PasswordChange, request: Request):
    user = user_for(request)
    rate_limit(request, 'password-change', 8, 600, user['id'])
    with connect() as db:
        stored = db.execute('SELECT password_hash FROM users WHERE id=?', (user['id'],)).fetchone()[0]
    if not verify_password(stored, payload.current_password):
        raise HTTPException(400, '当前密码不正确。')
    hashed = PASSWORDS.hash(payload.new_password)
    current = request.cookies.get(COOKIE)
    with connect() as db:
        db.execute('UPDATE users SET password_hash=? WHERE id=?', (hashed, user['id']))
        # Other browsers are signed out; this session and API tokens stay valid.
        db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?', (user['id'], digest(current) if current else ''))
    return {'ok': True}


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)


@router.get('/api/avatars/{user_id}')
def avatar(user_id: str):
    with connect() as db:
        row = db.execute('SELECT avatar_pattern,avatar_key FROM users WHERE id=?', (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, '用户不存在。')
    headers = {'Cache-Control': 'public, max-age=300'}
    if row['avatar_key'] and (S.DATA / row['avatar_key']).is_file():
        return Response((S.DATA / row['avatar_key']).read_bytes(), media_type='image/png', headers=headers)
    return Response(svg(row['avatar_pattern'] or '0000000000'), media_type='image/svg+xml', headers=headers)


@router.get('/api/me')
def me(request: Request):
    user = user_for(request)
    with connect() as db:
        row = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        stats = db.execute('SELECT COUNT(*) AS games,SUM(rank=1) AS wins,SUM(kills) AS kills,SUM(deaths) AS deaths,SUM(robbed) AS robbed,SUM(delivered) AS delivered FROM match_players WHERE author_id=?', (user['id'],)).fetchone()
        bots = db.execute('SELECT COUNT(*) FROM bots WHERE owner_id=?', (user['id'],)).fetchone()[0]
        versions = db.execute('SELECT COUNT(*) FROM versions v JOIN bots b ON b.id=v.bot_id WHERE b.owner_id=?', (user['id'],)).fetchone()[0]
    return {**profile(row), 'created_at': row['created_at'], 'bots': bots, 'versions': versions,
            'stats': {key: stats[key] or 0 for key in stats.keys()}}


@router.patch('/api/me')
def update_me(payload: ProfileUpdate, request: Request):
    user = user_for(request)
    name = payload.display_name.strip()
    if not name:
        raise HTTPException(400, '显示名称不能为空。')
    with connect() as db:
        db.execute('UPDATE users SET display_name=? WHERE id=?', (name, user['id']))
    return {'ok': True, 'display_name': name}


def _png_size(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise HTTPException(400, '头像需为 PNG 图片（网页会自动裁剪转换）。')
    return struct.unpack('>II', data[16:24])


@router.post('/api/me/avatar')
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    user = user_for(request)
    data = await file.read(MAX_AVATAR + 1)
    if len(data) > MAX_AVATAR:
        raise HTTPException(413, '头像不能超过 256 KiB。')
    width, height = _png_size(data)
    if not (16 <= width <= 512 and 16 <= height <= 512):
        raise HTTPException(400, '头像尺寸应在 16 至 512 像素之间。')
    key = f'avatars/{user["id"]}.png'
    temporary = S.DATA / f'{key}.{secrets.token_hex(4)}.tmp'
    temporary.write_bytes(data)
    temporary.replace(S.DATA / key)
    with connect() as db:
        db.execute('UPDATE users SET avatar_key=?,avatar_version=avatar_version+1 WHERE id=?', (key, user['id']))
        version = db.execute('SELECT avatar_version FROM users WHERE id=?', (user['id'],)).fetchone()[0]
    return {'avatar_version': version}


@router.delete('/api/me/avatar')
def reset_avatar(request: Request):
    user = user_for(request)
    with connect() as db:
        db.execute('UPDATE users SET avatar_key=NULL,avatar_version=avatar_version+1 WHERE id=?', (user['id'],))
        version = db.execute('SELECT avatar_version FROM users WHERE id=?', (user['id'],)).fetchone()[0]
    (S.DATA / f'avatars/{user["id"]}.png').unlink(missing_ok=True)
    return {'avatar_version': version}


BOARD_SQL = '''SELECT p.version_id,v.version,v.bot_id,b.name AS bot_name,b.builtin,u.display_name AS author,p.author_id,
    COUNT(*) AS games,SUM(p.rank=1) AS wins,AVG(p.rank) AS avg_rank,AVG(p.score) AS score,
    SUM(p.kills) AS kills,SUM(p.deaths) AS deaths,SUM(p.assists) AS assists,
    SUM(p.robbed) AS robbed,SUM(p.lost) AS lost,AVG(p.delivered) AS delivered,AVG(p.mined) AS mined,
    AVG(p.territory) AS territory,AVG(p.vision) AS vision,AVG(p.ships_built) AS ships_built
    FROM match_players p JOIN matches m ON m.id=p.match_id JOIN versions v ON v.id=p.version_id
    JOIN bots b ON b.id=v.bot_id LEFT JOIN users u ON u.id=b.owner_id
    WHERE m.status='complete' AND m.public=1 AND (b.builtin=1 OR v.language='cpp') {mode} GROUP BY p.version_id'''


@router.get('/api/leaderboard/stats')
def leaderboard_stats(mode: int | None = None):
    clause, params = ('AND m.mode=?', [mode]) if mode in (2, 4, 8) else ('', [])
    with connect() as db:
        rows = [dict(r) for r in db.execute(BOARD_SQL.format(mode=clause), params)]
    for row in rows:
        row['kda'] = round((row['kills'] + row['assists']) / max(1, row['deaths']), 2)
        row['robbed_per_game'] = row['robbed'] / row['games']
        row['win_rate'] = (row['wins'] or 0) / row['games']
    return {'entries': rows, 'metrics': COLUMNS}


@router.get('/api/summary')
def summary():
    day = 86400
    start = (now() // day - 13) * day
    with connect() as db:
        counts = db.execute('''SELECT (SELECT COUNT(*) FROM users) AS users,(SELECT COUNT(*) FROM bots WHERE builtin=0) AS bots,
            (SELECT COUNT(*) FROM versions) AS versions,(SELECT COUNT(*) FROM matches WHERE status='complete') AS matches,
            (SELECT COUNT(*) FROM matches WHERE status IN ('queued','running')) AS pending,
            (SELECT COALESCE(SUM(kills),0) FROM match_players) AS wrecks,
            (SELECT COALESCE(SUM(delivered),0) FROM match_players) AS delivered''').fetchone()
        daily = {r['d']: r['n'] for r in db.execute("SELECT finished_at/? AS d,COUNT(*) AS n FROM matches WHERE status='complete' AND finished_at>=? GROUP BY d", (day, start))}
    return {**dict(counts), 'daily': [{'day': (start // day + i) * day, 'matches': daily.get(start // day + i, 0)} for i in range(14)],
            'generated_at': int(time.time())}
