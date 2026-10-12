"""Explicitly opt-in real API tests. Never substitutes fixture data."""
import os
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from contracts import normalize_info
from gmgn_api import GMGN
from scan import extract


@unittest.skipUnless(os.environ.get('RUN_LIVE_TESTS')=='1','real API requires rotated Secret and explicit opt-in')
class Live(unittest.TestCase):
    def test_real_auth_hot_search_and_window_fields(self):
        client=GMGN();raw,received=client.hot();blocks=extract(raw)
        self.assertTrue(blocks['6h']);self.assertTrue(blocks['24h'])
        info,observed=client.info(blocks['6h'][0]['address'])
        row=normalize_info(info,observed)
        self.assertEqual(row['mint'],blocks['6h'][0]['address'])
        self.assertLess(observed-received,120)
        for field in ('market_cap','age_minutes','r6','v6','v24'):
            self.assertIsNotNone(row[field],field+' unavailable in live response')
        self.assertGreaterEqual(row['v24'],row['v6'])
        if row['complete_24h']:self.assertIsNotNone(row['r24'])
        # No assertion can prove a service as-of timestamp the API did not provide.

    def test_real_closed_candle_timestamp_normalization(self):
        client=GMGN();raw,_=client.hot();mint=extract(raw)['6h'][0]['address']
        end=int(time.time())//60*60
        candles=client.candles(mint,end-600,end)
        self.assertTrue(candles)
        for row in candles:
            self.assertEqual(row['time']%60,0)
            self.assertGreaterEqual(row['time'],end-600)
            self.assertLess(row['time'],end)
