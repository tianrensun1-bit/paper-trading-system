import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/"src"))
from scan import extract,normalize,peers,enrich

M="A"*32
N="B"*32
class ScanTest(unittest.TestCase):
 def test_blocks(self):
  self.assertEqual(set(extract({"data":[{"chain":"sol","interval":"6h","tokens":[]},{"chain":"sol","interval":"24h","tokens":[]}]})),{"6h","24h"})
 def test_filter(self):
  now=1800000000
  data=[{"address":M,"market_cap":100000,"volume":10000,"price_change_percent":12,"open_timestamp":now-90000},
        {"address":N,"market_cap":100000,"volume":1000,"price_change_percent":99,"open_timestamp":now-100}]
  self.assertEqual(list(normalize(data,now)),[M])
 def test_peers(self):
  a=[{"mint":M,"market_cap":100000,"volume":10000,"change":10,"age_hours":50},{"mint":N,"market_cap":110000,"volume":5000,"change":20,"age_hours":60}]
  res=peers(a)
  self.assertEqual(res[0]["peer_count"],1)
  self.assertAlmostEqual(res[0]["price_effect"],100)
 def test_eighteen_hours(self):
  rows=[{"mint":M,"volume":20,"change":10}]
  enrich(rows,{M:{"volume":50,"change":32}})
  self.assertEqual(rows[0]["v18"],30)
  self.assertAlmostEqual(rows[0]["r18"],20)
if __name__=="__main__":unittest.main()
