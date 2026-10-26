import hashlib
import io
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend import settings as S
from backend.api import app
from backend.db import connect, initialize, now
from backend.runner import claim, run_match
from backend.security import COOKIE
from backend.storage import validate_archive
from backend.builds import prepare, sandbox, BotBuildError
from backend.scheduler import version_info, snapshot

PASSWORD = "a-long-test-password-42"
TRACE = (
    b'{"type":"user","sessionId":"s","userType":"external","entrypoint":"cli","timestamp":"2026-10-25T10:00:00Z","message":{"role":"user","content":"write a bot"}}\n'
    b'{"type":"assistant","sessionId":"s","userType":"external","entrypoint":"cli","timestamp":"2026-10-25T10:40:00Z","message":{"role":"assistant","model":"claude-opus-5-5","content":[],"usage":{"output_tokens":1200}}}\n'
    b'{"type":"api-request","sessionId":"s","timestamp":"2026-10-25T10:40:00Z","params":{"model":"claude-opus-5-5","output_config":{"effort":"high"}}}\n'
)
SOURCE = b'#include <iostream>\n#include <string>\nint main(){std::string line;std::getline(std::cin,line);std::cout<<"example"<<std::endl;while(std::getline(std::cin,line))std::cout<<std::endl;}\n'
PYTHON_SOURCE = b'import sys\nprint("legacy",flush=True)\nfor line in sys.stdin: print("",flush=True)\n'


class BackendTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = S.DATA
        self.oldfree = S.MIN_DISK_FREE
        S.DATA = Path(self.temp.name)
        S.MIN_DISK_FREE = 0
        initialize()
        self.a = TestClient(app, base_url=S.ORIGIN, headers={"Origin": S.ORIGIN})
        self.b = TestClient(app, base_url=S.ORIGIN, headers={"Origin": S.ORIGIN})
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.a.close()
        self.b.close()
        S.DATA = self.old
        S.MIN_DISK_FREE = self.oldfree
        self.temp.cleanup()

    def account(self, client, name):
        response = client.post(
            "/api/auth/register", json={"username": name, "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["user"]

    def upload(
        self,
        client,
        name="test-bot",
        version="1.0",
        source=SOURCE,
        filename="bot.cpp",
        bot=None,
        trace=TRACE,
        declared=None,
    ):
        if bot is None:
            response = client.post("/api/bots", json={"name": name})
            self.assertEqual(response.status_code, 201, response.text)
            bot = response.json()["id"]
        files = {"file": (filename, source)}
        if trace is not None:
            files["trace"] = ("session.jsonl", trace)
        response = client.post(
            f"/api/bots/{bot}/versions",
            data={"version": version, **(declared or {})},
            files=files,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return bot, response.json()["id"]

    def test_auth_argon2_and_session_revocation(self):
        user = self.account(self.a, "alice")
        with connect() as db:
            stored = db.execute(
                "SELECT password_hash FROM users WHERE id=?", (user["id"],)
            ).fetchone()[0]
            token = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
        self.assertTrue(stored.startswith("$argon2id$"))
        self.assertNotEqual(token, self.a.cookies.get(COOKIE))
        self.assertEqual(self.a.get("/api/session").json()["user"]["username"], "alice")
        self.a.post("/api/auth/logout", json={})
        self.assertEqual(self.a.get("/api/tests").status_code, 401)
        self.assertEqual(
            self.a.post(
                "/api/auth/login",
                json={"username": "alice", "password": PASSWORD + "wrong"},
            ).status_code,
            401,
        )
        self.assertEqual(
            self.a.post(
                "/api/auth/login", json={"username": "alice", "password": PASSWORD}
            ).status_code,
            200,
        )

    def test_private_sources_and_matches_are_isolated(self):
        self.account(self.a, "alice")
        self.account(self.b, "bob")
        bot, vid = self.upload(self.a)
        self.assertNotIn(bot, [b["id"] for b in self.b.get("/api/bots").json()["bots"]])
        self.assertEqual(self.b.get(f"/api/versions/{vid}/source").status_code, 404)
        self.assertEqual(
            self.b.post(
                f"/api/bots/{bot}/versions",
                data={"version": "hijack"},
                files={"file": ("bot.cpp", SOURCE)},
            ).status_code,
            404,
        )
        job = self.a.post(
            "/api/tests",
            json={"version_ids": [vid, "builtin-baseline-v1"], "seeds": [11]},
        ).json()["id"]
        match = self.a.get(f"/api/tests/{job}").json()["matches"][0]["id"]
        self.assertEqual(self.b.get(f"/api/tests/{job}").status_code, 404)
        self.assertEqual(self.b.get(f"/api/matches/{match}").status_code, 404)
        self.assertEqual(self.b.get("/api/matches").json()["total"], 0)
        self.assertEqual(
            self.b.post(
                "/api/tests",
                json={"version_ids": [vid, "builtin-baseline-v1"], "seeds": [11]},
            ).status_code,
            404,
        )

    def test_latest_folder_and_fixed_test_versions(self):
        user = self.account(self.a, "alice")
        bot, v1 = self.upload(self.a)
        _, v2 = self.upload(
            self.a, version="2.0", bot=bot, source=SOURCE + b"// second\n"
        )
        folder = S.DATA / "users" / user["id"] / "bots" / bot
        self.assertEqual((folder / "latest").resolve(), folder / "versions" / v2)
        response = self.a.post(
            "/api/tests", json={"bot_ids": [bot, "builtin-baseline"], "seeds": [11]}
        )
        self.assertEqual(response.status_code, 201, response.text)
        job = response.json()["id"]
        self.upload(self.a, version="3.0", bot=bot, source=SOURCE + b"// third\n")
        seats = self.a.get(f"/api/tests/{job}").json()["matches"][0]["seats"]
        self.assertIn(v2, [s["id"] for s in seats])
        self.assertNotIn(v1, [s["id"] for s in seats])
        duplicate = self.a.post(
            f"/api/bots/{bot}/versions",
            data={"version": "2.0"},
            files={"file": ("bot.cpp", SOURCE + b"// overwrite"), "trace": ("t.jsonl", TRACE)},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            self.a.get(f"/api/versions/{v2}/source").content, SOURCE + b"// second\n"
        )

    def test_csrf_and_scoped_api_token(self):
        self.account(self.a, "alice")
        self.assertEqual(
            self.a.post(
                "/api/bots",
                json={"name": "bad"},
                headers={"Origin": "https://evil.example"},
            ).status_code,
            403,
        )
        value = self.a.post("/api/tokens", json={"name": "cli"}).json()
        header = {"Authorization": "Bearer " + value["token"]}
        anonymous = TestClient(app, base_url=S.ORIGIN)
        self.assertEqual(anonymous.get("/api/tests", headers=header).status_code, 200)
        self.assertEqual(
            self.a.delete(
                "/api/tokens/" + value["id"], headers={"Origin": "https://evil.example"}
            ).status_code,
            403,
        )
        self.assertEqual(self.a.delete("/api/tokens/" + value["id"]).status_code, 200)
        self.assertEqual(anonymous.get("/api/tests", headers=header).status_code, 401)
        anonymous.close()

    def test_upload_validation_traversal_symlink_and_bomb(self):
        for name, mode, data in [
            ("../escape.py", None, b"x"),
            ("evil.py", stat.S_IFLNK | 0o777, b"/etc/passwd"),
            ("huge.dat", None, b"0" * (S.MAX_UNPACKED + 1)),
        ]:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("bot.cpp", SOURCE)
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                if mode:
                    info.external_attr = mode << 16
                archive.writestr(info, data)
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_archive(stream.getvalue(), "bot.zip")
        self.assertEqual(validate_archive(b"int main(){}", "bot.cpp"), "cpp")
        with self.assertRaises(ValueError):
            validate_archive(PYTHON_SOURCE, "bot.py")

    def test_only_cpp_sources_and_cpp_projects_can_be_uploaded(self):
        self.account(self.a, "alice")
        bot = self.a.post("/api/bots", json={"name": "cpp-only"}).json()["id"]

        def archive(files):
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as z:
                for name, content in files:
                    z.writestr(name, content)
            return data.getvalue()

        for filename, source in [
            ("bot.py", PYTHON_SOURCE), ("BOT.PY", PYTHON_SOURCE),
            ("bot.js", b"console.log('bot')"), ("bot", SOURCE),
            ("python.zip", archive([("bot.py", PYTHON_SOURCE)])),
            ("mixed.ZIP", archive([("main.cpp", SOURCE), ("bot.py", PYTHON_SOURCE)])),
            ("nested.zip", archive([("main.cc", SOURCE), ("lib/helper.PY", PYTHON_SOURCE)])),
            ("bytecode.zip", archive([("main.cpp", SOURCE), ("__pycache__/bot.pyc", b"x")])),
            ("empty.zip", archive([("main.cpp/", b"")])),
            ("headers.zip", archive([("bot.hpp", b"#pragma once")])),
            ("broken.zip", b"not a zip"),
        ]:
            with self.subTest(filename=filename):
                response = self.a.post(f"/api/bots/{bot}/versions", data={"version": "bad", "rank": "true"},
                                       files={"file": (filename, source), "trace": ("trace.jsonl", TRACE)})
                self.assertEqual(response.status_code, 400, response.text)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM versions WHERE bot_id=?", (bot,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)
        for index, filename in enumerate(("main.cpp", "main.cc", "MAIN.CXX")):
            _, vid = self.upload(self.a, bot=bot, version=str(index), filename=filename)
            self.assertEqual(self.a.get(f"/api/versions/{vid}/source").content, SOURCE)
        project = archive([("src/main.cc", SOURCE), ("src/helper.cxx", b"int helper(){return 1;}"), ("src/helper.hpp", b"#pragma once")])
        self.upload(self.a, bot=bot, version="zip", filename="project.ZIP", source=project)
        versions = next(b for b in self.a.get("/api/bots").json()["bots"] if b["id"] == bot)["versions"]
        self.assertTrue(all(v["language"] == "cpp" and v["eligible"] for v in versions))

    def legacy_python(self, vid):
        """Reproduce a stored pre-policy user version without uploading Python."""
        with connect() as db:
            row = db.execute("SELECT object_key FROM versions WHERE id=?", (vid,)).fetchone()
            (S.DATA / row["object_key"]).write_bytes(PYTHON_SOURCE)
            db.execute("UPDATE versions SET language='python',filename='bot.py',sha256=?,size=? WHERE id=?",
                       (hashlib.sha256(PYTHON_SOURCE).hexdigest(), len(PYTHON_SOURCE), vid))

    def test_legacy_python_cannot_enter_rank_test_default_or_cached_runtime(self):
        user = self.account(self.a, "alice")
        bot, cpp = self.upload(self.a, version="1")
        _, legacy = self.upload(self.a, bot=bot, version="2")
        self.legacy_python(legacy)
        for path, body in [
            (f"/api/versions/{legacy}/rank", {}),
            ("/api/tests", {"version_ids": [legacy, "builtin-baseline-v1"], "seeds": [11]}),
        ]:
            response = self.a.post(path, json=body)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertIn("C++17", response.text)
        self.assertEqual(self.a.patch(f"/api/bots/{bot}", json={"default_version_id": legacy}).status_code, 400)
        with connect() as db:
            # An old default pointer must not make bot_ids select Python.
            db.execute("UPDATE bots SET default_version_id=? WHERE id=?", (legacy, bot))
            seat = snapshot(version_info(db, legacy, user["id"]))
        response = self.a.post("/api/tests", json={"bot_ids": [bot, "builtin-baseline"], "seeds": [11]})
        self.assertEqual(response.status_code, 201, response.text)
        seats = self.a.get(f"/api/tests/{response.json()['id']}").json()["matches"][0]["seats"]
        self.assertEqual(seats[0]["id"], cpp)
        directory = (S.DATA / seat["object_key"]).parent
        (directory / "runtime").mkdir()
        (directory / "build.json").write_text(json.dumps({"language": "python", "source_sha256": seat["sha256"]}))
        with self.assertRaisesRegex(BotBuildError, "C\\+\\+17"):
            prepare(seat)
        self.assertEqual(self.a.get(f"/api/versions/{legacy}/source").content, PYTHON_SOURCE)
        self.assertEqual(self.a.get(f"/api/versions/{legacy}/trace").status_code, 200)
        items = self.a.get("/api/me/submissions").json()["submissions"]
        self.assertFalse(next(v for v in items if v["id"] == legacy)["eligible"])
        self.a.patch(f"/api/versions/{cpp}", json={"archived": True})
        self.assertEqual(self.a.post("/api/tests", json={"bot_ids": [bot, "builtin-baseline"], "seeds": [11]}).status_code, 404)

    def test_legacy_queued_matches_fail_once_and_cannot_be_retried(self):
        self.account(self.a, "alice")
        _, vid = self.upload(self.a)
        response = self.a.post("/api/tests", json={"version_ids": [vid, "builtin-baseline-v1"], "seeds": [11, 29]})
        job = response.json()["id"]
        self.legacy_python(vid)
        match = claim()
        with patch("backend.runner.prepare") as build:
            self.assertFalse(run_match(match))
            build.assert_not_called()
        detail = self.a.get(f"/api/tests/{job}").json()
        self.assertFalse(detail["retryable"])
        failed = next(m for m in detail["matches"] if m["id"] == match["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["attempts"], 1)
        self.assertIn("C++17", failed["error"])
        self.assertEqual(self.a.post(f"/api/tests/{job}/retry", json={}).status_code, 400)
        with connect() as db:
            self.assertEqual(db.execute("SELECT status FROM matches WHERE id=?", (match["id"],)).fetchone()[0], "failed")
        self.assertEqual(self.a.post(f"/api/tests/{job}/cancel", json={}).status_code, 200)

    def test_legacy_rankings_are_hidden_but_history_is_preserved(self):
        from backend.rating import _cache
        self.account(self.a, "alice")
        _, vid = self.upload(self.a)
        job = self.a.post(f"/api/versions/{vid}/rank", json={}).json()["id"]
        with connect() as db:
            games = db.execute("SELECT id,seat_json FROM matches WHERE job_id=?", (job,)).fetchall()
            for game in games:
                seats = json.loads(game["seat_json"])
                stats = {str(i): {"rank": 1 if s["id"] == vid else 2, "score": 100} for i, s in enumerate(seats)}
                db.execute("UPDATE matches SET status='complete',finished_at=123,result_json=? WHERE id=?", (json.dumps({"stats": stats}), game["id"]))
                for i, s in enumerate(seats):
                    db.execute("INSERT INTO match_players(match_id,seat,version_id,rank,score) VALUES(?,?,?,?,?)", (game["id"], i, s["id"], stats[str(i)]["rank"], 100))
        _cache["key"] = None
        self.assertIn(vid, [e["version_id"] for e in self.a.get("/api/leaderboard").json()["entries"]])
        self.assertIn(vid, [e["version_id"] for e in self.a.get("/api/leaderboard/elo").json()["entries"]])
        self.legacy_python(vid)
        for path in ("/api/leaderboard", "/api/leaderboard/elo", "/api/leaderboard/stats"):
            self.assertNotIn(vid, [e["version_id"] for e in self.a.get(path).json()["entries"]])
        item = self.a.get("/api/me/submissions").json()["submissions"][0]
        self.assertFalse(item["eligible"])
        self.assertIsNone(item["elo"]["rank"])
        self.assertEqual(item["ranked"]["complete"], 12)
        self.assertEqual(self.a.get(f"/api/tests/{job}").json()["counts"], {"complete": 12})
        self.assertEqual(self.a.post(f"/api/versions/{vid}/rank", json={}).status_code, 400)

    def test_retired_python_download_is_not_served_even_if_stale_file_exists(self):
        (S.DATA / "sample-python.zip").write_bytes(b"old generated sample")
        with patch("backend.api.DIST", S.DATA):
            self.assertEqual(self.a.get("/sample-python.zip").status_code, 404)

    def test_cli_rejects_python_before_network_or_account_mutation(self):
        import client
        with patch.object(sys, "argv", ["client.py", "upload", "bot.py", "--name", "bot", "--version", "1", "--trace", "t.jsonl"]), patch.object(client, "request") as request:
            with self.assertRaises(SystemExit) as exc:
                client.main()
            self.assertEqual(exc.exception.code, 2)
            request.assert_not_called()

    def test_job_limits_and_fair_scheduling(self):
        self.account(self.a, "alice")
        self.account(self.b, "bob")
        _, va = self.upload(self.a)
        _, vb = self.upload(self.b)
        ja = self.a.post(
            "/api/tests",
            json={"version_ids": [va, "builtin-baseline-v1"], "seeds": [11, 29]},
        ).json()["id"]
        jb = self.b.post(
            "/api/tests",
            json={"version_ids": [vb, "builtin-baseline-v1"], "seeds": [11]},
        ).json()["id"]
        first = claim()
        self.assertEqual(first["job_id"], ja)
        self.assertIsNone(claim())
        with connect() as db:
            db.execute(
                "UPDATE matches SET status='complete' WHERE id=?", (first["id"],)
            )
        second = claim()
        self.assertEqual(second["job_id"], jb)
        bad = self.a.post(
            "/api/tests",
            json={"version_ids": [va, "builtin-baseline-v1"], "modes": [8]},
        )
        self.assertEqual(bad.status_code, 400)

    def test_expired_lease_retry_and_completed_match_skipping(self):
        self.account(self.a, "alice")
        _, vid = self.upload(self.a)
        self.a.post(
            "/api/tests",
            json={"version_ids": [vid, "builtin-baseline-v1"], "seeds": [11]},
        )
        first = claim()
        with connect() as db:
            db.execute("UPDATE matches SET lease_until=0 WHERE id=?", (first["id"],))
        second = claim()
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["attempts"], 2)
        with connect() as db:
            self.assertEqual(
                db.execute(
                    "SELECT status FROM attempts WHERE match_id=? AND number=1",
                    (first["id"],),
                ).fetchone()[0],
                "interrupted",
            )
            db.execute(
                "UPDATE matches SET status='complete' WHERE id=?", (second["id"],)
            )
        self.assertIsNone(claim())

    def test_ranked_has_fixed_evaluation_and_private_tests_do_not_count(self):
        self.account(self.a, "alice")
        _, vid = self.upload(self.a)
        self.a.post(
            "/api/tests",
            json={
                "version_ids": [vid, "builtin-baseline-v1"],
                "seeds": [1],
                "kind": "ranked",
            },
        )
        self.assertEqual(self.a.get("/api/leaderboard").json()["entries"], [])
        response = self.a.post(f"/api/versions/{vid}/rank", json={})
        self.assertEqual(response.status_code, 201, response.text)
        job = self.a.get("/api/tests/" + response.json()["id"]).json()
        self.assertEqual(job["total"], 12)
        self.assertEqual(job["config"]["seeds"], [11, 29, 47])
        self.assertTrue(all(m["public"] == 1 for m in job["matches"]))
        self.assertEqual(self.a.get("/api/leaderboard").json()["entries"], [])

    def test_invalid_cpp_build_is_cached_and_not_retried(self):
        self.account(self.a, "alice")
        _, vid = self.upload(
            self.a, filename="main.cpp", source=b"int main( { syntax error"
        )
        self.a.post(
            "/api/tests",
            json={"version_ids": [vid, "builtin-baseline-v1"], "seeds": [11]},
        )
        match = claim()
        self.assertFalse(run_match(match))
        with connect() as db:
            row = db.execute(
                "SELECT status,attempts FROM matches WHERE id=?", (match["id"],)
            ).fetchone()
            seat = snapshot(
                version_info(db, vid, self.a.get("/api/session").json()["user"]["id"])
            )
        self.assertEqual(tuple(row), ("failed", 1))
        with self.assertRaises(BotBuildError):
            prepare(seat)

    def test_real_cpp_against_fixed_baseline_and_replay(self):
        self.account(self.a, "alice")
        source = (S.ROOT / "examples/cpp/main.cpp").read_bytes()
        _, vid = self.upload(self.a, filename="main.cpp", source=source)
        response = self.a.post(
            "/api/tests",
            json={"version_ids": [vid, "builtin-baseline-v1"], "seeds": [11]},
        )
        self.assertEqual(response.status_code, 201, response.text)
        match = claim()
        self.assertTrue(run_match(match))
        detail = self.a.get("/api/matches/" + match["id"]).json()
        self.assertEqual(detail["status"], "complete")
        self.assertTrue(detail["has_replay"])
        self.assertFalse(any(detail["result"]["terminated"].values()), detail)
        replay = self.a.get("/api/matches/" + match["id"] + "/replay")
        self.assertEqual(replay.status_code, 200)
        self.assertGreater(len(replay.json()["full_frames"]), 10)
        self.assertTrue(
            self.a.get("/api/matches/" + match["id"] + "/logs").json()["players"]
        )

    def test_cpp_zip_compiles_multiple_units_and_matches_fixed_raider(self):
        self.account(self.a, "alice")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("src/MAIN.CXX", SOURCE.replace(b'int main(){', b'#include "helper.hpp"\nint main(){helper();'))
            archive.writestr("src/helper.cc", b'int helper(){return 0;}')
            archive.writestr("src/helper.hpp", b'int helper();')
        _, vid = self.upload(self.a, filename="project.zip", source=stream.getvalue())
        response = self.a.post("/api/tests", json={"version_ids": [vid, "builtin-raider-v1"], "seeds": [11]})
        self.assertEqual(response.status_code, 201, response.text)
        match = claim()
        self.assertTrue(run_match(match))
        detail = self.a.get("/api/matches/" + match["id"]).json()
        self.assertEqual(detail["status"], "complete")
        self.assertFalse(any(detail["result"]["terminated"].values()), detail)


    def test_single_admin_and_user_management(self):
        admin = self.account(self.a, S.ADMIN_USERNAME)
        bob = self.account(self.b, "bob")
        self.assertTrue(self.a.get("/api/session").json()["user"]["is_admin"])
        self.assertFalse(self.b.get("/api/session").json()["user"]["is_admin"])
        self.assertEqual(self.b.get("/api/admin/users").status_code, 403)
        listed = self.a.get("/api/admin/users").json()["users"]
        self.assertEqual([u["username"] for u in listed if u["is_admin"]], [S.ADMIN_USERNAME])
        with self.assertRaises(sqlite3.IntegrityError), connect() as db:
            db.execute("UPDATE users SET is_admin=1 WHERE id=?", (bob["id"],))
        self.assertEqual(self.a.patch(f"/api/admin/users/{admin['id']}", json={"disabled": True}).status_code, 400)
        self.assertEqual(self.a.patch(f"/api/admin/users/{bob['id']}", json={"disabled": True}).status_code, 200)
        self.assertIsNone(self.b.get("/api/session").json()["user"])
        login = self.b.post("/api/auth/login", json={"username": "bob", "password": PASSWORD})
        self.assertEqual(login.status_code, 403)
        self.a.patch(f"/api/admin/users/{bob['id']}", json={"disabled": False})
        password = self.a.post(f"/api/admin/users/{bob['id']}/password").json()["password"]
        self.assertEqual(self.b.post("/api/auth/login", json={"username": "bob", "password": PASSWORD}).status_code, 401)
        self.assertEqual(self.b.post("/api/auth/login", json={"username": "bob", "password": password}).status_code, 200)
        wrong = self.b.post("/api/me/password", json={"current_password": "nope", "new_password": "another-long-password"})
        self.assertEqual(wrong.status_code, 400)
        changed = self.b.post("/api/me/password", json={"current_password": password, "new_password": "another-long-password"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertTrue(self.b.get("/api/session").json()["user"])
        self.assertEqual(self.b.post("/api/auth/login", json={"username": "bob", "password": "another-long-password"}).status_code, 200)

    def test_trace_is_required_detected_and_strongest_setup_counts(self):
        self.account(self.a, "alice")
        response = self.a.post("/api/bots", json={"name": "traced"})
        bot = response.json()["id"]
        missing = self.a.post(f"/api/bots/{bot}/versions", data={"version": "1"}, files={"file": ("bot.cpp", SOURCE)})
        self.assertEqual(missing.status_code, 400)
        _, vid = self.upload(self.a, bot=bot, version="2",
                             declared={"model": "claude-haiku-5-5", "effort": "low", "harness": "claude-code"})
        item = self.a.get("/api/me/submissions").json()["submissions"][0]
        self.assertEqual(item["detection"]["model"], "claude-opus-5-5")
        self.assertEqual(item["detection"]["effort"], "high")
        self.assertEqual(item["detection"]["harness"], "claude-code")
        self.assertEqual(item["detection"]["duration_seconds"], 2400)
        attribution = item["attribution"]
        self.assertEqual(attribution["model"]["value"], "claude-opus-5-5")
        self.assertEqual(attribution["model"]["source"], "detected")
        self.assertEqual(attribution["effort"]["value"], "high")
        self.assertEqual(set(attribution["mismatch"]), {"model", "effort"})
        # The bot icon follows the detected model, not the under-declared one.
        listed = next(b for b in self.a.get("/api/bots").json()["bots"] if b["id"] == bot)
        self.assertEqual(listed["model"], "claude-opus-5-5")
        self.assertNotIn("detection_json", listed["versions"][0])
        trace = self.a.get(f"/api/versions/{vid}/trace")
        self.assertEqual(trace.status_code, 200)
        self.assertEqual(self.b.get(f"/api/versions/{vid}/trace").status_code, 401)
        # Declaring a stronger setup than detected keeps the declaration.
        _, strong = self.upload(self.a, bot=bot, version="3",
                                declared={"model": "claude-fable-5-1", "effort": "max", "harness": "claude-code"})
        item = next(i for i in self.a.get("/api/me/submissions").json()["submissions"] if i["id"] == strong)
        self.assertEqual(item["attribution"]["model"]["value"], "claude-fable-5-1")

    def test_admin_catalog_override_and_elo_correction(self):
        self.account(self.a, S.ADMIN_USERNAME)
        self.account(self.b, "bob")
        _, weak = self.upload(self.b, name="weak", declared={"model": "claude-haiku-5-5", "effort": "low", "harness": "chat-web"},
                              trace=b"plain text chat with claude-haiku-5-5")
        _, strong = self.upload(self.b, name="strong", declared={"model": "claude-opus-5-5", "effort": "high", "harness": "claude-code"})
        with connect() as db:
            db.execute("INSERT INTO jobs(id,owner_id,name,kind,config_json,created_at) VALUES('j',NULL,'j','private','{}',0)")
            seats = lambda *ids: json.dumps([{"id": i} for i in ids])
            result = lambda r0, r1: json.dumps({"stats": {"0": {"rank": r0, "score": 1}, "1": {"rank": r1, "score": 0}}})
            games = [(strong, "builtin-baseline-v1", 1, 2)] * 6 + [(weak, "builtin-baseline-v1", 1, 2)] * 5 + [(weak, "builtin-baseline-v1", 2, 1)]
            for i, (x, y, rx, ry) in enumerate(games):
                db.execute("INSERT INTO matches(id,job_id,owner_id,mode,seed,seat_json,status,public,result_json,created_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (f"m{i}", "j", None, 2, 1, seats(x, y), "complete", 1, result(rx, ry), i, i))
        entries = {e["version_id"]: e for e in self.a.get("/api/leaderboard/elo").json()["entries"]}
        self.assertGreater(entries[strong]["elo"], entries[weak]["elo"])
        self.assertEqual(entries[strong]["correction"], 140 + 25 + 30)
        self.assertEqual(entries[weak]["correction"], 40 - 25 + 0)
        self.assertEqual(entries["builtin-baseline-v1"]["correction"], 0)
        self.assertIsNone(entries["builtin-baseline-v1"]["rank"])
        self.assertEqual(entries[weak]["rank"], 1)
        # Admin raises the Haiku correction and overrides the strong version's model.
        entry = next(e for e in self.a.get("/api/admin/catalog").json()["model"] if e["id"] == "claude-haiku-5-5")
        entry["elo_offset"] = 400
        self.assertEqual(self.a.put("/api/admin/catalog/model/claude-haiku-5-5", json=entry).status_code, 200)
        self.assertEqual(self.b.put("/api/admin/catalog/model/claude-haiku-5-5", json=entry).status_code, 403)
        response = self.a.put(f"/api/admin/versions/{strong}/attribution", json={"model": "claude-sonnet-5-5", "note": "人工确认"})
        self.assertEqual(response.status_code, 200, response.text)
        entries = {e["version_id"]: e for e in self.a.get("/api/leaderboard/elo").json()["entries"]}
        self.assertEqual(entries[weak]["correction"], 400 - 25)
        self.assertEqual(entries[strong]["correction"], 100 + 25 + 30)
        self.assertEqual(entries[strong]["rank"], 1)
        # Hidden versions keep their rating but leave the public board.
        self.b.patch(f"/api/versions/{strong}", json={"listed": False})
        ids = [e["version_id"] for e in self.a.get("/api/leaderboard/elo").json()["entries"]]
        self.assertNotIn(strong, ids)

    def test_version_archive_and_default_version(self):
        self.account(self.a, "alice")
        bot, first = self.upload(self.a, version="1")
        _, second = self.upload(self.a, version="2", bot=bot)
        resolve = lambda: self.a.post("/api/tests", json={"bot_ids": [bot, "builtin-baseline"], "seeds": [3]}).json()["id"]
        seats = lambda job: self.a.get(f"/api/tests/{job}").json()["matches"][0]["seats"][0]["id"]
        self.assertEqual(seats(resolve()), second)
        self.assertEqual(self.a.patch(f"/api/bots/{bot}", json={"default_version_id": first}).status_code, 200)
        self.assertEqual(seats(resolve()), first)
        self.a.patch(f"/api/versions/{first}", json={"archived": True, "notes": "旧版"})
        self.assertEqual(seats(resolve()), second)
        versions = next(b for b in self.a.get("/api/bots").json()["bots"] if b["id"] == bot)["versions"]
        self.assertEqual({v["version"]: v["archived"] for v in versions}, {"1": 1, "2": 0})
        self.assertEqual(self.a.patch(f"/api/bots/{bot}", json={"default_version_id": first}).status_code, 400)


class ProfileAndAnalyticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = S.DATA
        S.DATA = Path(self.temp.name)
        initialize()
        self.client = TestClient(app, base_url=S.ORIGIN, headers={"Origin": S.ORIGIN})

    def tearDown(self):
        self.client.close()
        S.DATA = self.old
        self.temp.cleanup()

    def register(self, name):
        response = self.client.post("/api/auth/register", json={"username": name, "password": PASSWORD})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["user"]

    def test_default_avatars_are_unique_and_diagonal_symmetric(self):
        from backend.profiles import _cells
        ids = [self.register(f"pilot{i}")["id"] for i in range(3)]
        with connect() as db:
            patterns = [db.execute("SELECT avatar_pattern FROM users WHERE id=?", (i,)).fetchone()[0] for i in ids]
        self.assertEqual(len({p[:9] for p in patterns}), 3)
        grid = _cells(int(patterns[0][:9], 16))
        self.assertTrue(all(grid[r][c] == grid[c][r] for r in range(8) for c in range(8)))
        response = self.client.get(f"/api/avatars/{ids[0]}")
        self.assertEqual(response.headers["content-type"], "image/svg+xml")
        self.assertIn("public", response.headers["cache-control"])

    def test_avatar_upload_validation_and_reset(self):
        user = self.register("painter")
        bad = self.client.post("/api/me/avatar", files={"file": ("a.png", b"GIF89a" + b"0" * 64, "image/png")})
        self.assertEqual(bad.status_code, 400)
        png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + (64).to_bytes(4, "big") * 2 + b"\x08\x06\x00\x00\x00" + b"0" * 32
        ok = self.client.post("/api/me/avatar", files={"file": ("a.png", png, "image/png")})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(self.client.get(f"/api/avatars/{user['id']}").headers["content-type"], "image/png")
        self.assertTrue(self.client.get("/api/me").json()["has_custom_avatar"])
        self.client.delete("/api/me/avatar")
        self.assertEqual(self.client.get(f"/api/avatars/{user['id']}").headers["content-type"], "image/svg+xml")
        renamed = self.client.patch("/api/me", json={"display_name": "像素船长"})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(self.client.get("/api/session").json()["user"]["display_name"], "像素船长")

    def test_collision_statistics(self):
        from backend.analytics import analyze
        ship = lambda x, y, e: {"x": x, "y": y, "energy": e, "is_inspired": False}
        frames = [
            {"entities": {}, "events": [], "deposited": {"0": 0, "1": 0}},
            # turn 1: light ship 1 (player 0) rams heavy ship 2 (player 1) at (2,2)
            {"entities": {"0": {"1": ship(1, 2, 100)}, "1": {"2": ship(2, 2, 700)}},
             "events": [{"type": "shipwreck", "location": {"x": 2, "y": 2}, "ships": [2]}], "deposited": {"0": 0, "1": 0}},
            # turn 2: equal weights sink together
            {"entities": {"0": {"1": ship(2, 2, 800), "3": ship(5, 5, 0)}, "1": {"4": ship(5, 6, 0)}},
             "events": [{"type": "shipwreck", "location": {"x": 5, "y": 5}, "ships": [3, 4]}], "deposited": {"0": 0, "1": 0}},
            {"entities": {"0": {"1": ship(2, 2, 800)}, "1": {}}, "events": [], "deposited": {"0": 900, "1": 50}},
        ]
        replay = {"full_frames": frames, "production_map": {"width": 8, "height": 8},
                  "players": [{"player_id": 0, "factory_location": {"x": 0, "y": 0}}, {"player_id": 1, "factory_location": {"x": 4, "y": 4}}],
                  "game_statistics": {"player_statistics": [{"player_id": 0, "total_mined": 1000, "ships_spawned": 2, "number_dropoffs": 0}]}}
        p0, p1 = analyze(replay)
        self.assertEqual((p0["kills"], p0["deaths"], p0["assists"]), (1, 1, 1))
        self.assertEqual((p1["kills"], p1["deaths"], p1["assists"]), (0, 2, 1))
        self.assertEqual(p0["robbed"], 700)
        self.assertEqual(p1["lost"], 700)
        self.assertEqual(p0["delivered"], 900)
        self.assertGreater(p0["territory"], p1["territory"])


if __name__ == "__main__":
    unittest.main()
