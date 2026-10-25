# opus55-high bot notes (CMA-252)

Build: `g++ -std=c++17 -O2 -pipe bot.cpp -o bot`. Test: `./suite.sh` (12 games: seeds 11/29/47 x both seats x baseline/raider, 32x32, 200 turns, lab rules). Tunables via env `B_*` (defaults are the tuned values).

## Strategy
- Fog memory: last-seen halite per cell; first sighting also seeds the x-mirrored cell (x0.6); never-seen cells = 0.8 x mean known.
- Targets: global greedy assignment of (ship, cell) by gain/(dist + 1.5 + 0.25*dist_home), unique cells; inspiration bonus where >=2 enemies within r4.
- Moves: Kuhn-style matching over per-ship ranked moves (no self-collisions, swaps allowed); forced-stay ships first, then returning ships.
- Light-ship rules: penalty for cells reachable by an enemy of weight <= mine; bonus for light ships (<200) moving onto heavy enemies' cells / predicted next step toward their base (max 2 hunters per enemy).
- Return at 920 cargo (or 700 on poor cells); endgame recall at turns_left <= dist_home; final 2 turns ships adjacent to base crash in (empty keeper on base steals and deposits).
- Spawn while turn <= 95, ships < 20 and estimated map halite / (ships+1) > 7000; no spawn if own ship lands on the factory or an empty enemy can reach it.

## Tuning log (wins / 12, sum of score margins)
| config | wins | sumdiff |
|---|---|---|
| v1 (spawn to turn 125, cap 40, dropoff) | 3 seat-0 losses of 6 vs raider | - |
| spawn<=95, cap 20, dropoff on | 10 | 53.5k |
| + halite/ship spawn gate K=6000 | 12 | 68.3k |
| K=7000, queue margin 0 | 12 | 74.1k |
| + dropoff off | 12 | 78.4k |
| + hunt weight x2 (final) | 12 | 89.3k |
Others tried: spawn 80/110, cap 15/26, return 850/980, hunt 0/3x/4x — all equal or worse.

## Final local results (my seat in brackets)
| opp | seed | seat0 (me p0) | seat1 (me p1) |
|---|---|---|---|
| baseline | 11 | W 20438-9263 | W 19724-10697 |
| baseline | 29 | W 26754-10121 | W 23565-3874 |
| baseline | 47 | W 28271-19389 | W 29659-20634 |
| raider | 11 | W 16046-14797 | W 16412-15605 |
| raider | 29 | W 22983-19505 | W 26019-18994 |
| raider | 47 | W 25605-23797 | W 24611-24146 |

Held-out vs raider (seeds 5/77/123): 4/6 wins (lost s5 seat1, s123 seat0) -> some overfitting risk.
Speed: ~1 ms/turn (200-turn self-play: 0.29 s user total).
