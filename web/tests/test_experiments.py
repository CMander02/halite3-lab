import hashlib
import json
from pathlib import Path
import sqlite3
import importlib.util
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend import experiments as E, settings as S, rating
from backend.api import app
from backend.db import connect, initialize
from backend.runner import claim


class ExperimentTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=S.DATA;S.DATA=Path(self.temp.name)
        initialize();self.client=TestClient(app);self.addCleanup(self.cleanup)
        source=b'int main(){}';digest=hashlib.sha256(source).hexdigest()
        with connect() as db:
            db.execute("INSERT INTO users(id,username,display_name,password_hash,created_at,is_admin) VALUES('u','cmander','CMander','disabled',0,1)")
            db.execute("INSERT INTO jobs(id,name,kind,config_json,created_at) VALUES('rank-j','rank','ranked','{}',0)")
            for i in range(8):
                db.execute("INSERT INTO bots(id,owner_id,name,created_at) VALUES(?,'u',?,0)",(f'b{i}',f'bot-{i}'))
                key=f'blobs/{i}.cpp';(S.DATA/key).write_bytes(source)
                db.execute("INSERT INTO versions(id,bot_id,version,object_key,sha256,filename,size,created_at,language) VALUES(?,?,'1',?,?,'bot.cpp',12,0,'cpp')",
                           (f'v{i}',f'b{i}',key,digest))
                for j in range(12):
                    db.execute("INSERT INTO matches(id,job_id,mode,seed,seat_json,status,public,result_json,created_at,finished_at) VALUES(?,'rank-j',2,11,?,'complete',1,?,0,100)",
                        (f'{i}-{j}',json.dumps([dict(id=f'v{i}'),dict(id='builtin-baseline-v1')]),json.dumps(dict(stats={'0':dict(rank=1),'1':dict(rank=2)}))))
        rating._cache['key']=None

    def cleanup(self):
        self.client.close();S.DATA=self.old;self.temp.cleanup();rating._cache['key']=None

    def test_schedule_covers_rules_modes_baselines_and_every_seat(self):
        cases=E.scenarios();self.assertEqual(len(cases),28)
        self.assertEqual(len({c['match_seeds'][0] for c in cases}),28)
        players=[dict(id=f'v{i}') for i in range(8)];targets=[dict(id='base'),dict(id='raider')]
        games=E.tables(players,targets);self.assertEqual(len(games),80)
        for mode in (2,4,8):
            for bot in players:
                positions={i for group in games if len(group)==mode for i,p in enumerate(group) if p==bot}
                self.assertEqual(positions,set(range(mode)))
                for target in targets:
                    self.assertTrue(any(bot in g and target in g for g in games if len(g)==mode))
        self.assertEqual(cases[0]['setups']['8']['rules']['MAX_ENERGY'],15)
        self.assertEqual(cases[1]['setups']['8']['turns'],200)

    def test_creation_is_idempotent_remote_queue_cannot_be_claimed_locally(self):
        with connect() as db:
            first=E.create(db);second=E.create(db)
            self.assertEqual(first,second)
            contest=db.execute('SELECT * FROM contests WHERE id=?',(first,)).fetchone()
            self.assertEqual(db.execute('SELECT COUNT(*) FROM contest_entries WHERE contest_id=?',(first,)).fetchone()[0],8)
            self.assertEqual(len(E.contests.finalists(db,first)),8)
            counts=dict(db.execute('SELECT status,COUNT(*) FROM matches WHERE job_id=? GROUP BY status',(contest['final_job_id'],)))
            self.assertEqual(counts,{'remote_queued':2240})
        self.assertIsNone(claim())
        response=self.client.get('/api/contests/test-1/experiments')
        self.assertEqual(response.status_code,200,response.text)
        value=response.json();self.assertEqual(value['execution_host'],'txcloud')
        self.assertEqual(value['progress']['counts']['queued'],2240)
        self.assertEqual(len(value['roster']),8)
        self.assertEqual(self.client.get('/api/contests/test-1/standings?stage=final').status_code,200)
        detail=self.client.get('/api/contests/test-1').json()
        self.assertIn('规则实验与固定 Bot',detail['rules_text'])
        self.assertNotIn('地图上下、左右都环绕',detail['rules_text'])
        self.assertEqual(self.client.get('/api/contests/test-1/experiments?scenario=unknown').status_code,422)

    def test_experimental_results_do_not_change_global_rating_or_matrix(self):
        with connect() as db:
            before=rating.ratings(db)
            E.create(db)
            c=db.execute("SELECT * FROM contests WHERE number=1").fetchone()
            row=db.execute('SELECT * FROM matches WHERE job_id=? LIMIT 1',(c['final_job_id'],)).fetchone()
            ids=[s['id'] for s in json.loads(row['seat_json'])]
            db.execute("UPDATE matches SET status='complete',result_json=?,finished_at=200 WHERE id=?",
                       (json.dumps(dict(stats={str(i):dict(rank=i+1,score=0) for i in range(len(ids))})),row['id']))
            rating._cache['key']=None
            after=rating.ratings(db)
            self.assertEqual(before,after)
        stats=self.client.get('/api/leaderboard/stats').json()
        self.assertFalse(stats['entries'])

    def test_remote_export_has_only_frozen_versions_and_no_live_auth(self):
        path=Path(__file__).resolve().parents[1]/'scripts/experiment_transfer.py'
        spec=importlib.util.spec_from_file_location('experiment_transfer_test',path)
        transfer=importlib.util.module_from_spec(spec);spec.loader.exec_module(transfer)
        with connect() as db:
            E.create(db)
        before=S.DATA
        target=S.DATA/'remote-export'
        manifest=transfer.export(target)
        self.assertEqual(S.DATA,before)
        self.assertEqual(len(manifest['sources']),10)
        self.assertEqual(manifest['matches'],2240)
        d=sqlite3.connect(target/'arena.sqlite3')
        self.assertEqual(d.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],0)
        self.assertEqual(d.execute('SELECT COUNT(*) FROM api_tokens').fetchone()[0],0)
        self.assertEqual(d.execute('SELECT DISTINCT password_hash FROM users').fetchall(),[('remote-account-disabled',)])
        self.assertEqual(d.execute('SELECT COUNT(*) FROM matches').fetchone()[0],2240)
        self.assertEqual(d.execute('SELECT DISTINCT status FROM matches').fetchall(),[('queued',)])
        d.close()


if __name__=='__main__':unittest.main()
