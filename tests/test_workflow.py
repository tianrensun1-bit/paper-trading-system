from pathlib import Path
import unittest


class Workflow(unittest.TestCase):
    def test_pinned_client_rotation_gate_and_failure_persistence(self):
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/gmgn.yml').read_text(encoding='utf-8')
        for item in ('npm ci --ignore-scripts','GMGN_KEY_ROTATION_CONFIRMED',
                     'actions/setup-node','if: always()', 'data/runs/', 'data/status.json'):
            self.assertIn(item,text)
        self.assertNotIn('npm install -g gmgn-cli',text)
        self.assertNotIn('SOLANA_WALLET:',text)
        self.assertIn('cancel-in-progress: false',text)
