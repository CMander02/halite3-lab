"""Archive the original execution and start a complete, separately ranked batch."""
import copy
import json
import uuid
from .db import now


def fast500(db, engine_sha256, workers=2, cpu_percent=100, worker_cpus=None):
    if len(engine_sha256) != 64 or not 1 <= workers <= 4 or not 35 <= cpu_percent <= 100:
        raise ValueError('Invalid execution budget')
    if worker_cpus is not None and (len(worker_cpus)!=workers or len(set(worker_cpus))!=workers or any(c<0 for c in worker_cpus)):
        raise ValueError('Each worker needs a distinct CPU')
    contest = db.execute("SELECT * FROM contests WHERE slug='test-1'").fetchone()
    config = json.loads(contest['config_json'])
    if config.get('active_batch') == 'fast500':
        active=next(b for b in config['execution_batches'] if b['key']=='fast500')
        if (active['engine_sha256'],active['workers'],active['bot_cpu_percent'],active.get('worker_cpus')) != (engine_sha256,workers,cpu_percent,worker_cpus):
            raise RuntimeError('The active execution profile is immutable')
        return contest['final_job_id']
    old_id = contest['final_job_id']
    old = dict(db.execute('SELECT * FROM jobs WHERE id=?',(old_id,)).fetchone())
    old_config = json.loads(old['config_json'])
    rows = [dict(r) for r in db.execute('SELECT * FROM matches WHERE job_id=? ORDER BY rowid',(old_id,))]
    if len(rows) != 2240 or any(r['status'] not in ('complete','queued','remote_queued') for r in rows):
        raise RuntimeError('Drain the original batch; all completed games must remain intact')
    timestamp = now()
    new_id = str(uuid.uuid4())
    execution = dict(turn_timeout_ms=500,bot_cpu_percent=cpu_percent,bot_slice='halite3game1.slice',
                     execution_batch='fast500',engine_sha256=engine_sha256)
    job_config = copy.deepcopy(old_config)
    job_config.update(execution)
    if worker_cpus is not None:job_config['worker_cpus']=worker_cpus
    new = dict(old,id=new_id,name='#1 · 500 ms · txcloud',config_json=json.dumps(job_config),created_at=timestamp)
    keys=list(new)
    db.execute(f"INSERT INTO jobs({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",[new[k] for k in keys])
    for row in rows:
        row.update(id=str(uuid.uuid4()),job_id=new_id,status='queued',attempts=0,lease_token=None,lease_until=None,
                   error=None,replay_key=None,result_json=None,created_at=timestamp,started_at=None,finished_at=None)
        keys=list(row)
        db.execute(f"INSERT INTO matches({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",[row[k] for k in keys])
    db.execute("UPDATE matches SET status='cancelled' WHERE job_id=? AND status IN ('queued','remote_queued')",(old_id,))
    config.update(active_batch='fast500',execution_batches=[
        dict(key='legacy2000',label='已保留旧批次 · 2000 ms',job_id=old_id,turn_timeout_ms=2000,bot_cpu_percent=35,archived=True),
        dict(key='fast500',label='新批次 · 500 ms',job_id=new_id,turn_timeout_ms=500,bot_cpu_percent=cpu_percent,
             workers=workers,worker_cpus=worker_cpus,engine_sha256=engine_sha256,archived=False)],
        execution_host='txcloud')
    db.execute('UPDATE contests SET final_job_id=?,config_json=?,standings_json=NULL,finalized_at=NULL WHERE id=?',
               (new_id,json.dumps(config),contest['id']))
    return new_id
