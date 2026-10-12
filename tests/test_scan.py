import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/"src"))
from scan import extract,normalize,peers,enrich

M="So11111111111111111111111111111111111111112"
N="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
class ScanTest(unittest.TestCase):
 def test_blocks(self):
  self.assertEqual(set(extract({"code":0,"data":[{"chain":"sol","interval":"6h","tokens":[]},{"chain":"sol","interval":"24h","tokens":[]}]})),{"6h","24h"})
 def test_filter(self):
  now=1800000000
  data=[{"address":M,"circulating_supply":100000,"creation_timestamp":now-90000,
         "price":{"price":1,"price_6h":.5,"volume_6h":10000}},
        {"address":N,"circulating_supply":100000,"creation_timestamp":now-100,
         "price":{"price":1,"price_6h":.5,"volume_6h":1000}}]
  self.assertEqual(list(normalize(data,now)),[M])
 def test_peers(self):
  a=[{"mint":M,"market_cap":100000,"volume":10000,"change":10,"age_hours":50},{"mint":N,"market_cap":110000,"volume":5000,"change":20,"age_hours":60}]
  res=peers(a)
  self.assertEqual(res[0]["peer_count"],1)
  self.assertAlmostEqual(res[0]["price_effect"],100)
 def test_eighteen_hours(self):
  rows=[{"mint":M,"volume":20,"change":10,"age_hours":50,"windows_aligned":True}]
  enrich(rows,{M:{"volume":50,"change":32}})
  self.assertEqual(rows[0]["v18"],30)
  self.assertAlmostEqual(rows[0]["r18"],20)

 def test_original_user_example(self):
  rows=[dict(mint=M,market_cap=1000000,volume=100000,change=30,age_hours=50),
        dict(mint=N,market_cap=1000000,volume=500000,change=10,age_hours=50)]
  result=peers(rows)
  self.assertEqual(result[0]['price_effect'],300)
  self.assertEqual(result[1]['price_effect'],20)

 def test_missing_metrics_are_retained_and_not_ranked(self):
  rows=[dict(mint=M,market_cap=100000,volume=None,change=None,age_hours=50),
        dict(mint=N,market_cap=100000,volume=10000,change=10,age_hours=50)]
  result=peers(rows)
  self.assertEqual(len(result),2)
  self.assertIsNone(result[0]['price_effect'])
  self.assertEqual(result[1]['peer_count'],1)
  self.assertEqual(result[1]['peer_observed_count'],0)

 def test_negative_returns_have_separate_defensive_screen(self):
  rows=[dict(mint=M,market_cap=100000,volume=20000,change=-10,age_hours=50),
        dict(mint=N,market_cap=100000,volume=10000,change=-20,age_hours=50)]
  result=peers(rows)
  self.assertIsNone(result[0]['positive_pe_rank'])
  self.assertEqual(result[0]['higher_volume_less_loss_count'],1)

 def test_unknown_alignment_disables_confirmed_eighteen_hours(self):
  rows=[dict(mint=M,volume=20,change=10,age_hours=50)]
  enrich(rows,{M:dict(volume=50,change=32)})
  self.assertIsNone(rows[0]['r18'])
  self.assertAlmostEqual(rows[0]['r18_provisional'],20)

 def test_young_age_disables_previous_18h_even_if_api_start_price_exists(self):
  rows=[dict(mint=M,volume=20,change=10,age_hours=11,windows_aligned=True)]
  enrich(rows,{M:dict(volume=50,change=32)})
  self.assertIsNone(rows[0]['r18'])

 def test_anomaly_needs_eight_comparators_and_does_not_change_price_effect(self):
  rows=[dict(mint=str(i),market_cap=100000,volume=10000,change=i+1,age_hours=50,liquidity=20000) for i in range(8)]
  result=peers(rows)
  self.assertIsNone(result[0]['anomaly_ratio'])
  self.assertEqual(result[0]['price_effect'],10)

 def test_near_zero_turnover_does_not_publish_infinite_price_effect(self):
  result=peers([dict(mint=M,market_cap=100000,volume=1e-300,change=1000000,age_hours=50)])
  self.assertIsNone(result[0]['price_effect'])
if __name__=="__main__":unittest.main()
