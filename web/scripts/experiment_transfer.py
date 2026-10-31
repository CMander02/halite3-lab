"""Create, export and import #1 through explicit, idempotent operations.

The remote database contains only the chosen versions, dummy account hashes and
this experiment's queue. No live credentials, traces or unrelated bots leave the host.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import experiments as E, settings as S, contests
from backend.db import connect, initialize, now


def insert(db, table, row, replace=False):
    keys=list(row)
    db.execute(f"INSERT {'OR REPLACE ' if replace else ''}INTO {table}({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",[row[k] for k in keys])


def export(destination):
    destination=Path(destination).resolve()
    if destination.exists():
        raise RuntimeError('Export destination must be new; never overwrite a running queue')
    source=S.DATA
    with connect() as db:
        contest=dict(db.execute('SELECT * FROM contests WHERE slug=?',(E.SLUG,)).fetchone())
        job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(contest['final_job_id'],)).fetchone())
        matches=[dict(r) for r in db.execute('SELECT * FROM matches WHERE job_id=? ORDER BY rowid',(job['id'],))]
        seats={seat['id']:seat for row in matches for seat in json.loads(row['seat_json'])}
        owners={s['owner_id'] for s in seats.values() if s['owner_id']}|{job['owner_id']}
        users=[dict(db.execute('SELECT id,username,display_name,created_at FROM users WHERE id=?',(uid,)).fetchone()) for uid in owners]
        bots=[dict(db.execute('SELECT id,owner_id,name,builtin,created_at FROM bots WHERE id=?',(bid,)).fetchone()) for bid in {s['bot_id'] for s in seats.values()}]
        versions=[dict(db.execute('SELECT id,bot_id,version,object_key,sha256,filename,size,language,created_at FROM versions WHERE id=?',(vid,)).fetchone()) for vid in seats]
        entries=[dict(r) for r in db.execute('SELECT * FROM contest_entries WHERE contest_id=?',(contest['id'],))]
    destination.mkdir(mode=0o700,parents=True)
    try:
        S.DATA=destination
        initialize()
        with connect() as db:
            for user in users:
                user['password_hash']='remote-account-disabled'
                insert(db,'users',user)
            for row in bots:
                if row['builtin']:continue
                insert(db,'bots',row)
            for row in versions:
                insert(db,'versions',row,replace=True)
                relative=Path(row['object_key'])
                if relative.is_absolute() or '..' in relative.parts:raise RuntimeError('Invalid source path')
                target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                payload=(source/relative).read_bytes()
                if hashlib.sha256(payload).hexdigest()!=row['sha256']:raise RuntimeError('Source hash mismatch')
                target.write_bytes(payload);target.chmod(0o600)
            insert(db,'contests',contest)
            insert(db,'jobs',job)
            for entry in entries:insert(db,'contest_entries',entry)
            for row in matches:
                if row['status'] not in E.REMOTE_PENDING:raise RuntimeError('Export only before execution starts')
                row['status']='queued';row['attempts']=0
                insert(db,'matches',row)
        manifest=dict(contest_id=contest['id'],job_id=job['id'],engine_sha256=hashlib.sha256(S.ENGINE.read_bytes()).hexdigest(),
                      matches=len(matches),sources=[dict(id=v['id'],sha256=v['sha256']) for v in versions])
        (destination/'manifest.json').write_text(json.dumps(manifest,indent=2))
        (destination/'arena.sqlite3').chmod(0o600)
    finally:
        S.DATA=source
    return manifest


def import_results(download):
    download=Path(download).resolve()
    manifest=json.loads((download/'manifest.json').read_text())
    remote=sqlite3.connect(f"file:{download/'snapshot.sqlite3'}?mode=ro",uri=True);remote.row_factory=sqlite3.Row
    imported=0
    with connect() as db:
        contest=db.execute('SELECT * FROM contests WHERE id=? AND number=1',(manifest['contest_id'],)).fetchone()
        if not contest or contest['final_job_id']!=manifest['job_id']:raise RuntimeError('Experiment identity mismatch')
        job=db.execute('SELECT config_json FROM jobs WHERE id=?',(manifest['job_id'],)).fetchone()
        config=json.loads(job['config_json'])
        for row in remote.execute('SELECT * FROM matches WHERE job_id=? ORDER BY rowid',(manifest['job_id'],)):
            local=db.execute('SELECT * FROM matches WHERE id=? AND job_id=?',(row['id'],manifest['job_id'])).fetchone()
            if not local:raise RuntimeError('Unexpected remote match')
            if local['status']=='complete':continue
            if json.loads(local['seat_json'])!=json.loads(row['seat_json']):raise RuntimeError('Frozen seats changed')
            if row['status'] in ('queued','running'):
                db.execute('UPDATE matches SET status=?,attempts=?,started_at=? WHERE id=? AND status IN (?,?)',
                    ('remote_'+row['status'],row['attempts'],row['started_at'],row['id'],*E.REMOTE_PENDING))
                continue
            if row['status']=='failed':
                db.execute("UPDATE matches SET status='failed',attempts=?,error=?,finished_at=? WHERE id=?",(row['attempts'],row['error'],row['finished_at'],row['id']))
                continue
            if row['status']!='complete':continue
            result=json.loads(row['result_json'])
            if result.get('engine_sha256')!=manifest['engine_sha256']:raise RuntimeError('Engine hash mismatch')
            key=f"replays/{row['id']}.json.gz"
            if row['replay_key']!=key:raise RuntimeError('Unexpected replay path')
            setup=config['setups_by_seed'][f"{row['mode']}:{row['seed']}"]
            replay_file=download/key
            with gzip.open(replay_file,'rt') as stream:replay=json.load(stream)
            if (replay['production_map']['width'],replay['production_map']['height'])!=(setup['width'],setup['height']):raise RuntimeError('Map dimensions mismatch')
            if replay['map_generator_seed']!=setup['map_seed']:raise RuntimeError('Map seed mismatch')
            if any(replay['GAME_CONSTANTS'].get(k)!=v for k,v in setup['rules'].items()):raise RuntimeError('Rules mismatch')
            if len(result.get('stats',{}))!=row['mode']:raise RuntimeError('Incomplete seats')
            if not 0 <= result['turns'] <= setup['turns']:raise RuntimeError('Turn limit mismatch')
            target=S.DATA/key;target.parent.mkdir(exist_ok=True)
            temporary=target.with_suffix('.import.tmp');shutil.copyfile(replay_file,temporary);temporary.chmod(0o600);temporary.replace(target)
            db.execute("UPDATE matches SET status='complete',attempts=?,result_json=?,replay_key=?,finished_at=?,started_at=?,error=NULL WHERE id=?",
                (row['attempts'],row['result_json'],key,row['finished_at'],row['started_at'],row['id']))
            players=remote.execute('SELECT * FROM match_players WHERE match_id=?',(row['id'],)).fetchall()
            summary=remote.execute('SELECT * FROM match_rule_stats WHERE match_id=?',(row['id'],)).fetchone()
            if len(players)!=row['mode'] or not summary:raise RuntimeError('Remote diagnostics missing')
            db.execute('DELETE FROM match_players WHERE match_id=?',(row['id'],))
            for player in players:insert(db,'match_players',dict(player))
            insert(db,'match_rule_stats',dict(summary),replace=True)
            imported+=1
        pending=db.execute("SELECT COUNT(*) FROM matches WHERE job_id=? AND status IN ('remote_queued','remote_running')",(manifest['job_id'],)).fetchone()[0]
        failed=db.execute("SELECT COUNT(*) FROM matches WHERE job_id=? AND status='failed'",(manifest['job_id'],)).fetchone()[0]
        if not pending and not failed and not contest['finalized_at']:
            contests.finalize(db,contest)
    remote.close()
    return dict(imported=imported,pending=pending,failed=failed)


def promote(staging):
    remote=sqlite3.connect(f'file:{Path(staging).resolve()}?mode=ro',uri=True);remote.row_factory=sqlite3.Row
    contest=dict(remote.execute('SELECT * FROM contests WHERE slug=?',(E.SLUG,)).fetchone())
    config=json.loads(contest['config_json'])
    if not config.get('experimental') or contest['number']!=1:raise RuntimeError('Expected frozen contest #1')
    with connect() as db:
        existing=db.execute('SELECT id FROM contests WHERE number=1 OR slug=?',(E.SLUG,)).fetchone()
        if existing:
            if existing['id']!=contest['id']:raise RuntimeError('Contest #1 already in use')
            return dict(contest_id=contest['id'],existing=True)
        for version in config['roster']:
            row=db.execute('SELECT sha256 FROM versions WHERE id=?',(version['version_id'],)).fetchone()
            if not row or row['sha256']!=version['sha256']:raise RuntimeError('Version identity changed')
        contest['finalized_at']=None;contest['standings_json']=None
        insert(db,'contests',contest)
        job=dict(remote.execute('SELECT * FROM jobs WHERE id=?',(contest['final_job_id'],)).fetchone())
        insert(db,'jobs',job)
        for row in remote.execute('SELECT * FROM contest_entries WHERE contest_id=?',(contest['id'],)):
            insert(db,'contest_entries',dict(row))
        for row in remote.execute('SELECT * FROM matches WHERE job_id=? ORDER BY rowid',(job['id'],)):
            item=dict(row);item.update(status='remote_queued',attempts=0,replay_key=None,result_json=None,finished_at=None,started_at=None,lease_token=None,lease_until=None)
            insert(db,'matches',item)
    remote.close()
    return dict(contest_id=contest['id'],existing=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['create','export','import','promote','status']);p.add_argument('path',nargs='?');a=p.parse_args()
    if a.action=='create':
        initialize()
        with connect() as db:value={'contest_id':E.create(db)}
    elif a.action=='export':value=export(a.path)
    elif a.action=='import':value=import_results(a.path)
    elif a.action=='promote':value=promote(a.path)
    else:
        with connect() as db:
            c=db.execute('SELECT * FROM contests WHERE slug=?',(E.SLUG,)).fetchone()
            value=dict(contest_id=c['id'],job_id=c['final_job_id'],progress=contests.stage_progress(db,c,'final')) if c else None
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':main()
