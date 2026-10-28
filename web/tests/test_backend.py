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


def winner_first(winner):
    """Ranks for a synthetic game: `winner` first, the other seats in seat order."""
    def ranks(ids):
        others = iter(range(2, len(ids) + 1))
        return [1 if i == winner else next(others) for i in ids]
    return ranks


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

    def test_legacy_password_login_preserves_creation_policy(self):
        from backend.security import PASSWORDS

        legacy_password = "legacy42"
        rejected = self.a.post(
            "/api/auth/register", json={"username": "legacy", "password": legacy_password}
        )
        self.assertEqual(rejected.status_code, 422)
        user = self.account(self.a, "legacy")
        with connect() as db:
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (PASSWORDS.hash(legacy_password), user["id"]))
        self.a.post("/api/auth/logout")
        wrong = self.a.post("/api/auth/login", json={"username": "legacy", "password": "wrong42"})
        self.assertEqual(wrong.status_code, 401)
        login = self.a.post("/api/auth/login", json={"username": "legacy", "password": legacy_password})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["id"], user["id"])
        changed = self.a.post("/api/me/password", json={"current_password": legacy_password, "new_password": "short42"})
        self.assertEqual(changed.status_code, 422)
        for password in ("", "x" * 129):
            with self.subTest(password_length=len(password)):
                invalid = self.a.post("/api/auth/login", json={"username": "legacy", "password": password})
                self.assertEqual(invalid.status_code, 422)

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

    def test_multiplayer_benchmark_schedule(self):
        from collections import Counter
        from backend.scheduler import multiplayer_games
        cand, pool = {"id": "c"}, [{"id": f"o{i}"} for i in range(9)]
        games = multiplayer_games(cand, pool)
        self.assertEqual(Counter(len(seats) for seats, _ in games), {4: 48, 8: 24})
        for mode in (4, 8):
            tables = [(seats, seed) for seats, seed in games if len(seats) == mode]
            ids = [[s["id"] for s in seats] for seats, _ in tables]
            self.assertTrue(all(len(set(t)) == mode and "c" in t for t in ids))
            self.assertEqual(len({(tuple(t), seed) for t, (_, seed) in zip(ids, tables)}), len(tables))
            seats = Counter(t.index("c") for t in ids)
            self.assertEqual(set(seats), set(range(mode)))
            self.assertEqual(len(set(seats.values())), 1)
            self.assertEqual({o for t in ids for o in t} - {"c"}, {o["id"] for o in pool})
        self.assertEqual(Counter(o for t, _ in games if len(t) == 4 for o in [s["id"] for s in t])["o0"], 16)
        self.assertEqual({len(seats) for seats, _ in multiplayer_games(cand, pool[:5])}, {4})
        self.assertEqual(multiplayer_games(cand, pool[:2]), [])

    def test_ranked_submission_also_queues_public_multiplayer_games(self):
        self.account(self.a, "alice")
        versions = []
        with patch.object(S, "MAX_MATCHES_PER_DAY", 5000):
            for i in range(9):
                _, vid = self.upload(self.a, name=f"bot-{i}")
                response = self.a.post(f"/api/versions/{vid}/rank", json={})
                self.assertEqual(response.status_code, 201, response.text)
                versions.append(vid)
                with connect() as db:  # keep the 3-unfinished-jobs limit out of the way
                    db.execute("UPDATE matches SET status='cancelled' WHERE job_id=?", (response.json()["id"],))
            self.assertEqual(self.a.post(f"/api/versions/{vid}/rank", json={}).status_code, 201)
        with connect() as db:
            jobs = db.execute("SELECT * FROM jobs WHERE kind='ranked-multi' AND candidate_id=?", (vid,)).fetchall()
            self.assertEqual(len(jobs), 1)
            config = json.loads(jobs[0]["config_json"])
            rows = db.execute("SELECT mode,public,seat_json FROM matches WHERE job_id=?", (jobs[0]["id"],)).fetchall()
            first = db.execute("SELECT COUNT(*) FROM jobs WHERE kind='ranked-multi' AND candidate_id=?", (versions[0],)).fetchone()[0]
            queued = db.execute("SELECT COUNT(*) FROM matches m JOIN jobs j ON j.id=m.job_id WHERE j.kind='ranked-multi' AND m.status='queued'").fetchone()[0]
        # Pool: both builtins, then seven of the eight other #0 bots; never the candidate's own bot.
        self.assertEqual(config["opponents"][:2], ["builtin-baseline-v1", "builtin-raider-v1"])
        self.assertEqual(len(set(config["opponents"][2:]) & set(versions[:8])), 7)
        self.assertEqual(sorted(config["setups"]), ["4", "8"])
        self.assertEqual({m: sum(r["mode"] == m for r in rows) for m in (4, 8)}, {4: 48, 8: 24})
        self.assertTrue(all(r["public"] == 1 for r in rows))
        self.assertTrue(all(vid in [s["id"] for s in json.loads(r["seat_json"])] for r in rows))
        self.assertEqual(first, 0)  # alone with two builtins: too few opponents
        self.assertGreater(queued, 72)  # earlier multiplayer jobs did not count as unfinished jobs
        job = self.a.get("/api/tests/" + jobs[0]["id"]).json()
        self.assertEqual(job["kind"], "ranked-multi")
        self.assertEqual(job["total"], 72)
        # The multiplayer job is filed under #0: its games show up in #0's match list.
        with connect() as db:
            zero = db.execute("SELECT id,slug FROM contests WHERE number=0").fetchone()
            self.assertEqual(jobs[0]["contest_id"], zero["id"])
        listed = self.a.get(f"/api/matches?contest={zero['slug']}&mode=8").json()
        self.assertGreaterEqual(listed["total"], 24)
        self.assertTrue(all(m["mode"] == 8 for m in listed["matches"]))
        self.assertEqual(self.a.get("/api/matches?contest=no-such-contest").status_code, 404)
        # The private-practice view of /tests leaves benchmark jobs out.
        kinds = {j["kind"] for j in self.a.get("/api/tests").json()["jobs"]}
        self.assertIn("ranked-multi", kinds)
        self.assertEqual(self.a.get("/api/tests?kind=private").json()["jobs"], [])
        detail = self.a.get(f"/api/matches/{listed['matches'][0]['id']}").json()
        self.assertEqual(detail["contest"]["number"], 0)

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

    def test_four_player_match_uses_large_mirrored_map(self):
        self.account(self.a, "alice")
        vids = [self.upload(self.a, name=f"ffa-{i}")[1] for i in range(4)]
        response = self.a.post(
            "/api/tests", json={"version_ids": vids, "modes": [4], "seeds": [11]}
        )
        self.assertEqual(response.status_code, 201, response.text)
        match = claim()
        self.assertEqual(json.loads(match["config_json"])["setups"]["4"]["width"], 48)
        self.assertTrue(run_match(match))
        detail = self.a.get("/api/matches/" + match["id"]).json()
        self.assertEqual(detail["result"]["rules"]["PILEUP_WRECK_SIZE"], 3)
        self.assertEqual(detail["result"]["turns"], 300)
        replay = self.a.get("/api/matches/" + match["id"] + "/replay").json()
        self.assertEqual(
            (replay["production_map"]["width"], replay["production_map"]["height"]),
            (48, 48),
        )
        self.assertTrue(replay["GAME_CONSTANTS"]["MIRROR_REEFS"])


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
        # Optional by default; HALITE_REQUIRE_TRACE=1 makes it mandatory.
        self.assertEqual(self.a.post(f"/api/bots/{bot}/versions", data={"version": "0"}, files={"file": ("bot.cpp", SOURCE)}).status_code, 201)
        S.REQUIRE_TRACE = True
        self.addCleanup(setattr, S, "REQUIRE_TRACE", False)
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

    def contest_payload(self, **changes):
        payload = {
            "slug": "cup-1", "title": "第一届群赛", "summary": "测试", "description": "规则说明",
            "visible_at": now() - 100, "open_at": now() - 50, "close_at": now() + 3600, "published": True,
            "modes": [2, 4], "public_maps": {"2": [11, 29], "4": [7]}, "hidden_maps": {"2": [101], "4": [202]},
            "targets": ["builtin-baseline-v1", "builtin-raider-v1"], "base_version_id": "builtin-baseline-v1",
            "downloads": ["builtin-raider-v1"], "max_submissions": 3, "final_rounds": 2, "languages": ["cpp", "python"],
        }
        payload.update(changes)
        return payload

    def finish_games(self, where, params, rank_of):
        """Complete queued games synthetically: rank_of(seat_ids) -> ranks."""
        with connect() as db:
            rows = db.execute(f"SELECT id,seat_json FROM matches WHERE status='queued' AND {where}", params).fetchall()
            for row in rows:
                ids = [seat["id"] for seat in json.loads(row["seat_json"])]
                ranks = rank_of(ids)
                stats = {str(i): {"rank": r, "score": 1000 * (len(ids) - r)} for i, r in enumerate(ranks)}
                db.execute("UPDATE matches SET status='complete',result_json=?,finished_at=? WHERE id=?",
                           (json.dumps({"stats": stats}), now(), row["id"]))
        return len(rows)

    def test_contest_lifecycle_bench_final_and_global_elo(self):
        from backend import contests

        self.account(self.a, S.ADMIN_USERNAME)
        self.account(self.b, "bob")
        self.assertEqual(self.b.post("/api/admin/contests", json=self.contest_payload()).status_code, 403)
        bad = self.a.post("/api/admin/contests", json=self.contest_payload(hidden_maps={"2": [11], "4": []}))
        self.assertEqual(bad.status_code, 400)
        response = self.a.post("/api/admin/contests", json=self.contest_payload())
        self.assertEqual(response.status_code, 201, response.text)
        cid = response.json()["id"]
        # Hidden maps stay hidden from players until the results are published.
        detail = self.b.get("/api/contests/cup-1").json()
        self.assertEqual(detail["status"], "open")
        self.assertIsNone(detail["maps"]["2"]["hidden"])
        self.assertEqual(detail["maps"]["2"]["hidden_count"], 1)
        self.assertEqual(self.a.get("/api/contests/cup-1").json()["maps"]["2"]["hidden"], [101])
        self.assertEqual(detail["maps"]["4"]["width"], 48)
        self.assertEqual([d["version_id"] for d in detail["downloads"]], ["builtin-raider-v1"])
        self.assertEqual(self.b.get("/api/contests/cup-1/downloads/builtin-raider-v1").status_code, 200)
        self.assertEqual(self.b.get("/api/contests/cup-1/downloads/builtin-baseline-v1").status_code, 200)
        # 1v1: 2 targets x 2 maps x 2 seats; 4p: one group x 1 map x 4 seats.
        self.assertEqual(detail["bench_games"], 8 + 4)

        bot, v1 = self.upload(self.b, name="tide")
        _, v2 = self.upload(self.b, version="2.0", bot=bot)
        first = self.b.post("/api/contests/cup-1/entries", json={"version_id": v1})
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["games"], 12)
        self.assertEqual(self.b.post("/api/contests/cup-1/entries", json={"version_id": v1}).status_code, 409)
        self.assertEqual(self.a.post("/api/contests/cup-1/entries", json={"version_id": v1}).status_code, 404)
        with connect() as db:
            seeds = {r[0] for r in db.execute("SELECT seed FROM matches WHERE job_id=?", (first.json()["job_id"],))}
            self.assertEqual(seeds, {11, 29, 7})
        # The newer submission supersedes the queued bench games of the first one.
        second = self.b.post("/api/contests/cup-1/entries", json={"version_id": v2})
        self.assertEqual(second.status_code, 201, second.text)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM matches WHERE job_id=? AND status='cancelled'", (first.json()["job_id"],)).fetchone()[0], 12)
        self.finish_games("job_id=?", (second.json()["job_id"],), winner_first(v2))
        standings = self.b.get("/api/contests/cup-1/standings").json()["standings"]
        mine = next(r for r in standings["overall"] if r["version_id"] == v2)
        self.assertEqual((mine["rank"], mine["wins"], mine["games"]), (1, 12, 12))
        self.assertTrue(mine["current"])
        self.assertEqual(mine["versus"]["builtin-raider-v1"]["score"], mine["versus"]["builtin-raider-v1"]["games"])
        self.assertIsNone(next(r for r in standings["overall"] if r["version_id"] == "builtin-raider-v1")["rank"])
        self.assertEqual(len(standings["2"]), 3)
        # Contest games are private until the end: no public match, no global ELO.
        self.assertEqual(self.a.get("/api/leaderboard/elo").json()["entries"], [])
        self.assertEqual(self.b.get(f"/api/matches?scope=mine").json()["total"], 24)
        self.assertEqual(self.a.get("/api/matches").json()["total"], 0)
        # Picking the first submission makes it the finalist.
        entries = self.b.get("/api/contests/cup-1/entries").json()["entries"]
        self.assertEqual([e["seq"] for e in entries], [2, 1])
        self.assertTrue(entries[0]["current"])
        self.assertEqual(self.b.put("/api/contests/cup-1/pick", json={"entry_id": entries[1]["id"]}).status_code, 200)
        self.assertTrue(self.b.get("/api/contests/cup-1/entries").json()["entries"][1]["current"])
        self.b.put("/api/contests/cup-1/pick", json={"entry_id": entries[0]["id"]})
        # Bench fields freeze once submissions exist.
        frozen = self.a.put(f"/api/admin/contests/{cid}", json=self.contest_payload(public_maps={"2": [11], "4": [7]}))
        self.assertEqual(frozen.status_code, 409)
        self.assertEqual(self.a.put(f"/api/admin/contests/{cid}", json=self.contest_payload(title="改名")).status_code, 200)
        self.assertEqual(self.b.get("/api/contests/cup-1/standings?stage=final").status_code, 403)

        # Window closes: the runner tick queues the final with the hidden maps.
        with connect() as db:
            db.execute("UPDATE contests SET close_at=? WHERE id=?", (now() - 1, cid))
        self.assertEqual(self.b.post("/api/contests/cup-1/entries", json={"version_id": v1}).status_code, 409)
        contests.tick()
        with connect() as db:
            job = db.execute("SELECT final_job_id FROM contests WHERE id=?", (cid,)).fetchone()[0]
            games = db.execute("SELECT mode,seed,seat_json,public FROM matches WHERE job_id=?", (job,)).fetchall()
        self.assertTrue(job)
        # 1v1: finalist vs 2 targets x 3 maps x 2 seats; 4p: 2 rounds x 2 maps x 1 group.
        self.assertEqual(sum(g["mode"] == 2 for g in games), 12)
        self.assertEqual(sum(g["mode"] == 4 for g in games), 4)
        self.assertIn(101, {g["seed"] for g in games})
        self.assertTrue(all(g["public"] == 0 for g in games))
        self.assertTrue(all([seat["id"] for seat in json.loads(g["seat_json"])].count(v2) == 1 for g in games))
        self.assertEqual(self.b.get("/api/contests/cup-1").json()["status"], "closed")
        # A restart discards the first schedule: its finished games no longer count.
        self.finish_games("job_id=? AND mode=2", (job,), lambda ids: [2 if i == v2 else 1 for i in ids])
        restarted = self.a.post(f"/api/admin/contests/{cid}/final")
        self.assertEqual(restarted.status_code, 200, restarted.text)
        job = restarted.json()["job_id"]
        self.finish_games("job_id=?", (job,), lambda ids: [ids.index(i) + 1 for i in ids])
        contests.tick()
        detail = self.b.get("/api/contests/cup-1").json()
        self.assertEqual(detail["status"], "finished")
        self.assertEqual(detail["maps"]["2"]["hidden"], [101])
        final = self.b.get("/api/contests/cup-1/standings?stage=final").json()
        self.assertTrue(final["final"])
        row = next(r for r in final["standings"]["overall"] if r["version_id"] == v2)
        self.assertEqual(row["rank"], 1)
        self.assertEqual(row["hidden"]["games"], 4 + 2)  # 1v1 seed 101 x 2 targets x 2 seats; 4p seed 202 x 2 rounds
        # Published: games are public and now count in the global ELO.
        self.assertEqual(self.a.get("/api/matches").json()["total"], 24 + 16 + 16)  # bench + final + discarded first final
        ids = [e["version_id"] for e in self.a.get("/api/leaderboard/elo").json()["entries"]]
        self.assertIn(v2, ids)
        self.assertNotIn(v1, ids)  # cancelled bench, never played

        # Bot page: version history with global ELO and contest results, visible to others.
        profile = self.a.get(f"/api/bots/{bot}/profile").json()
        self.assertEqual([v["version"] for v in profile["versions"]], ["1.0", "2.0"])
        latest = profile["versions"][1]
        self.assertIsNotNone(latest["elo"])
        self.assertEqual(latest["contests"][0]["final"]["rank"], 1)
        self.assertEqual(latest["contests"][0]["status"], "finished")
        self.assertEqual(self.a.put(f"/api/admin/contests/{cid}", json=self.contest_payload()).status_code, 409)

    def test_contest_visibility_language_and_quota(self):
        self.account(self.a, S.ADMIN_USERNAME)
        self.account(self.b, "bob")
        payload = self.contest_payload(slug="later", visible_at=now() + 600, open_at=now() + 700, close_at=now() + 900)
        self.assertEqual(self.a.post("/api/admin/contests", json=payload).status_code, 201)
        draft = self.contest_payload(slug="draft", published=False)
        self.assertEqual(self.a.post("/api/admin/contests", json=draft).status_code, 201)
        self.assertEqual([c["number"] for c in self.b.get("/api/contests").json()["contests"]], [0])
        self.assertEqual(self.b.get("/api/contests/later").status_code, 404)
        self.assertEqual([c["number"] for c in self.a.get("/api/contests").json()["contests"]], [2, 1, 0])
        cpp = self.contest_payload(slug="cpp", languages=["cpp"], max_submissions=1, modes=[2])
        self.assertEqual(self.a.post("/api/admin/contests", json=cpp).status_code, 201)
        # Uploads are C++ only; a contest also needs the single file to be named bot.cpp.
        bot, misnamed = self.upload(self.b, filename="main.cpp")
        response = self.b.post("/api/contests/cpp/entries", json={"version_id": misnamed})
        self.assertEqual(response.status_code, 400)
        self.assertIn("bot.cpp", response.json()["detail"])
        source = b'#include <iostream>\nint main(){std::string s; std::getline(std::cin,s); std::cout<<"x"<<std::endl; while(std::getline(std::cin,s)) std::cout<<std::endl;}\n'
        _, a = self.upload(self.b, version="c1", bot=bot, source=source, filename="bot.cpp")
        _, b = self.upload(self.b, version="c2", bot=bot, source=source + b"\n", filename="bot.cpp")
        self.assertEqual(self.b.post("/api/contests/cpp/entries", json={"version_id": a}).status_code, 201)
        self.assertEqual(self.b.post("/api/contests/cpp/entries", json={"version_id": b}).status_code, 409)
        # Targets must be platform baselines or the admin's own versions.
        self.assertEqual(self.a.post("/api/admin/contests", json=self.contest_payload(slug="xx", targets=[a])).status_code, 400)
        # Drafts without submissions can be deleted.
        contest = next(c for c in self.a.get("/api/contests").json()["contests"] if c["slug"] == "draft")
        self.assertEqual(self.a.delete(f"/api/admin/contests/{contest['id']}").status_code, 200)

    def test_admin_has_no_usage_quotas(self):
        for name, value in [("MAX_MATCHES_PER_DAY", 4), ("MAX_MATCHES_PER_JOB", 4)]:
            self.addCleanup(setattr, S, name, getattr(S, name))
            setattr(S, name, value)
        self.account(self.a, S.ADMIN_USERNAME)
        self.account(self.b, "bob")
        source = b'#include <iostream>\nint main(){std::string s; std::getline(std::cin,s); std::cout<<"x"<<std::endl; while(std::getline(std::cin,s)) std::cout<<std::endl;}\n'
        _, va = self.upload(self.a, source=source)
        _, vb = self.upload(self.b, source=source)
        test = lambda client, version, seeds: client.post("/api/tests", json={"version_ids": [version, "builtin-baseline-v1"], "seeds": seeds})
        # Regular users keep the per-job, concurrent-job and daily limits.
        self.assertEqual(test(self.b, vb, [1, 2, 3, 4, 5]).status_code, 400)
        for seed in [1, 2, 3]:
            self.assertEqual(test(self.b, vb, [seed]).status_code, 201)
        self.assertEqual(test(self.b, vb, [4]).status_code, 429)
        # The admin has none of them, nor the hourly rate limit or the 10-seed cap.
        self.assertEqual(test(self.a, va, list(range(12))).status_code, 201)
        for seed in range(11):
            self.assertEqual(test(self.a, va, [seed]).status_code, 201)
        # ... nor a contest's submission cap.
        self.assertEqual(self.a.post("/api/admin/contests", json=self.contest_payload(slug="one", languages=["cpp"], max_submissions=1, modes=[2])).status_code, 201)
        bot, first = self.upload(self.a, name="entry", source=source)
        _, second = self.upload(self.a, version="2.0", bot=bot, source=source + b"\n")
        for version in [first, second]:
            self.assertEqual(self.a.post("/api/contests/one/entries", json={"version_id": version}).status_code, 201)

    def test_written_game_rules(self):
        from backend import contest_docs as D
        expected = {2: [(8, 16), (23, 16)], 4: [(14, 14), (33, 14), (14, 33), (33, 33)],
                    8: [(4, 8), (11, 8), (4, 23), (11, 23), (27, 8), (20, 8), (27, 23), (20, 23)]}
        for mode, spots in expected.items():
            setup = S.MODE_SETUPS[mode]
            self.assertEqual(D.factories(mode, setup["width"], setup["height"]), spots)
            if S.ENGINE.is_file():
                rendered = D.render_map(mode, 11, setup)
                self.assertEqual([tuple(f) for f in rendered["factories"]], spots)
        self.account(self.a, "alice")
        text = self.a.get("/api/contests/test-0").json()["rules_text"]
        for part in ["## 每回合的结算顺序", "P0 (8,16)、P1 (23,16)", "三艘船的例子：", "## 迷雾与观测", "## 违规与判负", "## 结束与名次"]:
            self.assertIn(part, text)
        self.assertNotIn("多船连撞", text)
        # With a 4-player mode the pileup rule is scoped to it and the three-ship example to the others.
        config = {"modes": [2, 4], "public_maps": {"2": [11], "4": [7]}, "hidden_maps": {}, "targets": [], "languages": ["cpp"],
                  "max_submissions": 5, "setups": {str(m): S.MODE_SETUPS[m] for m in (2, 4)}}
        text = D.rules_markdown({"number": 1, "title": "t", "visible_at": None, "open_at": 0, "close_at": 0, "rules": ""}, config)
        self.assertIn("**多船连撞**（仅 4 人混战）", text)
        self.assertIn("三艘船的例子（未开启多船连撞时）", text)

    def test_practice_contest_zero_absorbs_benchmark_runs(self):
        self.account(self.a, "alice")
        _, legacy = self.upload(self.a, name="legacy")
        job = self.a.post(f"/api/versions/{legacy}/rank").json()["id"]
        zero = self.a.get("/api/contests/test-0").json()
        self.assertEqual((zero["number"], zero["status"], zero["practice"]), (0, "open", True))
        entries = self.a.get("/api/contests/test-0/entries").json()["entries"]
        self.assertEqual([(e["version_id"], e["job_id"], e["seq"]) for e in entries], [(legacy, job, 1)])
        self.finish_games("job_id=?", (job,), winner_first(legacy))
        row = next(r for r in self.a.get("/api/contests/test-0/standings").json()["standings"]["overall"] if r["version_id"] == legacy)
        self.assertEqual((row["games"], row["rank"]), (12, 1))
        # Submitting bot.cpp to #0 is the same public 12-game benchmark.
        cpp = b'#include <iostream>\nint main(){}\n'
        response = self.a.post("/api/contests/test-0/submit", data={"bot": "zero-bot"}, files={"file": ("bot.cpp", cpp)})
        self.assertEqual(response.status_code, 201, response.text)
        with connect() as db:
            kind, public = db.execute("SELECT j.kind,MIN(m.public) FROM jobs j JOIN matches m ON m.job_id=j.id WHERE j.id=?", (response.json()["job_id"],)).fetchone()
        self.assertEqual((kind, public, response.json()["games"], response.json()["seq"]), ("ranked", 1, 12, 2))
        # In #0 every bot's latest submission is ranked, not one per user.
        self.assertEqual([e["current"] for e in self.a.get("/api/contests/test-0/entries").json()["entries"]], [True, True])

    def test_contest_upload_bot_cpp_kit_and_written_rules(self):
        self.account(self.a, S.ADMIN_USERNAME)
        self.account(self.b, "bob")
        payload = self.contest_payload(slug="cup-cpp", languages=["cpp"], rules="禁止读取地图种子。", prompt="")
        cid = self.a.post("/api/admin/contests", json=payload).json()["id"]
        cpp = b'#include <iostream>\nint main(){}\n'
        wrong = self.b.post("/api/contests/cup-cpp/submit", files={"file": ("main.cpp", cpp)})
        self.assertEqual(wrong.status_code, 400)
        self.assertIn("bot.cpp", wrong.json()["detail"])
        first = self.b.post("/api/contests/cup-cpp/submit", data={"note": "v1"}, files={"file": ("bot.cpp", cpp)})
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual((first.json()["bot"], first.json()["version"], first.json()["seq"]), ("cup-cpp", "1", 1))
        # Iterating on the same bot, with an agent trace this time.
        second = self.b.post("/api/contests/cup-cpp/submit", data={"bot": "cup-cpp"}, files={"file": ("bot.cpp", cpp + b"//2\n"), "trace": ("s.jsonl", TRACE)})
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual((second.json()["bot_id"], second.json()["version"]), (first.json()["bot_id"], "2"))
        bots = [b for b in self.b.get("/api/bots").json()["bots"] if b["owned"]]
        self.assertEqual([len(b["versions"]) for b in bots], [2])
        # An uploaded version that is not named bot.cpp cannot be entered.
        _, other = self.upload(self.b, name="other", source=cpp, filename="main.cpp")
        response = self.b.post("/api/contests/cup-cpp/entries", json={"version_id": other})
        self.assertEqual(response.status_code, 400)
        # Written rules come from the frozen configuration plus the admin's extra rules.
        detail = self.b.get("/api/contests/cup-cpp").json()
        self.assertIn("bot.cpp", detail["rules_text"])
        self.assertIn("48×48", detail["rules_text"])
        self.assertIn("禁止读取地图种子。", detail["rules_text"])
        self.assertIn("contest-submit cup-cpp", detail["prompt_text"])
        self.assertNotIn("prompt", detail)
        self.assertEqual(self.a.get("/api/contests/cup-cpp").json()["rules"], "禁止读取地图种子。")
        prompt = self.b.get("/api/contests/cup-cpp/prompt.md")
        self.assertEqual(prompt.status_code, 200)
        self.assertIn("比赛规则", prompt.text)
        # The problem kit.
        response = self.b.get("/api/contests/cup-cpp/kit.zip")
        self.assertEqual(response.status_code, 200)
        names = set(zipfile.ZipFile(io.BytesIO(response.content)).namelist())
        for name in ["README.md", "PROMPT.md", "RULES.md", "PROTOCOL.md", "starter/bot.cpp", "tools/client.py",
                     "maps/manifest.json", "maps/rules-2.json", "maps/rules-4.json", "bots/baseline-v1.0/bot.py", "bots/raider-v1.1/common.py"]:
            self.assertIn(f"cup-cpp/{name}", names)
        manifest = json.loads(zipfile.ZipFile(io.BytesIO(response.content)).read("cup-cpp/maps/manifest.json"))
        self.assertEqual([(m["mode"], m["seed"]) for m in manifest["public_maps"]], [(2, 11), (2, 29), (4, 7)])
        self.assertEqual(manifest["hidden_maps"], {"2": 1, "4": 1})
        self.assertNotIn("101", json.dumps(manifest))
        if S.ENGINE.is_file():
            rendered = json.loads(zipfile.ZipFile(io.BytesIO(response.content)).read("cup-cpp/maps/4-7.json"))
            self.assertEqual((rendered["width"], len(rendered["halite"]), len(rendered["factories"])), (48, 48 * 48, 4))
            self.assertTrue(any(rendered["reef"]))


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
        # radius-4 diamonds on an 8x8 torus: player 0 sees more cells (base + ships at (1,2) and (5,5))
        self.assertGreater(p0["vision"], p1["vision"])
        self.assertLessEqual(p0["vision"], 1.0)

    def test_vision_share(self):
        from backend.analytics import _vision
        # one source, radius 1 on a 10x10 torus: 5 cells; radius 4: 41 cells (no wrap overlap)
        self.assertEqual(_vision(10, 10, [(0, 0, 0)], 1, 1), [0.05])
        self.assertEqual(_vision(10, 10, [(0, 0, 0)], 1, 4), [0.41])
        # overlapping sources are not double counted; small torus caps at the whole map
        self.assertEqual(_vision(10, 10, [(0, 0, 0), (0, 0, 0)], 1, 1), [0.05])
        self.assertEqual(_vision(4, 4, [(0, 0, 0)], 1, 4), [1.0])



if __name__ == "__main__":
    unittest.main()
