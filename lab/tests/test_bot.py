import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BotTest(unittest.TestCase):
    def test_loaded_returning_ship_displaces_empty_base_ship(self):
        ships = [{'id':i,'x':x,'y':y,'cargo':cargo} for i,(x,y,cargo) in enumerate([
            (8,8,0),(7,8,800),(9,8,800),(8,7,800),(8,9,800)])]
        own = {'id':0,'factory':[8,8],'bank':0,'ships':ships,'dropoffs':[]}
        obs = {'type':'turn','turn':30,'player_id':0,'width':16,'height':16,
               'terrain':[0]*256,'halite':[0]*256,'players':[own]}
        constants = {'MAX_TURNS':200,'MAX_ENERGY':1000,'NEW_ENTITY_ENERGY_COST':1000,
                     'MOVE_COST_RATIO':10,'EXTRACT_RATIO':4}
        init = dict(obs,type='init',protocol='halite3-lab-v1',constants=constants)
        proc = subprocess.run([sys.executable,str(ROOT/'lab/bots/raider.py')],
                              input=json.dumps(init)+'\n'+json.dumps(obs)+'\n',text=True,capture_output=True,timeout=5)
        self.assertEqual(proc.returncode,0,proc.stderr)
        actions = proc.stdout.splitlines()[1].split()
        moves = dict(zip('onsew',[(0,0),(0,-1),(0,1),(1,0),(-1,0)]))
        targets = {}
        for i in range(0,len(actions),3):
            sid = int(actions[i+1]);dx,dy=moves[actions[i+2]]
            targets[sid]=((ships[sid]['x']+dx)%16,(ships[sid]['y']+dy)%16)
        self.assertEqual(len(set(targets.values())),5)
        self.assertNotEqual(targets[0],(8,8))
        self.assertIn((8,8),targets.values())


if __name__ == '__main__':
    unittest.main()
