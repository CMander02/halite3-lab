#!/bin/bash
# runs all 12 games; env vars pass through to bot. prints per-game line + win count
D=/home/cmander/Project/halite3-lab-bot/bots/opus55-high
B="$D/bot"
run1(){ s=$1; opp=$2; seat=$3
  if [ $seat = 0 ]; then r=$($D/run.sh $s "$B" "python3 lab/bots/$opp.py"); me=p0; else r=$($D/run.sh $s "python3 lab/bots/$opp.py" "$B"); me=p1; fi
  echo "$opp seed$s seat$seat $r" ; }
for opp in baseline raider; do for s in 11 29 47; do for seat in 0 1; do run1 $s $opp $seat & done; done; wait; done > $D/last_suite.txt
cat $D/last_suite.txt | sort
python3 - $D/last_suite.txt <<'PY'
import sys,re
w=0;n=0;diff=0
for l in open(sys.argv[1]):
    seat=int(re.search(r'seat(\d)',l).group(1)); sc={int(a):(int(b),int(c)) for a,b,c in re.findall(r'p(\d):rank(\d):(\d+)',l)}
    n+=1; w+= sc[seat][0]==1; diff+=sc[seat][1]-sc[1-seat][1]
print('wins',w,'/',n,'sumdiff',diff)
PY
