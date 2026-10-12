"""Prevent a setup failure from leaving the previous success as the latest state."""
import datetime as dt
import json
import os
from pathlib import Path

data=Path('data');reports=Path('reports')
data.mkdir(exist_ok=True);reports.mkdir(exist_ok=True)
path=data/'status.json'
old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
run_id=os.environ.get('GITHUB_RUN_ID','local')
if old.get('github_run_id')!=run_id:
    status=dict(status='failed',github_run_id=run_id,utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                error='工作流准备或采集步骤失败，查看Actions失败步骤')
    path.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (data/'latest.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (reports/'latest.md').write_text('# 最新扫描失败\n\n'+status['utc']+'\n\n'+status['error']+
                                   '\n\n旧快照保留，不能当作本次成功行情。\n',encoding='utf-8')
    (reports/'latest.csv').write_text('status,github_run_id\nfailed,'+run_id+'\n',encoding='utf-8-sig')
