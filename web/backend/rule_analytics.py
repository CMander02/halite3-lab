"""Versioned rule diagnostics. Replay work happens at completion/offline, never in GETs.

Frames contain start-of-turn ships and end-of-turn cell deltas. Reconstruct
movement and process actual events in order, including deposit before spawning.
Unknown collision reconstructions are counted, not guessed.
"""
from collections import Counter, defaultdict
import json
import math
import time
from fastapi import APIRouter, HTTPException
from .db import connect
from .rating import board

router = APIRouter()
SCHEMA = 1
BINS = ['0', '1–99', '100–249', '250–499', '500–999', '1000+']
DIRECTIONS = {'n': (0, -1), 's': (0, 1), 'e': (1, 0), 'w': (-1, 0)}


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS match_rule_stats (
        match_id TEXT PRIMARY KEY REFERENCES matches(id), schema_version INTEGER NOT NULL,
        summary_json TEXT NOT NULL)''')


def analyze(replay):
    constants = replay['GAME_CONSTANTS']
    terrain = replay['production_map']
    width, height = terrain['width'], terrain['height']
    grid = [cell['energy'] for row in terrain['grid'] for cell in row]
    reefs = {(x, y) for y, row in enumerate(terrain['grid']) for x, c in enumerate(row) if c.get('reef')}
    structures = {(p['factory_location']['x'], p['factory_location']['y']): p['player_id'] for p in replay['players']}
    initial = sum(grid)
    seats = [dict(ship_turns=0, moving_turns=0, cargo_bins=[0] * len(BINS), peak_ships=0) for _ in replay['players']]
    collisions = Counter()
    unknown = 0
    frames = replay['full_frames']
    for frame in frames:
        events = frame.get('events', [])
        # A final snapshot has no actions/events and must not add another ship-turn.
        terminal = frame is frames[-1]
        ships = {int(sid): dict(ship, pid=int(pid), moved=False, born=False, start=ship['energy'])
                 for pid, group in frame.get('entities', {}).items() for sid, ship in group.items()}
        if not terminal:
            for pid, group in frame.get('entities', {}).items():
                seat = seats[int(pid)]
                seat['peak_ships'] = max(seat['peak_ships'], len(group))
                for ship in group.values():
                    value = ship['energy']
                    bucket = 0 if value == 0 else 1 if value < 100 else 2 if value < 250 else 3 if value < 500 else 4 if value < 1000 else 5
                    seat['cargo_bins'][bucket] += 1
                    seat['ship_turns'] += 1
        for event in events:
            if event['type'] == 'construct':
                loc = event['location']
                structures[loc['x'], loc['y']] = event['owner_id']
                grid[loc['y'] * width + loc['x']] = 0
                ships.pop(int(event['id']), None)
        for pid, moves in frame.get('moves', {}).items():
            seen = set()
            for move in moves:
                sid = move.get('id')
                if move['type'] != 'm' or sid not in ships or sid in seen or ships[sid]['pid'] != int(pid):
                    continue
                seen.add(sid)
                ship = ships[sid]
                direction = DIRECTIONS.get(move.get('direction'))
                if not direction:
                    continue
                ratio = constants.get('INSPIRED_MOVE_COST_RATIO', 10) if ship.get('is_inspired') else constants.get('MOVE_COST_RATIO', 10)
                cost = grid[ship['y'] * width + ship['x']] // ratio
                x, y = (ship['x'] + direction[0]) % width, (ship['y'] + direction[1]) % height
                if ship['energy'] >= cost and (x, y) not in reefs:
                    ship.update(x=x, y=y, energy=ship['energy'] - cost, moved=True)
                    seats[ship['pid']]['moving_turns'] += 1
        locations = defaultdict(dict)
        for sid, ship in ships.items():
            locations[ship['x'], ship['y']][sid] = ship
        deposited = False
        for event in events:
            loc = event.get('location', {})
            position = loc.get('x'), loc.get('y')
            if event['type'] == 'spawn':
                # Spawn events come after the automatic friendly-structure dump.
                if not deposited:
                    for point, group in locations.items():
                        for ship in group.values():
                            if structures.get(point) == ship['pid']:
                                ship['energy'] = 0
                    deposited = True
                locations[position][int(event['id'])] = dict(pid=event['owner_id'], energy=event.get('energy', 0), start=0, moved=False, born=True)
            elif event['type'] == 'shipwreck':
                group = locations[position]
                dead = {int(sid) for sid in event['ships']}
                survivors = set(group) - dead
                if len(group) < 2 or not dead <= set(group) or len(survivors) > 1:
                    unknown += 1
                    for sid in dead:
                        group.pop(sid, None)
                    continue
                owners = tuple(sorted({s['pid'] for s in group.values()}))
                mixed = len(owners) > 1
                threshold = constants.get('PILEUP_WRECK_SIZE', 0)
                outcome = 'capture' if survivors else 'pileup' if threshold > 0 and len(group) >= threshold else 'tie' if constants.get('LIGHT_SHIP_COLLISIONS') else 'upstream'
                loot = 0
                settlement = {sid: ship['energy'] for sid, ship in group.items()}
                if survivors:
                    winner = group[next(iter(survivors))]
                    total = sum(group[s]['energy'] for s in dead)
                    gain = min(total, max(0, constants.get('MAX_ENERGY', 1000) - winner['energy']))
                    loot = gain
                    winner['energy'] += gain
                # Aggregate by participant owners and outcome, retaining denominators.
                key = (owners, mixed, outcome)
                collisions[key] += 1
                for sid, ship in group.items():
                    seat = seats[ship['pid']]
                    prefix = 'enemy_' if mixed else 'friendly_'
                    for field, amount in [('participants', 1), ('empty', ship['start'] == 0),
                                          ('settlement_empty', settlement[sid] == 0),
                                          ('moving', ship['moved']), ('moving_empty', ship['moved'] and ship['start'] == 0),
                                          ('newborn', ship['born']), ('deaths', sid in dead),
                                          (outcome, 1), (outcome + '_empty', ship['start'] == 0)]:
                        seat[prefix + field] = seat.get(prefix + field, 0) + amount
                    if sid in survivors:
                        seat[prefix + 'loot'] = seat.get(prefix + 'loot', 0) + loot
                for sid in dead:
                    group.pop(sid)
        # End-of-turn deltas become the next turn's source-cell amounts.
        for cell in frame.get('cells', []):
            grid[cell['y'] * width + cell['x']] = cell['production']
    config = {k: constants.get(k) for k in ('VISION_RADIUS', 'FOG_ENABLED', 'REEF_PERCENT', 'MIRROR_REEFS', 'PILEUP_WRECK_SIZE', 'LIGHT_SHIP_COLLISIONS', 'INSPIRATION_ENABLED', 'MOVE_COST_RATIO', 'MAX_ENERGY')}
    config.update(width=width, height=height, turns=constants['MAX_TURNS'])
    return dict(config=config, initial=initial, remaining=sum(grid), reefs=len(reefs), cells=width * height,
                seats=seats, unknown=unknown,
                events=[dict(owners=list(owners), enemy=mixed, outcome=outcome, count=count)
                        for (owners, mixed, outcome), count in collisions.items()])


def record(db, match_id, replay):
    value = analyze(replay)
    db.execute('INSERT OR REPLACE INTO match_rule_stats VALUES(?,?,?)', (match_id, SCHEMA, json.dumps(value, separators=(',', ':'))))
    return value


def report(db, mode=None, group='all'):
    entries = board(db)
    allowed = {e['version_id'] for e in entries}
    candidates = sorted([e for e in entries if not e['builtin'] and e['games'] >= 12], key=lambda e: (-e['elo'], e['version_id']))
    cutoff = candidates[max(0, math.ceil(len(candidates) / 4) - 1)]['elo'] if candidates else None
    top = [e for e in candidates if e['elo'] >= cutoff] if candidates else []
    selected = {e['version_id'] for e in top} if group == 'top' else allowed
    query = '''SELECT m.id,m.mode,m.seat_json,m.finished_at,s.summary_json FROM matches m
        LEFT JOIN match_rule_stats s ON s.match_id=m.id AND s.schema_version=?
        WHERE m.public=1 AND m.status='complete' AND m.result_json IS NOT NULL'''
    params = [SCHEMA]
    if mode is not None:
        query += ' AND m.mode=?'
        params.append(mode)
    cohorts = {}
    eligible = covered = 0
    latest = None
    for row in db.execute(query, params):
        versions = [s['id'] for s in json.loads(row['seat_json'])]
        # Whole-match resource totals must not reveal a hidden/private version's data.
        if not set(versions) <= allowed or not set(versions) & selected:
            continue
        eligible += 1
        if not row['summary_json']:
            continue
        covered += 1
        latest = max(latest or 0, row['finished_at'] or 0)
        value = json.loads(row['summary_json'])
        key = json.dumps([row['mode'], value['config']], sort_keys=True)
        item = cohorts.setdefault(key, dict(mode=row['mode'], config=value['config'], games=0, seats=0, initial=0, remaining=0,
                                            cells=0, reefs=0, unknown=0, ship_turns=0, moving_turns=0, cargo_bins=[0] * len(BINS),
                                            enemy_events=0, friendly_events=0, outcomes={}, friendly_outcomes={}, counters={}, peak_ships_sum=0))
        item['games'] += 1
        for field in ('initial', 'remaining', 'cells', 'reefs', 'unknown'):
            item[field] += value[field]
        chosen = {i for i, vid in enumerate(versions) if vid in selected}
        for seat in chosen:
            stats = value['seats'][seat]
            item['seats'] += 1
            item['peak_ships_sum'] += stats['peak_ships']
            for field in ('ship_turns', 'moving_turns'):
                item[field] += stats[field]
            item['cargo_bins'] = [a + b for a, b in zip(item['cargo_bins'], stats['cargo_bins'])]
            for field, amount in stats.items():
                if field.startswith(('enemy_', 'friendly_')):
                    item['counters'][field] = item['counters'].get(field, 0) + amount
        for event in value['events']:
            if not set(event['owners']) & chosen:
                continue
            if event['enemy']:
                item['enemy_events'] += event['count']
                outcome = event['outcome']
                item['outcomes'][outcome] = item['outcomes'].get(outcome, 0) + event['count']
            else:
                item['friendly_events'] += event['count']
                outcome = event['outcome']
                item['friendly_outcomes'][outcome] = item['friendly_outcomes'].get(outcome, 0) + event['count']
    return dict(schema=SCHEMA, mode=mode, group=group, eligible=eligible, covered=covered, missing=eligible-covered,
                latest_match_at=latest, generated_at=int(time.time()), bins=BINS,
                top=dict(min_games=12, candidates=len(candidates), cutoff=cutoff,
                         versions=[dict(version_id=e['version_id'], bot_id=e['bot_id'], bot_name=e['bot_name'], version=e['version'], elo=e['elo']) for e in top]),
                cohorts=sorted(cohorts.values(), key=lambda e: (e['mode'], e['config']['width'], e['config']['turns'], str(e['config']))))


@router.get('/api/leaderboard/rules')
def rules(mode: int | None = None, group: str = 'all'):
    if mode not in (None, 2, 4, 8) or group not in ('all', 'top'):
        raise HTTPException(422, '人数需为 2、4、8；分组需为 all 或 top。')
    with connect() as db:
        return report(db, mode, group)
