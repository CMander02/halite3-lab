"""Protocol fixture: issue directions by own ship order, optionally record input."""
import json
from pathlib import Path
import sys

plan = json.loads(sys.argv[1])
trace = Path(sys.argv[2]) if len(sys.argv) > 2 else None
init = json.loads(sys.stdin.readline())
me = init['player_id']
if trace:
    trace.write_text(json.dumps(init)+'\n')
print('scripted', flush=True)
for line in sys.stdin:
    obs = json.loads(line)
    if trace:
        with trace.open('a') as stream:
            stream.write(line)
    own = next(p for p in obs['players'] if p['id'] == me)
    actions = plan.get(str(obs['turn']), [])
    if actions == 'spawn':
        print('g', flush=True)
    else:
        print(' '.join(f"m {s['id']} {d}" for s, d in zip(sorted(own['ships'], key=lambda s:s['id']), actions)), flush=True)
