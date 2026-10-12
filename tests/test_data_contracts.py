import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from contracts import normalize_info, hot_tokens, ContractError
from gmgn_api import GMGN, ProviderError

MINT='So11111111111111111111111111111111111111112'


class DataContracts(unittest.TestCase):
    def test_derived_return_overflow_is_rejected(self):
        data=dict(address=MINT,creation_timestamp=1799800000,circulating_supply=1e16,
                  price=dict(price=1e-10,price_6h=1e-320))
        with self.assertRaises(ContractError):
            normalize_info(data,1800000000)
    def test_prices_determine_returns_without_guessing_hot_percent_units(self):
        data=dict(address=MINT,creation_timestamp=1799800000,circulating_supply=100000,
                  price=dict(price='1.3',price_6h='1',price_24h='.5',volume_6h=100,volume_24h=500))
        row=normalize_info(data,1800000000)
        self.assertAlmostEqual(row['r6'],.3)
        self.assertAlmostEqual(row['r24'],1.6)

    def test_creation_age_is_not_replaced_with_open_timestamp(self):
        data=dict(address=MINT,creation_timestamp=1800000000-700*60,
                  open_timestamp=1800000000-30*60,price=dict(price=2,price_6h=1,price_24h=1))
        row=normalize_info(data,1800000000)
        self.assertEqual(row['age_minutes'],700)
        self.assertIsNone(row['r24'])

    def test_duplicate_interval_blocks_are_rejected(self):
        blocks=[dict(chain='sol',interval='6h',tokens=[dict(address=MINT)])]*2
        with self.assertRaises(ContractError):
            hot_tokens(blocks,'6h')

    def test_bad_mint_is_not_accepted_by_length_only(self):
        with self.assertRaises(ContractError):
            hot_tokens([dict(chain='sol',interval='6h',tokens=[dict(address='A'*32)])],'6h')

    def test_exposed_key_cannot_be_used_without_rotation_confirmation(self):
        with patch.dict(os.environ,{'GMGN_API_KEY':'synthetic-key'},clear=True):
            with self.assertRaises(ProviderError):
                GMGN()

    def test_no_private_key_or_debug_config_in_child_process(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{
                'GMGN_API_KEY':'synthetic-key','GMGN_PRIVATE_KEY':'synthetic-private','GMGN_DEBUG':'1'}):
            provider=GMGN.__new__(GMGN)
            provider.command=['mock']; provider.raw_dir=Path(d); provider.seq=0; provider.last=0
            response=Mock(returncode=0,stdout='{"symbol":"synthetic-key"}',stderr='')
            with patch('gmgn_api.subprocess.run',return_value=response) as call:
                data,_=provider._call(['token','info'])
            env=call.call_args.kwargs['env']
            self.assertNotIn('GMGN_PRIVATE_KEY',env)
            self.assertNotIn('GMGN_DEBUG',env)
            self.assertNotIn('synthetic-key',json.dumps(data))

    def test_trading_command_is_never_permitted(self):
        provider=GMGN.__new__(GMGN)
        with self.assertRaises(ProviderError):
            provider._call(['swap','buy'])
