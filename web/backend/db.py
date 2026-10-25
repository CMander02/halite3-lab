from contextlib import contextmanager
import hashlib
import io
from pathlib import Path
import sqlite3
import time
import zipfile
from . import settings as S


@contextmanager
def connect():
    connection = sqlite3.connect(S.DATA / "arena.sqlite3", timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=15000")
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize():
    S.DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in ["blobs", "replays", "logs", "work"]:
        (S.DATA / directory).mkdir(exist_ok=True, mode=0o700)
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not exists:
            db.executescript((Path(__file__).parent / "schema.sql").read_text())
        columns = {row["name"] for row in db.execute("PRAGMA table_info(api_tokens)")}
        if "expires_at" not in columns:
            db.execute(
                "ALTER TABLE api_tokens ADD COLUMN expires_at INTEGER NOT NULL DEFAULT 0"
            )
        if "language" not in {
            r["name"] for r in db.execute("PRAGMA table_info(versions)")
        }:
            db.execute(
                "ALTER TABLE versions ADD COLUMN language TEXT NOT NULL DEFAULT 'python'"
            )
        from . import admin, analytics, profiles

        profiles.migrate(db)
        admin.migrate(db)
        analytics.backfill(db)
        for name, version in [("baseline", "1.0"), ("raider", "1.1")]:
            blob = io.BytesIO()
            with zipfile.ZipFile(blob, "w", zipfile.ZIP_DEFLATED) as archive:
                for filename, contents in [
                    ("bot.py", (S.PROJECT / f"lab/bots/{name}.py").read_bytes()),
                    ("common.py", (S.PROJECT / "lab/bots/common.py").read_bytes()),
                ]:
                    info = zipfile.ZipInfo(filename, date_time=(2026, 10, 25, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, contents)
            data = blob.getvalue()
            digest = hashlib.sha256(data).hexdigest()
            key = f"blobs/builtin-{name}-{digest}.zip"
            (S.DATA / key).write_bytes(data)
            previous = db.execute(
                "SELECT sha256 FROM versions WHERE id=?", (f"builtin-{name}-v1",)
            ).fetchone()
            if previous and previous["sha256"] not in ("pending", digest):
                raise RuntimeError(
                    "Builtin source changed: create a new immutable version and season before deployment"
                )
            db.execute(
                "UPDATE versions SET object_key=?,sha256=?,size=? WHERE id=?",
                (key, digest, len(data), f"builtin-{name}-v1"),
            )


def now():
    return int(time.time())
