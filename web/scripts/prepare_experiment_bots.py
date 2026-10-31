"""Precompile frozen experiment versions in the same native sandbox as matches."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import initialize, connect
from backend.builds import prepare

initialize()
with connect() as db:
    contest=db.execute("SELECT final_job_id FROM contests WHERE slug='test-1'").fetchone()
    seats={seat['id']:seat for row in db.execute('SELECT seat_json FROM matches WHERE job_id=?',(contest['final_job_id'],)) for seat in json.loads(row['seat_json'])}
for vid,seat in sorted(seats.items()):
    _,info=prepare(seat)
    assert info['source_sha256']==seat['sha256']
    print(json.dumps(dict(version_id=vid,source_sha256=info['source_sha256'],language=info['language'],compiler=info.get('compiler'))),flush=True)
