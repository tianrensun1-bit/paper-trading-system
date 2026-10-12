#!/usr/bin/env python3
"""GMGN Hot Searches research. Read-only, stdlib-only. No wallet operations."""
import csv
import datetime as dt
import gzip
import html
import io
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import uuid

from contracts import ContractError, hot_tokens, normalize_info
from gmgn_api import GMGN, ProviderError, CLI_VERSION, SOURCE_COMMIT

ROOT = Path(__file__).resolve().parents[1]
def num(x):
    try:
        if isinstance(x, (dict,bool)): return None
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
        if raw.get("code") != 0:
            raise ValueError("API returned failure")
        raw=raw['data']
    return {period:hot_tokens(raw,period) for period in ('6h','24h')}

def normalize(items,now):
    """Normalize documented token-info objects, never hot-search percent aliases."""
    rows={}
    for a in items:
        r=normalize_info(a,now)
        mc,age=r['market_cap'],r['age_minutes']
        if mc is None or age is None or not 30000<=mc<=2000000 or age<600:continue
        mint=r['mint']
        if mint in rows:raise ContractError('duplicate token-info mint')
        row=dict(mint=mint,symbol=r['symbol'],market_cap=mc,age_hours=age/60,
                 volume=r['v6'],change=num(100*r['r6']) if r['r6'] is not None else None,
                 volume24=r['v24'],change24=num(100*r['r24']) if r['r24'] is not None else None,
                 price=r['price'],liquidity=r['liquidity'],observed_at=now,
                 holders=num(a.get('holder_count')),swaps=num(a['price'].get('swaps_6h')),
                 source_asof=None,windows_aligned=False,complete_24h=r['complete_24h'],
                 trade_signal='WAIT',decision_reason='结构与风险规则尚未定义或核验',
                 metric_version='pe-percent-v1')
        for field in ('buy_volume6','sell_volume6','buy_volume24','sell_volume24','buys6','sells6'):
            row[field]=r[field]
        rows[mint]=row
    return rows

def comparable(a,b):
    return max(a['market_cap'],b['market_cap'])/min(a['market_cap'],b['market_cap'])<=1.25+1e-12

def peers(rows):
    arr=list(rows.values()) if isinstance(rows,dict) else list(rows)
    for a in arr:
        a['turnover']=a['volume']/a['market_cap'] if a['volume'] is not None else None
        a['price_effect']=num(a['change']/a['turnover']) if a.get('turnover') and a['change'] is not None else None
        a['quality_flags']=','.join(flag for condition,flag in (
            (not a.get('volume'),'成交额缺失或为零'),
            (a.get('liquidity') is None,'流动性缺失'),
            (a.get('liquidity')==0,'无可核实流动性'),
            (a.get('change') is not None and a['change']>100,'涨幅超过100%'),
            (a.get('is_wash_trading') is True,'刷量标记'),
            (a['price_effect'] is None,'PE不可计算')) if condition)
    for a in arr:
        ps=[b for b in arr if b['mint']!=a['mint'] and comparable(a,b)]
        observed=[b for b in ps if b.get('change') is not None and b.get('volume') is not None]
        a.update(peer_count=len(ps),peer_observed_count=len(observed),positive_pe_rank=None,
                 relative_return_percentile=None,peer_change_median=None,peer_turnover_median=None,
                 low_volume_higher_gain_count=0,higher_volume_less_loss_count=0)
        if observed:
            a['peer_change_median']=statistics.median(b['change'] for b in observed)
            a['peer_turnover_median']=statistics.median(b['turnover'] for b in observed)
            if a['change'] is not None:
                a['relative_return_percentile']=100*sum(b['change']<a['change'] for b in observed)/len(observed)
        if a['change'] is not None and a['change']>0 and a['price_effect'] is not None:
            up=[b for b in observed if b['change']>0 and b['price_effect'] is not None]
            if up:
                a['positive_pe_rank']=1+sum(b['price_effect']>a['price_effect'] for b in up)
            a['low_volume_higher_gain_count']=sum(b['change']>0 and a['volume']<b['volume'] and a['change']>b['change'] for b in observed)
        elif a['change'] is not None and a['change']<0 and a['volume'] is not None:
            a['higher_volume_less_loss_count']=sum(b['change']<a['change']<0 and a['volume']>b['volume'] for b in observed)
    # Independent descriptive matched-neighbor benchmark; no prediction claim.
    for a in arr:
        ps=[]
        if a.get('turnover') and a['change'] is not None:
            for b in arr:
                if b['mint']==a['mint'] or not b.get('turnover') or b['change'] is None or not comparable(a,b):continue
                if not .5<=b['turnover']/a['turnover']<=2 or not .5<=b['age_hours']/a['age_hours']<=2:continue
                if a.get('liquidity') and (not b.get('liquidity') or not .5<=b['liquidity']/a['liquidity']<=2):continue
                ps.append(b)
        a["conditional_n"]=len(ps)
        typical=statistics.median(abs(b["change"]) for b in ps) if len(ps)>=8 else None
        a["typical_abs_move"]=typical
        baseline=statistics.median(b['change'] for b in ps) if typical is not None else None
        a['typical_signed_move']=baseline
        a['anomaly_delta_pp']=num(a['change']-baseline) if baseline is not None else None
        a['anomaly_ratio']=num(a['anomaly_delta_pp']/max(2,typical)) if a['anomaly_delta_pp'] is not None else None
        a['anomaly_controls']='市值,相对成交额,币龄'+(',流动性' if a.get('liquidity') else '；流动性未控制')
    return arr

def enrich(r6,r24):
    for a in r6:
        b=r24.get(a["mint"])
        a["volume24"]=b["volume"] if b else None
        a["change24"]=b["change"] if b else None
        a.update(v18=None,r18=None,v18_provisional=None,r18_provisional=None,
                 hourly_activity_ratio=None,window_status='截止点未核实，18h仅作暂算')
        if a.get('age_hours') is None or a['age_hours']<24:
            a['window_status']='币龄不足24h或未知，不能拆完整前18h';continue
        if not b or any(v is None for v in (a['volume'],a['change'],b['volume'],b['change'])):continue
        if b['volume']<a['volume'] or min(a['change'],b['change'])<=-100:
            a['window_status']='窗口值不一致，禁止拆分';continue
        v18=b['volume']-a['volume']
        r18=100*((1+b['change']/100)/(1+a['change']/100)-1)
        a.update(v18_provisional=v18,r18_provisional=r18)
        if a.get('windows_aligned') is True:
            a.update(v18=v18,r18=r18,hourly_activity_ratio=3*a['volume']/v18 if v18 else None,
                     window_status='已确认对齐')

def command():
    return GMGN().hot()[0]

def all_pairs(records):
    result=[]
    for i,a in enumerate(records):
        for b in records[i+1:]:
            if not comparable(a,b):continue
            result.append(dict(a=a['mint'],b=b['mint'],
                price_effect_difference=a['price_effect']-b['price_effect']
                    if a['price_effect'] is not None and b['price_effect'] is not None else None,
                return_difference_pp=a['change']-b['change']
                    if a['change'] is not None and b['change'] is not None else None))
    return result

def safe_json(path,value):
    text=json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)
    key=os.environ.get('GMGN_API_KEY')
    if key:text=text.replace(key,'[REDACTED]')
    Path(path).write_text(text+'\n',encoding='utf-8')

def csv_save(path,records):
    columns=sorted({k for row in records for k in row})
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for row in records:
            writer.writerow({k:("'"+v if isinstance(v,str) and v[:1] in '=+-@\t\r' else v) for k,v in row.items()})

def cell(value):
    if value is None:return 'NA'
    if isinstance(value,float):return f'{value:.5g}'
    text=html.escape(str(value)).replace('|','&#124;').replace('\n',' ').replace('\r',' ')
    for char in ('\\','[',']','`','*','_'):text=text.replace(char,'\\'+char)
    return text

def table(rows,cols):
    return '\n'.join(['|'+'|'.join(label for _,label in cols)+'|',
                      '|'+'|'.join('---' for _ in cols)+'|']+
                     ['|'+'|'.join(cell(row.get(key)) for key,_ in cols)+'|' for row in rows])

def render(snapshot):
    rows=snapshot['records']
    up=[r for r in rows if r.get('change') is not None and r['change']>0 and r['price_effect'] is not None]
    down=[r for r in rows if r['higher_volume_less_loss_count']>0]
    anomalous=sorted(rows,key=lambda r:(r['anomaly_ratio'] is not None,r['anomaly_ratio'] or 0),reverse=True)
    return '\n\n'.join([
        '# GMGN SOL 动态量价研究：数据验证阶段',
        f"UTC：{snapshot['utc']}；状态：{snapshot['status']}；版本：pe-percent-v1",
        f"6h热搜 {snapshot['raw_6h']} 币，24h热搜 {snapshot['raw_24h']} 币，复核后 {len(rows)} 币，共 {snapshot['pair_count']} 对。",
        '来源：官方Hot Searches + 每Mint同一次token-info。全球Top-500的SOL子集，沿用官方默认renounced/frozen；不代表全链。',
        'Price Effect = 6h收益百分点 / (6h美元成交额/当前市值)。收益从当前价/窗口起点价计算，未猜测百分比字段。',
        '各Mint顺序采集，不是严格同一时刻的原子快照。采集跨度见覆盖率，逐币observed_at保留在CSV；横向比较属于近似同期比较。',
        '## 覆盖率', '```json\n'+json.dumps(snapshot['coverage'],ensure_ascii=False,indent=2)+'\n```',
        '## 上涨币原始 Price Effect（预览30，全部数据见CSV）',
        table(up[:30],[('symbol','币'),('market_cap','市值USD'),('change','6h收益%'),('volume','6h成交USD'),
                      ('price_effect','PE'),('positive_pe_rank','正向同类排名'),('peer_count','全部对手'),('peer_observed_count','可比较对手'),
                      ('quality_flags','质量限制')]),
        '## 高量少跌（单独筛选，不加入正向PE得分）',
        table(down,[('mint','Mint'),('change','6h收益%'),('volume','6h成交USD'),('higher_volume_less_loss_count','符合对手数')]),
        '## 独立条件异常排名',
        '市值比≤1.25，相对成交额/币龄比0.5–2，可用流动性同样匹配；留一法至少8个参照。典型绝对波动为|收益|中位数；异常为有向收益偏离条件中位数，按max(2百分点,典型绝对波动)归一化。仅描述性分数，不是概率、显著性证明或预测模型。与PE的相关性不能当成独立因果证据。',
        table(anomalous,[('mint','Mint'),('conditional_n','参照数'),('typical_abs_move','典型绝对波动%'),
                        ('typical_signed_move','条件有向收益%'),('anomaly_delta_pp','偏离百分点'),('anomaly_ratio','异常分数'),('anomaly_controls','控制条件')]),
        '## 24h与此前18h',
        '接口未提供可核实的统一窗口截止点，因此r18/v18确认值为空。CSV中的provisional字段仅作暂算，不能用于资格判断。币龄不足24h、字段缺失或V24<V6时不拆完整18h。',
        table(rows,[('mint','Mint'),('volume24','24h成交USD'),('change24','完整24h收益%'),('v18','确认18h成交'),('r18','确认18h收益%'),
                    ('buy_volume6','6h买额'),('sell_volume6','6h卖额'),('window_status','窗口状态')]),
        '## 交易资格、持仓与研究状态',
        '所有资格为WAIT：15m/1h/4h结构、风险条件、背离、再入场与保护规则尚未定义并验证。排名不直接产生买卖指令。未连接私人钱包或真实成交历史。',
        '本仓库尚未完成H1–H4回测或未来收益回补；历史快照保留全部合格样本，不只保留前十。低流动性、刷量、集中持仓和样本选择均可能解释高PE，不能据此证实有效卖盘收缩。',
        '公开仓库只保存市场数据；私人钱包、持仓和成交资料须另行配置私有存储。'])+'\n'

def run(root=None,provider_factory=None):
    root=Path(root or ROOT)
    (root/'reports').mkdir(parents=True,exist_ok=True)
    (root/'data').mkdir(parents=True,exist_ok=True)
    run_id=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    folder=root/'data/runs'/run_id;folder.mkdir(parents=True)
    manifest=dict(run_id=run_id,status='running',cli_version=CLI_VERSION,source_commit=SOURCE_COMMIT,
                  github_run_id=os.environ.get('GITHUB_RUN_ID','local'),
                  code_commit=os.environ.get('GITHUB_SHA','local'),started_at=time.time())
    safe_json(root/'data/status.json',manifest)
    try:
        client=(provider_factory or GMGN)(folder/'raw')
        raw,received=client.hot();blocks=extract(raw)
        if not blocks['6h'] or not blocks['24h']:raise ProviderError('Empty SOL hot-search block')
        records=[];excluded=[]
        for hot in blocks['6h']:
            info,observed=client.info(hot['address'])
            if info.get('address')!=hot['address']:raise ContractError('token-info mint mismatch')
            normalized=normalize([info],observed)
            if not normalized:
                excluded.append(dict(mint=hot['address'],reason='市值/创建币龄不可核实或已不在范围'));continue
            row=normalized[hot['address']]
            row.update(hot_rank=num(hot.get('rank')),visiting_count=num(hot.get('visiting_count')),
                       is_wash_trading=hot.get('is_wash_trading'),rug_ratio=num(hot.get('rug_ratio')),
                       top_10_holder_rate=num(hot.get('top_10_holder_rate')))
            records.append(row)
        records=peers(records)
        day={r['mint']:dict(volume=r['volume24'],change=r['change24']) for r in records}
        enrich(records,day)
        records.sort(key=lambda r:(r.get('change') is not None and r['change']>0 and r['price_effect'] is not None,r['price_effect'] or 0),reverse=True)
        pairs=all_pairs(records)
        span=time.time()-received
        if span>1800:raise ProviderError('Collection span exceeded 30 minutes')
        missing={k:sum(r.get(k) is None for r in records) for k in (
            'change','volume','liquidity','buy_volume6','sell_volume6','volume24','change24','buy_volume24','sell_volume24')}
        young=sum(not r['complete_24h'] for r in records)
        unexpected_missing=any(count>(young if k=='change24' else 0) for k,count in missing.items())
        status='partial' if unexpected_missing or not records else 'success'
        snapshot=dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),run_id=run_id,status=status,
                      source='GMGN official hot-searches + token/info',metric_version='pe-percent-v1',
                      raw_6h=len(blocks['6h']),raw_24h=len(blocks['24h']),records=records,pair_count=len(pairs),
                      coverage=dict(excluded=len(excluded),collection_seconds=span,missing=missing,
                                    incomplete_24h=young,
                                    confirmed_aligned_windows=sum(r['windows_aligned'] is True for r in records),
                                    source_asof='未提供'))
        safe_json(root/'data/latest.json',snapshot)
        text=json.dumps(snapshot,ensure_ascii=False,allow_nan=False)
        with gzip.open(folder/'snapshot.json.gz','wt',encoding='utf-8') as f:f.write(text)
        with (root/'data/history.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(run_id=run_id,utc=snapshot['utc'],metric_version='pe-percent-v1',
                                   snapshot=f'runs/{run_id}/snapshot.json.gz'))+'\n')
        csv_save(root/'reports/latest.csv',records);csv_save(folder/'records.csv',records)
        csv_save(folder/'pairs.csv',pairs)
        safe_json(folder/'excluded.json',excluded)
        report=render(snapshot)
        (root/'reports/latest.md').write_text(report,encoding='utf-8')
        (folder/'report.md').write_text(report,encoding='utf-8')
        manifest.update(status=status,coverage=snapshot['coverage'])
    except Exception as exc:
        error=str(exc) if isinstance(exc,(ProviderError,ContractError)) else type(exc).__name__
        manifest.update(status='failed',error=error)
        safe_json(root/'data/latest.json',dict(status='failed',run_id=run_id,error=error))
        csv_save(root/'reports/latest.csv',[dict(status='failed',run_id=run_id,error=error)])
        (root/'reports/latest.md').write_text('# 最新扫描失败\n\n'+error+
            '\n\n没有生成成功行情报告；已有历史快照保留，不能把旧报告当作最新行情。\n',encoding='utf-8')
    manifest['finished_at']=time.time()
    safe_json(folder/'manifest.json',manifest);safe_json(root/'data/status.json',manifest)
    print('Read-only data run: '+manifest['status'])
    return 0 if manifest['status']=='success' else 1

if __name__=="__main__":
    raise SystemExit(run())
