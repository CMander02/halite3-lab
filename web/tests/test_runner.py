"""Concurrency and ownership invariants for the native-process coordinator."""

import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import builds, runner, settings as S
from backend.db import connect, initialize


def claim_in_process(data, output):
    S.DATA = Path(data)
    match = runner.claim(2, 8)
    output.put(match["id"] if match else None)


def build_in_process(data, seat, output):
    S.DATA = Path(data)
    try:
        directory, info = builds.prepare(seat)
        output.put((str(directory), info["source_sha256"]))
    except Exception as exc:
        output.put(str(exc))


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(S, "DATA", Path(self.temp.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        initialize()
        with connect() as db:
            for name in ("alice", "bob"):
                db.execute("INSERT INTO users(id,username,display_name,password_hash,created_at) VALUES(?,?,?,?,0)", (name, name, name, "unused"))
                db.execute("INSERT INTO jobs(id,owner_id,name,config_json,created_at) VALUES(?,?,?,'{}',0)", (name, name, name))

    def enqueue(self, id, mode=2, owner="alice"):
        with connect() as db:
            db.execute("INSERT INTO matches(id,job_id,owner_id,mode,seed,seat_json,created_at) VALUES(?,?,?,?,11,'[]',0)", (id, owner, owner, mode))

    def complete(self, match):
        with connect() as db:
            db.execute("UPDATE matches SET status='complete',lease_token=NULL WHERE id=?", (match["id"],))

    def test_fairness_capacity_and_large_match_no_starvation(self):
        self.enqueue("a1", 4)
        self.enqueue("a2", 2)
        self.enqueue("b1", 8, "bob")
        first = runner.claim(2, 8)
        self.assertEqual(first["id"], "a1")
        # Bob is next; smaller Alice work cannot bypass his eight-seat match.
        self.assertIsNone(runner.claim(2, 8))
        self.complete(first)
        second = runner.claim(2, 8)
        self.assertEqual(second["id"], "b1")
        self.assertIsNone(runner.claim(2, 8))
        self.complete(second)
        self.assertEqual(runner.claim(2, 8)["id"], "a2")

    def test_finishing_worker_keeps_seat_reservation_until_sandbox_cleanup(self):
        self.enqueue("one", 8)
        self.enqueue("two", 2)
        first = runner.claim(2, 8)
        self.complete(first)
        self.assertIsNone(runner.claim(2, 8, reserved_seats=8))
        self.assertEqual(runner.claim(2, 8)["id"], "two")

    def test_concurrent_claims_reserve_once_and_enforce_both_limits(self):
        for mode in (2, 4):
            with self.subTest(mode=mode):
                with connect() as db:
                    db.execute("DELETE FROM attempts")
                    db.execute("DELETE FROM matches")
                for i in range(6):
                    self.enqueue(str(i), mode)
                context = multiprocessing.get_context("spawn")
                output = context.Queue()
                processes = [context.Process(target=claim_in_process, args=(str(S.DATA), output)) for _ in range(6)]
                for process in processes:
                    process.start()
                values = [output.get(timeout=20) for _ in processes]
                for process in processes:
                    process.join(20)
                    self.assertEqual(process.exitcode, 0)
                    process.close()
                output.close()
                claimed = [value for value in values if value is not None]
                self.assertEqual(len(claimed), 2)
                self.assertEqual(len(set(claimed)), 2)

    def test_crashed_worker_recovery_does_not_touch_other_match_or_completed_result(self):
        self.enqueue("one")
        self.enqueue("two")
        first = runner.claim(2, 8)
        second = runner.claim(2, 8)
        runner.recover(first)
        with connect() as db:
            self.assertEqual(db.execute("SELECT status FROM matches WHERE id='two'").fetchone()[0], "running")
        retried = runner.claim(2, 8)
        self.assertEqual((retried["id"], retried["attempts"]), (first["id"], 2))
        runner.recover(first)  # stale lease cannot undo the replacement
        with connect() as db:
            self.assertTrue(runner.owns(db, retried))
            self.assertTrue(runner.owns(db, second))
        self.complete(retried)
        runner.recover(retried)
        with connect() as db:
            self.assertEqual(db.execute("SELECT status FROM matches WHERE id='one'").fetchone()[0], "complete")

    def test_stale_worker_failure_does_not_publish_logs_or_attempt_status(self):
        self.enqueue("one")
        first = runner.claim()
        runner.recover(first)
        replacement = runner.claim()
        log = S.DATA / "logs/one.json"
        log.write_text("replacement logs")
        with patch.object(runner, "match_eligible", return_value=False), patch.object(runner, "stop_units"):
            self.assertFalse(runner.run_match(first))
        self.assertEqual(log.read_text(), "replacement logs")
        with connect() as db:
            self.assertTrue(runner.owns(db, replacement))
            self.assertEqual(db.execute("SELECT status FROM attempts WHERE match_id='one' AND number=1").fetchone()[0], "interrupted")

    def test_coordinator_renews_during_build_and_reaps_only_dead_worker(self):
        self.enqueue("one")
        self.enqueue("two")
        first = runner.claim(2, 8)
        second = runner.claim(2, 8)
        from unittest.mock import Mock
        live, dead = Mock(), Mock()
        live.is_alive.return_value = True
        dead.is_alive.return_value = False
        workers = {1: (live, first), 2: (dead, second)}
        with connect() as db:
            db.execute("UPDATE matches SET lease_until=1")
        with patch.object(runner, "stop_units") as stop:
            runner.maintain(workers)
        self.assertEqual(list(workers), [1])
        stop.assert_called_once_with(runner.units_for(second))
        with connect() as db:
            self.assertGreater(db.execute("SELECT lease_until FROM matches WHERE id='one'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT status FROM matches WHERE id='two'").fetchone()[0], "queued")

    def test_stale_success_cannot_replace_replay_logs_or_analytics(self):
        from unittest.mock import Mock
        self.enqueue("one")
        participants = [{"name": "example", "version": "1"}] * 2
        with connect() as db:
            db.execute("UPDATE jobs SET config_json=?", (json.dumps(S.MODE_SETUPS[2]),))
            db.execute("UPDATE matches SET seat_json=?", (json.dumps(participants),))
        first = runner.claim()
        runner.recover(first)
        replacement = runner.claim()
        replay = S.DATA / "replays/one.json.gz"
        replay.write_bytes(b"replacement replay")
        logs = S.DATA / "logs/one.json"
        logs.write_text("replacement logs")

        def engine(argv, **kwargs):
            workspace = Path(argv[argv.index("-i") + 1])
            raw_replay = workspace / "test.hlt"
            raw_replay.write_text(json.dumps({"players": [{}, {}], "full_frames": [0, 1, 2]}))
            process = Mock(returncode=0)
            process.communicate.return_value = (json.dumps({"stats": {"0": {"rank": 1}, "1": {"rank": 2}}, "replay": str(raw_replay)}), "")
            process.poll.return_value = 0
            return process

        with patch.object(runner, "match_eligible", return_value=True), patch.object(runner, "prepare", return_value=(S.DATA, {"language": "cpp"})), patch.object(runner.subprocess, "Popen", side_effect=engine), patch.object(runner, "stop_units"), patch.object(runner.analytics, "record") as record:
            self.assertFalse(runner.run_match(first))
        record.assert_not_called()
        self.assertEqual(replay.read_bytes(), b"replacement replay")
        self.assertEqual(logs.read_text(), "replacement logs")
        with connect() as db:
            self.assertTrue(runner.owns(db, replacement))

    def test_shared_cold_cpp_build_is_published_once(self):
        # Both processes request the same immutable C++ version with no cache.
        payload = b'int main(){return 0;}\n'
        key = "blobs/shared.cpp"
        (S.DATA / key).write_bytes(payload)
        seat = {"id": "shared", "owner_id": "alice", "language": "cpp", "object_key": key,
                "sha256": hashlib.sha256(payload).hexdigest(), "filename": "main.cpp"}
        context = multiprocessing.get_context("spawn")
        output = context.Queue()
        processes = [context.Process(target=build_in_process, args=(str(S.DATA), seat, output)) for _ in range(2)]
        for process in processes:
            process.start()
        results = [output.get(timeout=75) for _ in processes]
        for process in processes:
            process.join(20)
            self.assertEqual(process.exitcode, 0)
            process.close()
        output.close()
        self.assertEqual(results, [(str(S.DATA / "blobs/runtime"), seat["sha256"])] * 2)
        info = json.loads((S.DATA / "blobs/build.json").read_text())
        self.assertEqual(info["binary_sha256"], hashlib.sha256((S.DATA / "blobs/runtime/bot").read_bytes()).hexdigest())
        self.assertFalse((S.DATA / "blobs/build-error.json").exists())


if __name__ == "__main__":
    unittest.main()
