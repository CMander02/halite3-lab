from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import subprocess
import time
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import arena


class ArenaTest(unittest.TestCase):
    def cfg(self):
        cfg = arena.load_config(arena.ROOT/'lab/config/duel.json')
        cfg.update(seeds=[11], turns=4)
        return cfg

    def test_ten_bot_combination_counts(self):
        cfg = arena.load_config(arena.ROOT/'lab/config/league10.json')
        games = list(arena.schedule(cfg))
        self.assertEqual(Counter(spec['mode'] for _,spec in games),{2:45,4:210,8:45})
        self.assertEqual(len({mid for mid,_ in games}),300)
        self.assertTrue(all(len(set(spec['seats'])) == spec['mode'] for _,spec in games))

    def test_cyclic_seats_are_balanced(self):
        cfg = arena.load_config(arena.ROOT/'lab/config/league10.json')
        cfg['rotate_seats'] = True
        games = list(arena.schedule(cfg))
        self.assertEqual(len(games),1290)
        counts = Counter((spec['mode'],name,seat) for _,spec in games for seat,name in enumerate(spec['seats']))
        for mode in cfg['modes']:
            for bot in cfg['bots']:
                self.assertEqual(len({counts[mode,bot['name'],seat] for seat in range(mode)}),1)

    def test_real_matches_resume_without_replaying_completed(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = self.cfg()
            first = arena.run(cfg,temp,jobs=1,limit=1)
            self.assertEqual(first['matches'],{'complete':1,'pending':1})
            db = sqlite3.connect(Path(temp)/'arena.sqlite3')
            old = db.execute("SELECT id,result FROM matches WHERE status='complete'").fetchone()
            second = arena.run(cfg,temp,jobs=2)
            self.assertEqual(second['matches'],{'complete':2})
            self.assertEqual(db.execute('SELECT result FROM matches WHERE id=?',(old[0],)).fetchone()[0],old[1])
            self.assertEqual(db.execute('SELECT sum(attempts) FROM matches').fetchone()[0],2)
            db.close()

    def test_failed_attempt_retries_and_keeps_history(self):
        cfg = self.cfg()
        cfg['rotate_seats'] = False
        with tempfile.TemporaryDirectory() as temp:
            result = {'stats':{'0':{'rank':1,'score':5000},'1':{'rank':2,'score':4000}}}
            with patch.object(arena,'play',side_effect=[RuntimeError('transient test error'),result]):
                summary = arena.run(cfg,temp,jobs=1,max_attempts=2)
            self.assertEqual(summary['matches'],{'complete':1})
            db = sqlite3.connect(Path(temp)/'arena.sqlite3')
            self.assertEqual(db.execute('SELECT status FROM attempts ORDER BY number').fetchall(),[('failed',),('complete',)])
            db.close()

    def test_interrupted_state_is_recovered(self):
        cfg = self.cfg()
        with tempfile.TemporaryDirectory() as temp:
            db = arena.connect(Path(temp)/'arena.sqlite3')
            arena.prepare(db,cfg)
            with db:
                mid = db.execute('SELECT id FROM matches LIMIT 1').fetchone()['id']
                db.execute("UPDATE matches SET status='running',attempts=1 WHERE id=?",(mid,))
                db.execute("INSERT INTO attempts VALUES(?,1,'running','interrupted-dir',NULL)",(mid,))
            arena.prepare(db,cfg)
            row = db.execute('SELECT status,attempts FROM matches WHERE id=?',(mid,)).fetchone()
            self.assertEqual(tuple(row),('pending',1))
            self.assertEqual(db.execute('SELECT status FROM attempts').fetchone()['status'],'interrupted')
            db.close()
            summary = arena.run(cfg,temp,jobs=2)
            self.assertEqual(summary['matches'],{'complete':2})

    def test_config_and_source_changes_rejected(self):
        cfg = self.cfg()
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'bot.py'
            source.write_text('# version one')
            cfg['bots'][0]['sources'] += [str(source)]
            db = arena.connect(Path(temp)/'arena.sqlite3')
            arena.prepare(db,cfg)
            cfg['turns'] += 1
            with self.assertRaisesRegex(ValueError,'changed'):
                arena.prepare(db,cfg)
            cfg['turns'] -= 1
            source.write_text('# version two')
            with self.assertRaisesRegex(ValueError,'changed'):
                arena.prepare(db,cfg)
            db.close()

    def test_hard_killed_coordinator_resumes_match(self):
        cfg = self.cfg()
        cfg['rotate_seats'] = False
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            marker = temp/'entered'
            bot = temp/'pause_once.py'
            bot.write_text("import json,sys,time\nfrom pathlib import Path\n"
                           "init=json.loads(sys.stdin.readline())\n"
                           f"marker=Path({str(marker)!r})\n"
                           "if not marker.exists():\n marker.write_text('ready')\n time.sleep(20)\n"
                           "print('pause-once',flush=True)\n"
                           "for line in sys.stdin: print('',flush=True)\n")
            for item in cfg['bots']:
                item['command'] = [sys.executable,str(bot)]
                item['sources'] = [str(bot)]
            config = temp/'config.json'
            config.write_text(json.dumps(cfg))
            directory = temp/'run'
            command = [sys.executable,str(arena.ROOT/'lab/arena.py'),'run',str(config),'--out',str(directory),'--jobs','1']
            proc = subprocess.Popen(command,cwd=arena.ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
            try:
                deadline = time.monotonic()+10
                while not marker.exists() and time.monotonic()<deadline and proc.poll() is None:
                    time.sleep(0.01)
                self.assertTrue(marker.exists())
                children = []
                for task in Path(f'/proc/{proc.pid}/task').iterdir():
                    children += [int(pid) for pid in (task/'children').read_text().split()]
                self.assertTrue(children)
                proc.kill()
                proc.communicate(timeout=5)
                deadline = time.monotonic()+5
                while time.monotonic()<deadline:
                    live = [pid for pid in children if Path(f'/proc/{pid}/stat').exists()
                            and Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0] != 'Z']
                    if not live:
                        break
                    time.sleep(0.01)
                self.assertFalse(live,'Engine survived coordinator death')
                resumed = subprocess.run(command,cwd=arena.ROOT,capture_output=True,text=True,timeout=15)
                self.assertEqual(resumed.returncode,0,resumed.stderr+resumed.stdout)
                db = sqlite3.connect(directory/'arena.sqlite3')
                self.assertEqual(db.execute('SELECT status,attempts FROM matches').fetchone(),('complete',2))
                self.assertEqual(db.execute('SELECT status FROM attempts ORDER BY number').fetchall(),[('interrupted',),('complete',)])
                db.close()
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()

    def test_concurrent_status_reports_publish_valid_json(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            db = arena.connect(directory/'arena.sqlite3')
            arena.prepare(db,self.cfg())
            db.close()
            def publish(_):
                local = arena.connect(directory/'arena.sqlite3')
                try:
                    return arena.report(local,directory)
                finally:
                    local.close()
            with ThreadPoolExecutor(max_workers=4) as pool:
                reports = list(pool.map(publish,range(24)))
            self.assertEqual(json.loads((directory/'summary.json').read_text()),reports[0])

    def test_timeout_kills_process_and_saves_logs(self):
        cfg = self.cfg()
        cfg.update(timeout=0.001,rotate_seats=False)
        with tempfile.TemporaryDirectory() as temp:
            summary = arena.run(cfg,temp,jobs=1,max_attempts=1)
            self.assertEqual(summary['matches'],{'failed':1})
            files = list((Path(temp)/'matches').glob('*/attempt-1/stderr.log'))
            self.assertEqual(len(files),1)


if __name__ == '__main__':
    unittest.main()
