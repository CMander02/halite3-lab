#!/bin/bash
# usage: run.sh seed botA_cmd botB_cmd  (cwd = halite3-lab root, like the arena)
R=/home/cmander/Project/halite3-lab
D=/home/cmander/Project/halite3-lab-bot/bots/opus55-high
cd $R
seed=$1; a=$2; b=$3
out=$(./build/halite --results-as-json --no-compression --width 32 --height 32 --seed $seed --turn-limit 200 --constants-file lab/config/rules.json --replay-directory $D/replays "$a" "$b" 2>/dev/null)
echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); s=d['stats']; print(' '.join(f\"p{k}:rank{v['rank']}:{v['score']}\" for k,v in sorted(s.items())), d.get('terminated') or '')"
