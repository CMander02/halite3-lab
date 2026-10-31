import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend import rule_analytics as R, settings as S, rating
from backend.api import app
from backend.db import initialize, connect


def replay(ships, moves, events, constants=None, cells=None):
    return dict(
        GAME_CONSTANTS=dict(MAX_TURNS=1, LIGHT_SHIP_COLLISIONS=True, MOVE_COST_RATIO=10, **(constants or {})),
        players=[dict(player_id=p, factory_location=dict(x=0 if p == 0 else 4, y=0)) for p in range(2)],
        production_map=dict(width=8, height=8, grid=[[dict(energy=100) for x in range(8)] for y in range(8)]),
        full_frames=[dict(entities=ships, moves=moves, events=events, cells=cells or []), dict(entities={}, moves={}, events=[], cells=[])])


def ship(x, y, energy):
    return dict(x=x, y=y, energy=energy)


def wreck(ids, x=2, y=2):
    return dict(type='shipwreck', ships=ids, location=dict(x=x, y=y))


class RuleReplayTest(unittest.TestCase):
    def test_move_cost_empty_survivor_and_resource_delta(self):
        value = R.analyze(replay({'0': {'1': ship(1, 2, 10)}, '1': {'2': ship(2, 2, 600)}},
            {'0': [dict(type='m', id=1, direction='e')]}, [wreck([2])], cells=[dict(x=2, y=2, production=40)]))
        a, b = value['seats']
        self.assertEqual(a['enemy_settlement_empty'], 1)
        self.assertEqual(a['enemy_empty'], 0)
        self.assertEqual(a['enemy_loot'], 600)
        self.assertEqual(a['moving_turns'], 1)
        self.assertEqual(b['enemy_deaths'], 1)
        self.assertEqual(value['remaining'], 6340)
        self.assertEqual(value['events'][0]['outcome'], 'capture')
        self.assertEqual(sum(a['cargo_bins']), a['ship_turns'])

    def test_equal_minimum_and_three_ship_pileup_are_distinct(self):
        ships = {'0': {'1': ship(1, 2, 10), '3': ship(3, 2, 700)}, '1': {'2': ship(2, 2, 0)}}
        moves = {'0': [dict(type='m', id=1, direction='e'), dict(type='m', id=3, direction='w')]}
        value = R.analyze(replay(ships, moves, [wreck([1, 2, 3])]))
        self.assertEqual(value['events'][0]['outcome'], 'tie')
        pileup = R.analyze(replay(ships, moves, [wreck([1, 2, 3])], {'PILEUP_WRECK_SIZE': 3}))
        self.assertEqual(pileup['events'][0]['outcome'], 'pileup')
        self.assertEqual(pileup['seats'][1]['enemy_pileup_empty'], 1)

    def test_spawn_collision_after_deposit_and_friendly_separation(self):
        value = R.analyze(replay({'0': {'1': ship(0, 0, 900)}}, {},
            [dict(type='spawn', id=2, owner_id=0, energy=0, location=dict(x=0, y=0)), wreck([1, 2], 0, 0)]))
        self.assertFalse(value['events'][0]['enemy'])
        self.assertEqual(value['events'][0]['outcome'], 'tie')
        self.assertEqual(value['seats'][0]['friendly_settlement_empty'], 2)
        self.assertEqual(value['seats'][0]['friendly_empty'], 1)
        self.assertEqual(value['seats'][0]['friendly_newborn'], 1)

    def test_reef_and_insufficient_cargo_are_holds(self):
        data = replay({'0': {'1': ship(1, 2, 0)}}, {'0': [dict(type='m', id=1, direction='e')]}, [])
        self.assertEqual(R.analyze(data)['seats'][0]['moving_turns'], 0)
        data['full_frames'][0]['entities']['0']['1']['energy'] = 100
        data['production_map']['grid'][2][2]['reef'] = True
        self.assertEqual(R.analyze(data)['seats'][0]['moving_turns'], 0)

    def test_unknown_event_is_explicit(self):
        value = R.analyze(replay({'0': {'1': ship(1, 2, 10)}}, {}, [wreck([42])]))
        self.assertEqual(value['unknown'], 1)
        self.assertFalse(value['events'])


class RuleApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = S.DATA
        S.DATA = Path(self.temp.name)
        initialize()
        self.client = TestClient(app)
        self.addCleanup(self.cleanup)
        self.summary = R.analyze(replay({}, {}, []))
        with connect() as db:
            db.execute("INSERT INTO jobs(id,name,kind,config_json,created_at) VALUES('j','rules','private','{}',0)")

    def cleanup(self):
        self.client.close()
        S.DATA = self.old
        self.temp.cleanup()
        rating._cache['key'] = None

    def game(self, name, public=1, status='complete', stats=True, mode=2):
        with connect() as db:
            db.execute('INSERT INTO matches(id,job_id,mode,seed,seat_json,status,public,result_json,created_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (name, 'j', mode, 11, json.dumps([dict(id='builtin-baseline-v1'), dict(id='builtin-raider-v1')]), status, public,
                 json.dumps(dict(stats={'0': dict(rank=1), '1': dict(rank=2)})), 0, 100))
            if stats:
                db.execute('INSERT INTO match_rule_stats VALUES(?,?,?)', (name, R.SCHEMA, json.dumps(self.summary)))
        rating._cache['key'] = None

    def test_public_only_coverage_mode_and_hidden_versions(self):
        self.summary['events'] = [dict(owners=[0], enemy=False, outcome='pileup', count=3),
                                  dict(owners=[0, 1], enemy=True, outcome='capture', count=2)]
        self.game('public')
        self.game('missing', stats=False)
        self.game('private', public=0)
        self.game('unfinished', status='running')
        self.game('four', mode=4)
        result = self.client.get('/api/leaderboard/rules?mode=2').json()
        self.assertEqual((result['eligible'], result['covered'], result['missing']), (2, 1, 1))
        self.assertEqual(result['cohorts'][0]['games'], 1)
        self.assertEqual(result['cohorts'][0]['friendly_outcomes'], {'pileup': 3})
        self.assertEqual(result['cohorts'][0]['friendly_events'], 3)
        self.assertEqual(result['cohorts'][0]['outcomes'], {'capture': 2})
        self.assertEqual(self.client.get('/api/leaderboard/rules?group=top').json()['covered'], 0)
        for query in ('mode=3', 'group=bad'):
            self.assertEqual(self.client.get('/api/leaderboard/rules?' + query).status_code, 422)

    def test_rule_variants_stay_separate_and_record_is_idempotent(self):
        self.game('old')
        self.game('new')
        data = replay({}, {}, [], {'PILEUP_WRECK_SIZE': 3})
        with connect() as db:
            R.record(db, 'new', data)
            R.record(db, 'new', data)
        result = self.client.get('/api/leaderboard/rules').json()
        self.assertEqual(result['covered'], 2)
        self.assertEqual(len(result['cohorts']), 2)

    def test_top_uses_raw_elo_minimum_games_and_visibility(self):
        with connect() as db:
            for i in range(4):
                db.execute('INSERT INTO bots(id,name,created_at) VALUES(?,?,0)', (f'b{i}', f'public-{i}'))
                db.execute("INSERT INTO versions(id,bot_id,version,sha256,filename,size,created_at,language) VALUES(?,?, '1','hash','bot.cpp',1,0,'cpp')", (f'v{i}', f'b{i}'))
                for j in range(12):
                    win = j < 12 - i * 4
                    result = {'0': dict(rank=1 if win else 2), '1': dict(rank=2 if win else 1)}
                    db.execute("INSERT INTO matches(id,job_id,mode,seed,seat_json,status,public,result_json,created_at,finished_at) VALUES(?,'j',2,11,?,'complete',1,?,0,100)",
                               (f'{i}-{j}', json.dumps([dict(id=f'v{i}'), dict(id='builtin-baseline-v1')]), json.dumps(dict(stats=result))))
                    db.execute('INSERT INTO match_rule_stats VALUES(?,?,?)', (f'{i}-{j}', R.SCHEMA, json.dumps(self.summary)))
            # A high adjusted correction must not remove the raw strongest version.
            db.execute('UPDATE versions SET declared_effort=\'high\' WHERE id=\'v0\'')
        rating._cache['key'] = None
        result = self.client.get('/api/leaderboard/rules?group=top').json()
        self.assertEqual([v['version_id'] for v in result['top']['versions']], ['v0'])
        self.assertEqual(result['covered'], 12)
        self.assertEqual(result['cohorts'][0]['seats'], 12)
        with connect() as db:
            db.execute("UPDATE versions SET listed=0 WHERE id='v0'")
        self.assertEqual(self.client.get('/api/leaderboard/rules').json()['eligible'], 36)
        with connect() as db:
            db.execute("UPDATE versions SET archived=1 WHERE id='v1'")
            db.execute("UPDATE versions SET language='python' WHERE id='v2'")
        response = self.client.get('/api/leaderboard/rules').json()
        self.assertEqual(response['eligible'], 12)
        self.assertNotIn('public-0', json.dumps(response))


if __name__ == '__main__':
    unittest.main()
