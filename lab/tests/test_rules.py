import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT/'build/halite'
RULES = json.loads((ROOT/'lab/config/rules.json').read_text())


class RulesTest(unittest.TestCase):
    def game(self, ships=None, plans=None, rules=None, turns=1, seed=11, players=2, cells=None, width=32, height=16):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        out = Path(temp.name)
        constants = dict(RULES, REEF_PERCENT=0, INSPIRATION_ENABLED=False)
        constants.update(rules or {})
        (out/'rules.json').write_text(json.dumps(constants))
        args = [str(ENGINE), '--results-as-json', '--no-compression', '--width', str(width), '--height', str(height),
                '--turn-limit', str(turns), '--seed', str(seed), '-c', str(out/'rules.json'), '-i', str(out)]
        if ships is not None:
            version = re.search(r'#define HALITE_VERSION "(.*?)"', (ROOT/'game_engine/version.hpp').read_text())[1]
            grid = [0] * (width*height)
            for (x, y), value in (cells or {}).items():
                grid[y*width+x] = value
            snapshot = f'{version};fractal,{width},{height},{players},{seed};' + ','.join(map(str,grid)) + ',;'
            homes = [(0,0),(width//2,0),(0,height//2),(width//2,height//2)]
            for pid in range(players):
                home = homes[pid]
                entities = ','.join(f'{i}-{x}-{y}-{cargo}' for i,(x,y,cargo) in enumerate(ships[pid]))
                snapshot += f'{pid};5000;{home[0]}-{home[1]},;{entities};'
            args += ['--from-snapshot', snapshot]
        traces = []
        for pid in range(players):
            trace = out/f'player-{pid}.jsonl'
            traces.append(trace)
            args.append(shlex.join([sys.executable, str(ROOT/'lab/tests/scripted_bot.py'), json.dumps((plans or [{}]*players)[pid]), str(trace)]))
        proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertFalse(any(result['terminated'].values()), result)
        replay = json.loads(Path(result['replay']).read_text())
        return result, replay, [[json.loads(line) for line in path.read_text().splitlines()] for path in traces]

    def final_ships(self, replay):
        return [(pid, ship) for pid, ships in replay['full_frames'][-1]['entities'].items() for ship in ships.values()]

    def test_light_ship_steals_and_destroys_heavy(self):
        _, replay, _ = self.game([[(9,8,100)],[(10,8,500)]],[{'1':['e']},{}])
        ships = self.final_ships(replay)
        self.assertEqual(len(ships),1)
        self.assertEqual((ships[0][0],ships[0][1]['energy']),('0',600))

    def test_equal_weight_sinks_and_drops_ground_halite(self):
        _, replay, _ = self.game([[(9,8,100)],[(10,8,100)]],[{'1':['e']},{}])
        self.assertEqual(self.final_ships(replay),[])
        self.assertIn({'x':10,'y':8,'production':200},replay['full_frames'][1]['cells'])

    def test_tied_minimum_sinks_every_ship(self):
        _, replay, _ = self.game([[(9,8,100),(11,8,100)],[(10,8,500)]],[{'1':['e','w']},{}])
        self.assertEqual(self.final_ships(replay),[])
        self.assertIn({'x':10,'y':8,'production':700},replay['full_frames'][1]['cells'])

    def test_heavier_tie_does_not_destroy_unique_minimum(self):
        _, replay, _ = self.game([[(9,8,100),(11,8,300)],[(10,8,300)]],[{'1':['e','w']},{}])
        self.assertEqual(self.final_ships(replay)[0][1]['energy'],700)

    def test_loot_over_capacity_goes_to_ground(self):
        _, replay, _ = self.game([[(9,8,100),(11,8,900)],[(10,8,900)]],[{'1':['e','w']},{}])
        self.assertEqual(self.final_ships(replay)[0][1]['energy'],1000)
        self.assertIn({'x':10,'y':8,'production':900},replay['full_frames'][1]['cells'])

    def test_weight_is_compared_after_movement_cost(self):
        _, replay, _ = self.game([[(9,8,100)],[(10,8,95)]],[{'1':['e']},{}],cells={(9,8):100})
        self.assertEqual(self.final_ships(replay)[0][0],'0')
        self.assertEqual(self.final_ships(replay)[0][1]['energy'],185)

    def test_same_owner_uses_same_collision_rules(self):
        _, replay, _ = self.game([[(9,8,100),(11,8,500)],[]],[{'1':['e','w']},{}])
        self.assertEqual(self.final_ships(replay)[0][1]['energy'],600)

    def test_tied_wreck_on_base_stays_on_ground(self):
        result, replay, _ = self.game([[(1,0,100)],[(0,0,100)]],[{'1':['w']},{}])
        self.assertIn({'x':0,'y':0,'production':200},replay['full_frames'][1]['cells'])
        self.assertEqual(result['stats']['0']['score'],5000)

    def test_spawn_uses_light_ship_collision(self):
        _, replay, _ = self.game([[],[(0,0,100)]],[{'1':'spawn'},{}])
        ships = self.final_ships(replay)
        self.assertEqual(len(ships),1)
        self.assertEqual((ships[0][0],ships[0][1]['energy']),('0',100))

    def test_upstream_collision_switch(self):
        _, replay, _ = self.game([[(9,8,100)],[(10,8,500)]],[{'1':['e']},{}],rules={'LIGHT_SHIP_COLLISIONS':False})
        self.assertEqual(self.final_ships(replay),[])

    def test_pileup_of_unequal_ships_wrecks_all_in_place(self):
        _, replay, _ = self.game([[(9,8,100),(11,8,300)],[(10,8,500)]],[{'1':['e','w']},{}],rules={'PILEUP_WRECK_SIZE':3})
        self.assertEqual(self.final_ships(replay),[])
        self.assertIn({'x':10,'y':8,'production':900},replay['full_frames'][1]['cells'])

    def test_pileup_of_four_players_wrecks_all_in_place(self):
        ships = [[(9,4,0)],[(11,4,200)],[(10,3,200)],[(10,5,700)]]
        plans = [{'1':['e']},{'1':['w']},{'1':['s']},{'1':['n']}]
        _, replay, _ = self.game(ships,plans,players=4,rules={'PILEUP_WRECK_SIZE':3})
        self.assertEqual(self.final_ships(replay),[])
        self.assertIn({'x':10,'y':4,'production':1100},replay['full_frames'][1]['cells'])
        self.assertEqual(len(replay['full_frames'][1]['events'][0]['ships']),4)

    def test_pileup_threshold_keeps_two_ship_capture(self):
        _, replay, _ = self.game([[(9,8,100)],[(10,8,500)]],[{'1':['e']},{}],rules={'PILEUP_WRECK_SIZE':3})
        ships = self.final_ships(replay)
        self.assertEqual((len(ships),ships[0][0],ships[0][1]['energy']),(1,'0',600))

    def test_pileup_on_base_stays_on_ground(self):
        result, replay, _ = self.game([[(1,0,100),(0,1,300)],[(0,0,0)]],[{'1':['w','n']},{}],rules={'PILEUP_WRECK_SIZE':3})
        self.assertEqual(self.final_ships(replay),[])
        self.assertIn({'x':0,'y':0,'production':400},replay['full_frames'][1]['cells'])
        self.assertEqual(result['stats']['0']['score'],5000)

    def test_invalid_pileup_size_is_rejected(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        rules = Path(temp.name)/'rules.json'
        rules.write_text(json.dumps(dict(RULES, PILEUP_WRECK_SIZE=1)))
        proc = subprocess.run([str(ENGINE), '--results-as-json', '-c', str(rules), '-i', temp.name, 'true', 'true'],
                              cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(proc.returncode, 0)

    def test_mirrored_reefs_match_halite_symmetry(self):
        for players, width, height in ((2,32,32),(4,48,48),(8,64,32)):
            with self.subTest(players=players):
                _, replay, traces = self.game(rules={'REEF_PERCENT':20,'MIRROR_REEFS':True}, players=players, width=width, height=height)
                terrain = traces[0][0]['terrain']
                grid = replay['production_map']['grid']
                factories = sorted(tuple(p['factory_location'].values()) for p in replay['players'])
                self.assertIn(1,terrain)
                reflections = [lambda x,y: (width-1-x,y)]
                if players > 2:
                    reflections.append(lambda x,y: (x,height-1-y))
                if players > 4:
                    half = width//2
                    reflections.append(lambda x,y: (half-1-x if x < half else 3*half-1-x,y))
                for reflect in reflections:
                    self.assertEqual(sorted(reflect(*f) for f in factories), factories)
                    for y in range(height):
                        for x in range(width):
                            mx, my = reflect(x,y)
                            self.assertEqual(terrain[y*width+x], terrain[my*width+mx])
                            self.assertEqual(grid[y][x]['energy'], grid[my][mx]['energy'])
                seen, pending = set(),[terrain.index(0)]
                while pending:
                    pos = pending.pop()
                    if pos in seen:
                        continue
                    seen.add(pos)
                    x,y = pos%width,pos//width
                    pending += [ny*width+nx for nx,ny in [((x+1)%width,y),((x-1)%width,y),(x,(y+1)%height),(x,(y-1)%height)] if not terrain[ny*width+nx]]
                self.assertEqual(len(seen),terrain.count(0))

    def test_fog_hides_enemies_banks_and_resources(self):
        _, _, traces = self.game([[(2,2,100)],[(15,12,200)]],rules={'VISION_RADIUS':1})
        obs = traces[0][1]
        self.assertNotIn('game_seed',traces[0][0]['constants'])
        self.assertEqual(obs['players'][1]['ships'],[])
        self.assertIsNone(obs['players'][1]['bank'])
        self.assertIsNone(obs['halite'][12*32+15])
        self.assertEqual(len(obs['players'][0]['ships']),1)
        self.assertEqual(obs['halite'][2*32+2],0)
        self.assertEqual(obs['halite'][31],0)  # wraparound base vision

    def test_full_vision_switch(self):
        _, _, traces = self.game([[(2,2,100)],[(15,12,200)]],rules={'FOG_ENABLED':False})
        obs = traces[0][1]
        self.assertEqual(len(obs['players'][1]['ships']),1)
        self.assertEqual(obs['players'][1]['bank'],5000)
        self.assertNotIn(None,obs['halite'])

    def test_leaving_vision_removes_current_information(self):
        _, _, traces = self.game([[(5,5,100)],[(6,5,200)]],plans=[{'1':['w'],'2':['w']},{}],rules={'VISION_RADIUS':1},turns=3)
        self.assertEqual(len(traces[0][1]['players'][1]['ships']),1)
        self.assertEqual(traces[0][2]['players'][1]['ships'],[])
        self.assertIsNone(traces[0][2]['halite'][5*32+6])

    def test_reef_generation_symmetry_connectivity_and_eight_players(self):
        for players in (2,4,8):
            with self.subTest(players=players):
                _, replay, traces = self.game(rules={'REEF_PERCENT':20}, players=players)
                terrain = traces[0][0]['terrain']
                self.assertIn(1,terrain)
                cols = 2 if players in (2,4) else 4
                rows = players//cols
                tw, th = 32//cols, 16//rows
                for y in range(16):
                    for x in range(32):
                        self.assertEqual(terrain[y*32+x],terrain[(y%th)*32+(x%tw)])
                seen, pending = set(),[terrain.index(0)]
                while pending:
                    pos = pending.pop()
                    if pos in seen:
                        continue
                    seen.add(pos)
                    x,y = pos%32,pos//32
                    pending += [ny*32+nx for nx,ny in [((x+1)%32,y),((x-1)%32,y),(x,(y+1)%16),(x,(y-1)%16)] if not terrain[ny*32+nx] and ny*32+nx not in seen]
                self.assertEqual(len(seen),terrain.count(0))
                self.assertTrue(any(c.get('reef') for row in replay['production_map']['grid'] for c in row))

    def test_reef_move_holds_and_mines(self):
        _, _, traces = self.game(rules={'REEF_PERCENT':20})
        terrain = traces[0][0]['terrain']
        source = next(pos for pos in range(512) if terrain[pos] == 0 and terrain[(pos//32)*32+(pos%32+1)%32] == 1)
        x,y = source%32,source//32
        _, replay, _ = self.game([[(x,y,100)],[]],plans=[{'1':['e']},{}],rules={'REEF_PERCENT':20},cells={(x,y):100})
        ship = self.final_ships(replay)[0][1]
        self.assertEqual((ship['x'],ship['y'],ship['energy']),(x,y,125))

    def test_seed_reproduces_states_and_actions(self):
        args = dict(ships=[[(9,8,100)],[(10,8,500)]],plans=[{'1':['e']},{}],turns=2)
        _, a, _ = self.game(**args)
        _, b, _ = self.game(**args)
        self.assertEqual(a['full_frames'],b['full_frames'])


if __name__ == '__main__':
    unittest.main()
