import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from scan import run

M='So11111111111111111111111111111111111111112'
N='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'


class SyntheticClient:
    """Test-only data; not a production fallback."""
    def __init__(self,*args):
        self.info_calls=[]

    def hot(self):
        return [dict(chain='sol',interval='6h',tokens=[dict(address=M,price_change_percent=.3)]),
                dict(chain='sol',interval='24h',tokens=[dict(address=N)])],1800000000

    def info(self,mint):
        self.info_calls.append(mint)
        return dict(address=mint,symbol='TEST | <script>',creation_timestamp=1799800000,
                    circulating_supply=100000,liquidity=20000,
                    price=dict(price=1.3,price_6h=1,price_24h=.5,volume_6h=10000,volume_24h=50000,
                               buy_volume_6h=7000,sell_volume_6h=3000,buy_volume_24h=30000,sell_volume_24h=20000)),1800000000


class Pipeline(unittest.TestCase):
    def test_24h_data_come_from_same_token_even_if_not_on_24h_list(self):
        with tempfile.TemporaryDirectory() as d,patch('scan.time.time',return_value=1800000001):
            self.assertEqual(run(root=Path(d),provider_factory=SyntheticClient),0)
            snapshot=json.loads((Path(d)/'data/latest.json').read_text(encoding='utf-8'))
            row=snapshot['records'][0]
            self.assertAlmostEqual(row['change'],30)
            self.assertAlmostEqual(row['change24'],160)
            self.assertEqual(row['trade_signal'],'WAIT')
            self.assertIsNone(row['r18'])
            self.assertIn('&lt;script&gt;',(Path(d)/'reports/latest.md').read_text(encoding='utf-8'))

    def test_each_run_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as d,patch('scan.time.time',return_value=1800000001):
            for _ in range(2):
                self.assertEqual(run(root=Path(d),provider_factory=SyntheticClient),0)
            snapshots=list((Path(d)/'data/runs').glob('*/snapshot.json.gz'))
            self.assertEqual(len(snapshots),2)
            self.assertEqual(len(list((Path(d)/'data/runs').glob('*/records.csv'))),2)
            self.assertEqual(len((Path(d)/'data/history.jsonl').read_text(encoding='utf-8').splitlines()),2)

    def test_failed_live_auth_replaces_stale_success(self):
        with tempfile.TemporaryDirectory() as d,patch.dict('os.environ',{},clear=True):
            root=Path(d); (root/'reports').mkdir()
            (root/'reports/latest.md').write_text('old success',encoding='utf-8')
            (root/'reports/latest.csv').write_text('old success prices',encoding='utf-8')
            self.assertEqual(run(root=root),1)
            status=json.loads((root/'data/status.json').read_text(encoding='utf-8'))
            self.assertEqual(status['status'],'failed')
            self.assertIn('扫描失败',(root/'reports/latest.md').read_text(encoding='utf-8'))
            self.assertFalse((root/'data/history.jsonl').exists())
            self.assertNotIn('old success prices',(root/'reports/latest.csv').read_text(encoding='utf-8-sig'))
            self.assertIn('failed',(root/'reports/latest.csv').read_text(encoding='utf-8-sig'))


class SetupFailure(unittest.TestCase):
    def test_setup_failure_invalidates_previous_csv(self):
        import os
        import subprocess
        script=Path(__file__).resolve().parents[1]/'scripts/mark_failure.py'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'reports').mkdir()
            (root/'reports/latest.csv').write_text('stale market prices',encoding='utf-8')
            result=subprocess.run([sys.executable,str(script)],cwd=d,capture_output=True,
                                  env=dict(os.environ,GITHUB_RUN_ID='setup-failed-test'))
            self.assertEqual(result.returncode,0)
            content=(root/'reports/latest.csv').read_text(encoding='utf-8-sig')
            self.assertNotIn('stale market prices',content)
            self.assertIn('failed',content)
