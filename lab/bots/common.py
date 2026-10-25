"""Reference bot client for the halite3-lab-v1 protocol (standard library only)."""
import argparse
from collections import deque
import json
import sys

DIRECTIONS = [('o', 0, 0), ('n', 0, -1), ('s', 0, 1), ('e', 1, 0), ('w', -1, 0)]


def run(strategy):
    parser = argparse.ArgumentParser()
    parser.add_argument('--return-at', type=int, default=650)
    parser.add_argument('--fleet', type=int, default=12)
    args = parser.parse_args()
    init = json.loads(sys.stdin.readline())
    if init.get('protocol') != 'halite3-lab-v1':
        raise ValueError('This bot requires LAB_PROTOCOL=true')
    constants = init['constants']
    w, h = init['width'], init['height']
    me = init['player_id']
    terrain = init['terrain']
    memory = [None] * (w*h)
    last_seen = [-1] * (w*h)
    returning = set()
    print(strategy, flush=True)

    def index(x, y):
        return (y % h)*w + (x % w)

    def options(pos):
        x, y = pos % w, pos // w
        return [(d, index(x+dx, y+dy)) for d, dx, dy in DIRECTIONS if not terrain[index(x+dx, y+dy)]]

    def distances(target):
        dist = {target: 0}
        queue = deque([target])
        while queue:
            pos = queue.popleft()
            for _, nxt in options(pos)[1:]:
                if nxt not in dist:
                    dist[nxt] = dist[pos] + 1
                    queue.append(nxt)
        return dist

    for line in sys.stdin:
        obs = json.loads(line)
        turn = obs['turn']
        for pos, value in enumerate(obs['halite']):
            if value is not None:
                memory[pos], last_seen[pos] = value, turn
        own = next(p for p in obs['players'] if p['id'] == me)
        ships = own['ships']
        home = index(*own['factory'])
        bases = [home] + [index(*loc) for loc in own['dropoffs']]
        home_maps = [distances(base) for base in bases]
        home_dist = {pos: min(d.get(pos, w*h) for d in home_maps) for pos in home_maps[0]}
        enemies = {index(s['x'], s['y']): s['cargo'] for p in obs['players'] if p['id'] != me for s in p['ships']}
        reserved = {index(s['x'], s['y']) for s in ships}
        commands = []
        preferences = {}
        for ship in sorted(ships, key=lambda s: (-s['cargo'], s['id'])):
            sid, cargo = ship['id'], ship['cargo']
            pos = index(ship['x'], ship['y'])
            reserved.discard(pos)
            if cargo == 0:
                returning.discard(sid)
            if cargo >= args.return_at or constants['MAX_TURNS'] - turn <= home_dist.get(pos, w*h) + 5:
                returning.add(sid)
            cell = obs['halite'][pos] or 0
            ratio = constants['MOVE_COST_RATIO']
            # Inspiration can only reduce the move cost for shipped lab defaults.
            cost = cell // ratio
            choices = options(pos)
            if cargo < cost:
                choices = choices[:1]
            route = None
            if strategy == 'raider' and sid not in returning:
                dist = distances(pos)
                targets = []
                for target, steps in dist.items():
                    resource = memory[target]
                    value = 100 if resource is None else resource
                    stale = min(60, (turn - last_seen[target]) * 2)
                    score = (value + stale) / (steps + 2) - home_dist.get(target, w*h) * 0.7
                    targets.append((score, -target, target))
                if targets:
                    route = distances(max(targets)[2])
            scored = []
            for order, (direction, target) in enumerate(choices):
                if strategy != 'raider' and target in reserved:
                    continue
                moving = direction != 'o'
                weight = cargo - cost if moving else cargo
                if sid in returning:
                    score = -home_dist.get(target, w*h)*120
                    if target in bases:
                        score += 1000
                elif route is not None:
                    score = -route.get(target, w*h)*35
                    if not moving:
                        score += min(cell, constants['MAX_ENERGY']-cargo) / constants['EXTRACT_RATIO']
                else:
                    value = memory[target] if memory[target] is not None else 100
                    score = value / 4 if not moving else value / 6 - 8
                    if cell < 30 and moving:
                        score += 15
                if strategy == 'raider':
                    for enemy_pos, enemy_cargo in enemies.items():
                        enemy_reachable = {n for _, n in options(enemy_pos)}
                        if target in enemy_reachable and enemy_cargo <= weight:
                            score -= 1500 + cargo
                    if target in enemies and weight < enemies[target]:
                        score += min(700, enemies[target]) * 0.8
                elif target in enemies:
                    score -= 1500
                scored.append((score, -order, direction, target))
            if strategy == 'raider':
                preferences[sid] = [(d, target) for _, _, d, target in sorted(scored, reverse=True)]
            if not scored:
                direction, target = 'o', pos
            else:
                _, _, direction, target = max(scored)
            reserved.add(target)
            commands.append(f'm {sid} {direction}')
        if strategy == 'raider':
            # Match ships to distinct reachable cells. Augmenting paths allow a
            # returning ship to displace an unloaded ship blocking the base.
            destinations, assigned = {}, {}

            def place(sid, visited):
                for direction, target in preferences[sid]:
                    if target in visited:
                        continue
                    visited.add(target)
                    occupant = destinations.get(target)
                    if occupant is None or place(occupant, visited):
                        destinations[target] = sid
                        assigned[sid] = (direction, target)
                        return True
                return False

            for sid in reversed(preferences):
                if not place(sid, set()):
                    raise RuntimeError('No collision-free assignment despite legal hold positions')
            reserved = set(destinations)
            commands = [f'm {sid} {direction}' for sid, (direction, _) in sorted(assigned.items())]
        if (own['bank'] >= constants['NEW_ENTITY_ENERGY_COST'] and home not in reserved
                and len(ships) < args.fleet and turn < constants['MAX_TURNS'] * 0.55):
            commands.append('g')
        print(' '.join(commands), flush=True)
