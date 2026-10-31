import unittest
import test_rules


class ExperimentalRulesTest(unittest.TestCase):
    game = test_rules.RulesTest.game
    final_ships = test_rules.RulesTest.final_ships

    def test_symmetric_maps_budget_connectivity_and_determinism(self):
        for players in (2, 4, 8):
            for style in range(6):
                with self.subTest(players=players, style=style):
                    rules=dict(RULES_VERSION=2, SYMMETRIC_MAP=True, MAP_STYLE=style, ORE_PER_PLAYER=1000, REEF_PERCENT=12)
                    _, r, _ = self.game(players=players, width=32, height=32, rules=rules)
                    grid=r['production_map']['grid']
                    transform = lambda x,y: (31-x,31-y) if players==2 else (31-y,x)
                    for y,row in enumerate(grid):
                        for x,cell in enumerate(row):
                            tx,ty=transform(x,y)
                            self.assertEqual(cell,grid[ty][tx])
                            if players==8:self.assertEqual(cell,grid[x][y])
                    total=sum(c['energy'] for row in grid for c in row)
                    self.assertLessEqual(abs(total-players*1000),7)
                    sources=[(p['factory_location']['x'],p['factory_location']['y']) for p in r['players']]
                    seen={sources[0]};todo=[sources[0]]
                    while todo:
                        x,y=todo.pop()
                        for nx,ny in (((x+1)%32,y),((x-1)%32,y),(x,(y+1)%32),(x,(y-1)%32)):
                            if (nx,ny) not in seen and not grid[ny][nx].get('reef'):
                                seen.add((nx,ny));todo.append((nx,ny))
                    self.assertTrue(set(sources)<=seen)
                    self.assertEqual(len(seen),sum(not c.get('reef') for row in grid for c in row))
        _, a, _=self.game(players=8,width=64,height=64,rules=rules)
        _, b, _=self.game(players=8,width=64,height=64,rules=rules)
        self.assertEqual(a['production_map'],b['production_map'])

    def test_bounded_move_holds_without_cost_and_fog_does_not_wrap(self):
        _, r, traces=self.game([[(0,7,100)],[]],[{'1':['w']},{}],
            dict(BOUNDED_MAP=True,VISION_RADIUS=1),cells={(0,7):100},width=32,height=16)
        self.assertEqual(self.final_ships(r)[0][1]['x'],0)
        self.assertEqual(self.final_ships(r)[0][1]['energy'],125)
        self.assertIsNone(traces[0][1]['halite'][7*32+31])

    def test_free_movement_and_fixed_mining(self):
        _, r, _=self.game([[(9,8,100)],[]],[{'1':['e']},{}],dict(FREE_MOVEMENT=True),cells={(9,8):1000})
        self.assertEqual(self.final_ships(r)[0][1]['energy'],100)
        _, r, _=self.game([[(9,8,0)],[]],[{},{}],dict(FIXED_MINING=1),cells={(9,8):15})
        self.assertEqual(self.final_ships(r)[0][1]['energy'],1)

    def test_enemy_only_pileup_preserves_unique_light_friendly_ship(self):
        rules=dict(PILEUP_WRECK_SIZE=3,PILEUP_ENEMIES_ONLY=True)
        _, r, _=self.game([[(9,8,10),(10,8,20),(11,8,30)],[]],[{'1':['e','o','w']},{}],rules)
        self.assertEqual(len(self.final_ships(r)),1)
        self.assertEqual(self.final_ships(r)[0][1]['energy'],60)
        _, r, _=self.game([[(9,8,10),(11,8,30)],[(10,8,20)]],[{'1':['e','w']},{}],rules)
        self.assertFalse(self.final_ships(r))

    def test_safe_spawn_refunds_and_preserves_friendly_ship(self):
        _, r, _=self.game([[(0,0,100)],[]],[{'1':'spawn'},{}],dict(SAFE_FRIENDLY_SPAWN=True))
        self.assertEqual(len(self.final_ships(r)),1)
        self.assertEqual(r['full_frames'][-1]['energy']['0'],5100)

    def test_ship_limit_and_scout_metadata(self):
        _, r, traces=self.game([[(9,8,0)],[]],[{'1':'spawn'},{}],dict(MAX_SHIPS=1))
        self.assertEqual(len(self.final_ships(r)),1)
        _, r, traces=self.game([[],[]],[{'1':'spawn'},{}],dict(RULES_VERSION=2,SCOUT_EVERY=1,SCOUT_CAPACITY=7),turns=2,cells={(5,5):10})
        ships=self.final_ships(r)
        self.assertTrue(ships[0][1]['scout'])
        own=next(p for p in traces[0][2]['players'] if p['id']==0)
        self.assertEqual(own['ships'][0]['capacity'],7)
        self.assertEqual(own['ships'][0]['kind'],'scout')

    def test_spawn_interval_and_loss_cooldown(self):
        plans=[{str(t):'spawn' for t in range(1,5)},{}]
        _, r, _=self.game([[],[]],plans,dict(SPAWN_INTERVAL=3),turns=4,cells={(5,5):10})
        births=[t for t,f in enumerate(r['full_frames']) if any(e['type']=='spawn' for e in f['events'])]
        self.assertEqual(births,[1,4])
        _, r, _=self.game([[(0,0,0)],[]],plans,dict(RESPAWN_COOLDOWN=2),turns=4,cells={(5,5):10})
        births=[t for t,f in enumerate(r['full_frames']) if t and any(e['type']=='spawn' for e in f['events'])]
        self.assertEqual(births,[1,4])

    def test_coarse_ore_has_initial_cap_and_preserves_wreck_overflow(self):
        _, r, _=self.game(width=32,height=32,players=8,rules=dict(RULES_VERSION=2,SYMMETRIC_MAP=True,
            MAX_CELL_PRODUCTION=15,MIN_CELL_PRODUCTION=15,ORE_PER_PLAYER=900))
        self.assertLessEqual(max(c['energy'] for row in r['production_map']['grid'] for c in row),15)
        _, r, _=self.game([[(9,8,15)],[(10,8,15)]],[{'1':['e']},{}],dict(MAX_ENERGY=15,FREE_MOVEMENT=True))
        self.assertIn(dict(x=10,y=8,production=30),r['full_frames'][1]['cells'])
