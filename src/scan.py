#!/usr/bin/env python3
"""GMGN Hot Searches research. Read-only, stdlib-only. No wallet operations."""
import csv
import datetime as dt
import io
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
def num(x):
    try:
        if isinstance(x, dict): return None
        v=float(x)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError): return None

def first(obj, *keys):
    for k in keys:
        if isinstance(obj,dict) and obj.get(k) is not None: return obj[k]
    return None

def parse_time(x):
    v=num(x)
    if v is None:return None
    if v>1e12:v/=1000
    return v if 1e9<v<1e11 else None

def extract(raw):
    if isinstance(raw,dict):
        if raw.get("success") is False or raw.get("code") not in (None,0,200,"0","200"):
            raise ValueError("API returned failure")
        raw=raw.get("data", raw)
    if not isinstance(raw,list):raise ValueError("Expected GMGN data array with interval blocks")
    out={}
    for block in raw:
        interval=block.get("interval")
        if interval not in ("6h","24h") or block.get("chain")!="sol":continue
        tokens=block.get("tokens")
        if not isinstance(tokens,list):raise ValueError("Missing tokens array")
        out[interval]=tokens
    if set(out)!={"6h","24h"}:raise ValueError("Expected both 6h and 24h SOL blocks")
    return out

def normalize(items,now):
    rows={}
    for a in items:
        mint=first(a,"address","token_address","mint")
        mc=num(first(a,"market_cap","marketcap"))
        volume=num(first(a,"volume","volume_usd","total_volume"))
        ch=num(first(a,"price_change_percent","price_change","change"))
        ts=parse_time(first(a,"open_timestamp","creation_timestamp","created_at"))
        if not isinstance(mint,str) or not (32<=len(mint)<=44) or not (30000<= (mc or -1)<=2000000):continue
        if ts is None or now-ts<600*60:continue
        if volume is None or ch is None or volume<0:continue
        rows[mint]={"mint":mint,"symbol":str(a.get("symbol","?")),"market_cap":mc,
                    "volume":volume,"change":ch,"age_hours":round((now-ts)/3600,1),
                    "liquidity":num(first(a,"liquidity","liquidity_usd")),
                    "swaps":num(first(a,"swaps","swap_count")),
                    "rank":num(a.get("rank")),
                    "price":num(first(a,"price","price_usd")),
                    "visiting_count":num(a.get("visiting_count")),
                    "holders":num(first(a,"holder_count","holders"))}
    return rows

def peers(rows):
    arr=list(rows.values()) if isinstance(rows,dict) else list(rows)
    for a in arr:
        ps=[b for b in arr if b["mint"]!=a["mint"] and max(a["market_cap"],b["market_cap"])/min(a["market_cap"],b["market_cap"])<=1.25]
        a["peer_count"]=len(ps)
        a["turnover"]=a["volume"]/a["market_cap"]
        a["price_effect"]=a["change"]/a["turnover"] if a["turnover"]>0 else None
        if ps:
            a["peer_change_median"]=statistics.median(b["change"] for b in ps)
            a["peer_turnover_median"]=statistics.median(b["volume"]/b["market_cap"] for b in ps)
        else:
            a["peer_change_median"]=None
            a["peer_turnover_median"]=None
    # Separate conditional descriptive anomaly benchmark: peer absolute moves, robust and leave-one-out.
    for a in arr:
        ps=[b for b in arr if b["mint"]!=a["mint"] and max(a["market_cap"],b["market_cap"])/min(a["market_cap"],b["market_cap"])<=1.25 and .5<=((b["volume"]/b["market_cap"])/(a["turnover"] or 1e-12))<=2 and .5<=b["age_hours"]/a["age_hours"]<=2]
        a["conditional_n"]=len(ps)
        typical=statistics.median(abs(b["change"]) for b in ps) if len(ps)>=5 else None
        a["typical_abs_move"]=typical
        a["anomaly_ratio"]=a["change"]/typical if typical is not None and typical>0 else None
    return arr

def enrich(r6,r24):
    for a in r6:
        b=r24.get(a["mint"])
        a["volume24"]=b["volume"] if b else None
        a["change24"]=b["change"] if b else None
        a["v18"]=None;a["r18"]=None
        if b and b["volume"]>=a["volume"] and a["change"]>-100 and b["change"]>-100:
            a["v18"]=b["volume"]-a["volume"]
            a["r18"]=100*((1+b["change"]/100)/(1+a["change"]/100)-1)

def command():
    key=os.environ.get("GMGN_API_KEY","")
    if not key:raise RuntimeError("GMGN_API_KEY secret is missing; no live query performed")
    params=[{"chain":"sol","interval":period,"limit":500,"min_marketcap":30000,"max_marketcap":2000000,"min_created":"600m"} for period in ("6h","24h")]
    cli=os.environ.get("GMGN_CLI","gmgn-cli")
    cmd=[cli,"market","hot-searches","--params",json.dumps(params,separators=(",",":")),"--raw"]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=150,env=os.environ.copy())
    if p.returncode:raise RuntimeError("GMGN CLI request failed (details suppressed to avoid credential leakage)")
    return json.loads(p.stdout)

def run():
    now=dt.datetime.now(dt.timezone.utc)
    result=extract(command())
    six=normalize(result["6h"],now.timestamp())
    day=normalize(result["24h"],now.timestamp())
    if not result["6h"] or not result["24h"]:raise RuntimeError("GMGN returned empty time blocks; refusing success")
    records=peers(six);enrich(records,day)
    records.sort(key=lambda r:(r["price_effect"] is not None,r["price_effect"] or -1e12),reverse=True)
    stamp=now.isoformat()
    ROOT.joinpath("reports").mkdir(exist_ok=True)
    ROOT.joinpath("data").mkdir(exist_ok=True)
    # In a public repository the data are public; do not include private wallet holdings.
    snapshot={"utc":stamp,"source":"GMGN official market hot-searches","raw_6h":len(result["6h"]),
              "raw_24h":len(result["24h"]),"filtered_6h":len(records),"filtered_24h":len(day),
              "records":records}
    (ROOT/"data/latest.json").write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+"\n")
    with (ROOT/"data/history.jsonl").open("a") as f:f.write(json.dumps(snapshot,ensure_ascii=False)+"\n")
    cols=["mint","symbol","market_cap","age_hours","volume","change","turnover","price_effect","peer_count","conditional_n","anomaly_ratio","volume24","change24","v18","r18","liquidity","swaps","holders"]
    with (ROOT/"reports/latest.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore");w.writeheader();w.writerows(records)
    lines=["# GMGN SOL 热搜只读复评",f"抓取 UTC：{stamp}",f"来源：GMGN 官方 Hot Searches（分别为6h/24h快照；非全市场）",f"原始6h {len(result['6h'])}条，24h {len(result['24h'])}条；严格可核实筛选后6h {len(records)}条、24h {len(day)}条。","\n**样本覆盖率**：仅为接口返回条目；无法保证覆盖网页所有热搜或全市场。","**持仓**：尚未安全连接钱包，未复评私人持仓。","**1h/3h/6h未来收益**：当前仅保存快照；未经回填/到期观察，不声称已验证。","**三变量异常**：按市值(1.25倍)、换手(0.5-2倍)、币龄(0.5-2倍)同类条件，以对手绝对涨幅中位数作基准；需至少5个对手，否则记NA。","\n## 6h Price Effect 排名","|#|代币|市值USD|6h涨幅%|6h成交USD|PE|同市值对手数|条件异常|","|---:|---|---:|---:|---:|---:|---:|---:|"]
    for i,r in enumerate(records[:30],1):
        pe=r["price_effect"]; an=r["anomaly_ratio"]
        lines.append(f"|{i}|{r['symbol']} (`{r['mint']}`)|{r['market_cap']:.0f}|{r['change']:.2f}|{r['volume']:.0f}|{f'{pe:.2f}' if pe is not None else 'NA'}|{r['peer_count']}|{f'{an:.2f}' if an is not None else 'NA'}|")
    lines+=["\n## 24h / 前18h","6h和24h请求由一次 CLI 调用组成，但服务端时间截止点未保证绝对同步；仅当每个block的采样截止时间确认相同时，才能把V18和r18视为严谨拆分。当前CSV内计算值是暂存候选，不作为确定结论。","\n## 风险和下一步","PE对薄池、刷量和异常价格敏感；不是卖压收缩的证据。下轮需验证成交方向、池深、持有人和K线；未来收益需收集可追溯K线和交易成本。","数据不足时不推荐交易。"]
    (ROOT/"reports/latest.md").write_text("\n".join(lines)+"\n")
    print(f"Verified GMGN request: 6h={len(result['6h'])} 24h={len(result['24h'])}; filtered={len(records)}; {stamp}")

if __name__=="__main__":
    try:run()
    except Exception as exc:
        print("SCAN FAILED: "+str(exc).replace(os.environ.get("GMGN_API_KEY","###"),"[REDACTED]"),file=sys.stderr)
        sys.exit(1)
