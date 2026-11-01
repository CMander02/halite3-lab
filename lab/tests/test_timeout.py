"""The configurable deadline must terminate a slow reply without changing defaults."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
ENGINE=ROOT/'build/halite'


class TimeoutTest(unittest.TestCase):
    def run_game(self, milliseconds=None):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'rules.json').write_text(json.dumps(dict(LAB_PROTOCOL=True,REEF_PERCENT=0)))
            (p/'bot.py').write_text('import sys,time\nsys.stdin.readline()\nprint("timer",flush=True)\nfor line in sys.stdin:\n time.sleep(float(sys.argv[1]))\n print("",flush=True)\n')
            args=[str(ENGINE),'--results-as-json','--no-compression','--width','32','--height','32','--turn-limit','1','--seed','11','-c',str(p/'rules.json'),'-i',d]
            if milliseconds is not None:args+=['--turn-timeout-ms',str(milliseconds)]
            args += [shlex.join([sys.executable,str(p/'bot.py'),str(delay)]) for delay in (.65,0)]
            value=subprocess.run(args,text=True,capture_output=True,timeout=10,check=True)
            return json.loads(value.stdout)

    def test_500ms_terminates_slow_bot(self):
        result=self.run_game(500)
        self.assertEqual(result['turn_timeout_ms'],500)
        self.assertTrue(result['terminated']['0'])
        self.assertFalse(result['terminated'].get('1',False))

    def test_default_2000ms_allows_same_bot(self):
        result=self.run_game()
        self.assertEqual(result['turn_timeout_ms'],2000)
        self.assertFalse(any(result['terminated'].values()))


if __name__=='__main__':unittest.main()
