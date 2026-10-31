"""Per-player combat, hauling, territory and vision statistics derived from a replay.

Replay semantics (verified on lab replays): frame t lists ships at the START of
turn t and the events that happened during turn t; frame t+1 therefore holds
the survivor of a turn-t shipwreck. `deposited` is cumulative per player.
"""
from collections import deque
import gzip
import json
import logging
from . import settings as S

log = logging.getLogger('halite3.analytics')
TERRITORY_SAMPLES = 40
COLUMNS = ['kills', 'deaths', 'assists', 'robbed', 'lost', 'delivered', 'mined', 'territory', 'vision', 'ships_built', 'dropoffs']
DEFAULT_VISION_RADIUS = 4


def _territory(width, height, sources, players, bounded=False):
    """Share of cells whose unique nearest ship/structure (torus BFS) belongs to each player."""
    owner = [-1] * (width * height)
    dist = [-1] * (width * height)
    queue = deque()
    for x, y, pid in sources:
        index = y * width + x
        if dist[index] == -1:
            dist[index] = 0
            owner[index] = pid
            queue.append(index)
        elif dist[index] == 0 and owner[index] != pid:
            owner[index] = -2
    while queue:
        index = queue.popleft()
        y, x = divmod(index, width)
        for nx, ny in ((x + 1) % width, y), ((x - 1) % width, y), (x, (y + 1) % height), (x, (y - 1) % height):
            if bounded and abs(nx-x)+abs(ny-y)>1:
                continue
            other = ny * width + nx
            if dist[other] == -1:
                dist[other] = dist[index] + 1
                owner[other] = owner[index]
                queue.append(other)
            elif dist[other] == dist[index] + 1 and owner[other] != owner[index]:
                owner[other] = -2
    counts = [0] * players
    for value in owner:
        if value >= 0:
            counts[value] += 1
    return [count / (width * height) for count in counts]


def _vision(width, height, sources, players, radius, bounded=False):
    """Share of cells within torus Manhattan distance `radius` of each player's ships/structures."""
    seen = [set() for _ in range(players)]
    for source in sources:
        x, y, pid = source[:3]
        source_radius = source[3] if len(source)>3 else radius
        cells = seen[pid]
        for dx in range(-source_radius, source_radius + 1):
            span = source_radius - abs(dx)
            column = (x + dx) % width
            for dy in range(-span, span + 1):
                if bounded and not (0<=x+dx<width and 0<=y+dy<height):
                    continue
                cells.add(((y + dy) % height) * width + column)
    return [min(len(cells), width * height) / (width * height) for cells in seen]


def analyze(replay):
    frames = replay['full_frames']
    players = len(replay['players'])
    width = replay['production_map']['width']
    height = replay['production_map']['height']
    stats = [{key: 0 for key in COLUMNS} for _ in range(players)]
    for t, frame in enumerate(frames):
        nxt = frames[t + 1]['entities'] if t + 1 < len(frames) else {}
        before = {int(sid): (int(pid), ship) for pid, ships in frame.get('entities', {}).items() for sid, ship in ships.items()}
        for event in frame.get('events', []):
            if event.get('type') != 'shipwreck':
                continue
            destroyed = [before[sid] for sid in event.get('ships', []) if sid in before]
            location = (event['location']['x'], event['location']['y'])
            dead_ids = set(event.get('ships', []))
            survivor = next(((int(pid), int(sid)) for pid, ships in nxt.items() for sid, ship in ships.items()
                             if (ship['x'], ship['y']) == location and int(sid) not in dead_ids), None)
            for pid, ship in destroyed:
                stats[pid]['deaths'] += 1
                stats[pid]['lost'] += ship['energy']
            if survivor:
                winner, sid = survivor
                enemies = [(pid, ship) for pid, ship in destroyed if pid != winner]
                stats[winner]['kills'] += len(enemies)
                capacity = 1000 - before[sid][1]['energy'] if sid in before else 1000
                stats[winner]['robbed'] += max(0, min(sum(ship['energy'] for _, ship in enemies), capacity))
            else:
                for pid, _ in destroyed:
                    stats[pid]['assists'] += sum(1 for other, _ in destroyed if other != pid)
    deposited = frames[-1].get('deposited', {}) if frames else {}
    for pid in range(players):
        stats[pid]['delivered'] = int(deposited.get(str(pid), 0))
    for item in replay.get('game_statistics', {}).get('player_statistics', []):
        pid = item['player_id']
        if 0 <= pid < players:
            stats[pid]['mined'] = int(item.get('total_mined', 0))
            stats[pid]['ships_built'] = int(item.get('ships_spawned', 0))
            stats[pid]['dropoffs'] = int(item.get('number_dropoffs', 0))
    # Territory and vision: average cell shares over evenly spaced turns. Vision uses the
    # fog-of-war radius (what the player's own units light up), even when fog was off.
    radius = int(replay.get('GAME_CONSTANTS', {}).get('VISION_RADIUS', DEFAULT_VISION_RADIUS))
    constants = replay.get('GAME_CONSTANTS', {})
    bounded = bool(constants.get('BOUNDED_MAP'))
    structures = [(p['factory_location']['x'], p['factory_location']['y'], p['player_id']) for p in replay['players']]
    step = max(1, len(frames) // TERRITORY_SAMPLES)
    shares = [0.0] * players
    seen = [0.0] * players
    samples = 0
    for t in range(1, len(frames), step):
        frame = frames[t]
        for event in frames[t - 1].get('events', []):
            if event.get('type') == 'construct' and event.get('owner_id') is not None:
                structures.append((event['location']['x'], event['location']['y'], event['owner_id']))
        sources = list(structures) + [(ship['x'], ship['y'], int(pid)) for pid, ships in frame.get('entities', {}).items() for ship in ships.values()]
        for pid, share in enumerate(_territory(width, height, sources, players, bounded)):
            shares[pid] += share
        vision_sources = list(structures) + [(ship['x'], ship['y'], int(pid), int(constants.get('SCOUT_VISION_RADIUS',radius)) if ship.get('scout') else radius)
                                             for pid, ships in frame.get('entities',{}).items() for ship in ships.values()]
        for pid, share in enumerate(_vision(width, height, vision_sources, players, radius, bounded)):
            seen[pid] += share
        samples += 1
    for pid in range(players):
        stats[pid]['territory'] = round(shares[pid] / samples, 4) if samples else 0.0
        stats[pid]['vision'] = round(seen[pid] / samples, 4) if samples else 0.0
    return stats


def record(db, match_id, replay=None):
    """Store per-seat statistics for a completed match. Safe to call repeatedly."""
    row = db.execute('SELECT seat_json,result_json,replay_key,public FROM matches WHERE id=?', (match_id,)).fetchone()
    if not row or not row['result_json']:
        return False
    if replay is None:
        if not row['replay_key'] or not (S.DATA / row['replay_key']).is_file():
            return False
        with gzip.open(S.DATA / row['replay_key'], 'rt', encoding='utf-8') as stream:
            replay = json.load(stream)
    seats = json.loads(row['seat_json'])
    result = json.loads(row['result_json'])['stats']
    values = analyze(replay)
    from . import rule_analytics
    rule_analytics.record(db, match_id, replay)
    db.execute('DELETE FROM match_players WHERE match_id=?', (match_id,))
    for index, seat in enumerate(seats):
        final = result.get(str(index), {})
        db.execute(
            'INSERT INTO match_players(match_id,seat,version_id,bot_id,author_id,rank,score,' + ','.join(COLUMNS) + ') VALUES(' + ','.join('?' * (7 + len(COLUMNS))) + ')',
            (match_id, index, seat['id'], seat.get('bot_id'), seat.get('owner_id'), final.get('rank'), final.get('score'), *[values[index][key] for key in COLUMNS]))
    return True


def backfill(db, limit=500):
    # Matches without statistics, plus ones recorded before the vision column existed.
    rows = db.execute("SELECT m.id FROM matches m WHERE m.status='complete' AND m.replay_key IS NOT NULL AND (NOT EXISTS (SELECT 1 FROM match_players p WHERE p.match_id=m.id) OR EXISTS (SELECT 1 FROM match_players p WHERE p.match_id=m.id AND p.vision IS NULL)) LIMIT ?", (limit,)).fetchall()
    done = 0
    for row in rows:
        try:
            done += record(db, row['id'])
        except Exception:
            log.exception('analytics_backfill_failed id=%s', row['id'])
    return done
