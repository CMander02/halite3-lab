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
        public_matches=self.client.get('/api/matches?contest=test-1').json()['matches']
        self.assertTrue(public_matches)
        for match in public_matches:
            self.assertEqual(match['seed'],11)
            self.assertNotIn('job_config_json',match)
        match=self.client.get('/api/matches/'+public_matches[0]['id']).json()
        self.assertEqual(match['seed'],11)
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

    def test_new_batch_preserves_completed_rows_and_separates_rankings(self):
        from backend.experiment_batches import fast500
        with connect() as db:
            E.create(db)
            c=db.execute("SELECT * FROM contests WHERE number=1").fetchone()
            old_id=c['final_job_id']
            old=db.execute('SELECT * FROM matches WHERE job_id=? ORDER BY rowid LIMIT 1',(old_id,)).fetchone()
            db.execute("UPDATE matches SET status='complete',result_json=? WHERE id=?",(json.dumps(dict(stats={'0':dict(rank=1,score=100),'1':dict(rank=2,score=0)})),old['id']))
            before=dict(db.execute('SELECT * FROM matches WHERE id=?',(old['id'],)).fetchone())
            new_id=fast500(db,'a'*64,3)
            self.assertEqual(new_id,fast500(db,'a'*64,3))
            with self.assertRaisesRegex(RuntimeError,'immutable'):
                fast500(db,'b'*64,3)
            self.assertEqual(before,dict(db.execute('SELECT * FROM matches WHERE id=?',(old['id'],)).fetchone()))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM matches WHERE job_id=? AND status='cancelled'",(old_id,)).fetchone()[0],2239)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM matches WHERE job_id=?',(new_id,)).fetchone()[0],2240)
            row=db.execute('SELECT * FROM matches WHERE job_id=? ORDER BY rowid LIMIT 1',(new_id,)).fetchone()
            db.execute("UPDATE matches SET status='complete',result_json=? WHERE id=?",(json.dumps(dict(stats={'0':dict(rank=2,score=10),'1':dict(rank=1,score=20)})),row['id']))
        fast=self.client.get('/api/contests/test-1/experiments').json()
        old=self.client.get('/api/contests/test-1/experiments?batch=legacy2000').json()
        self.assertEqual(fast['selected_batch']['turn_timeout_ms'],500)
        self.assertEqual(old['selected_batch']['turn_timeout_ms'],2000)
        vid=json.loads(before['seat_json'])[0]['id']
        self.assertEqual(next(v for v in fast['standings']['2'] if v['version_id']==vid)['mean_score'],10)
        self.assertEqual(next(v for v in old['standings']['2'] if v['version_id']==vid)['mean_score'],100)
        self.assertEqual(self.client.get('/api/contests/test-1/experiments?batch=missing').status_code,422)

    def test_adopting_batch_is_idempotent_and_preserves_completed_games(self):
        from backend.experiment_batches import fast500
        path=Path(__file__).resolve().parents[1]/'scripts/experiment_transfer.py'
        spec=importlib.util.spec_from_file_location('experiment_transfer_adopt_test',path)
        transfer=importlib.util.module_from_spec(spec);spec.loader.exec_module(transfer)
        with connect() as db:
            E.create(db)
            old_id=db.execute("SELECT final_job_id FROM contests WHERE number=1").fetchone()[0]
            mid=db.execute('SELECT id FROM matches WHERE job_id=? ORDER BY rowid LIMIT 1',(old_id,)).fetchone()[0]
            db.execute("UPDATE matches SET status='complete',result_json='{}' WHERE id=?",(mid,))
            frozen=dict(db.execute('SELECT * FROM matches WHERE id=?',(mid,)).fetchone())
        snapshot=S.DATA/'transition.sqlite3'
        with sqlite3.connect(S.DATA/'arena.sqlite3') as source, sqlite3.connect(snapshot) as target:source.backup(target)
        with sqlite3.connect(snapshot) as remote:
            remote.row_factory=sqlite3.Row
            new_id=fast500(remote,'a'*64,3)
        with self.assertRaisesRegex(RuntimeError,'hash mismatch'):transfer.adopt_batch(snapshot,'b'*64)
        self.assertFalse(transfer.adopt_batch(snapshot,'a'*64)['existing'])
        self.assertTrue(transfer.adopt_batch(snapshot,'a'*64)['existing'])
        with connect() as db:
            self.assertEqual(frozen,dict(db.execute('SELECT * FROM matches WHERE id=?',(mid,)).fetchone()))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM matches WHERE job_id=? AND status='remote_queued'",(new_id,)).fetchone()[0],2240)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM matches WHERE job_id=? AND status='cancelled'",(old_id,)).fetchone()[0],2239)
        self.assertIsNone(claim())

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
