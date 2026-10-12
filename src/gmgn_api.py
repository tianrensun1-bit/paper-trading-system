import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from contracts import address, number

CLI_VERSION = '1.6.6'
SOURCE_COMMIT = '4575ef539e6a3115fa0481d41285cb79e77970bf'


class ProviderError(RuntimeError):
    pass


def validate_candles(data):
    if not isinstance(data, dict) or not isinstance(data.get('list'), list):
        raise ProviderError('invalid candle response schema')
    result, seen, units = [], set(), set()
    for c in data['list']:
        t = number(c.get('time'), nonnegative=True)
        if t is not None and 1_000_000_000_000 < t < 10_000_000_000_000 and t%1000==0:
            t /= 1000
            unit='milliseconds'
        else:
            unit='seconds'
        units.add(unit)
        if t is None or not 1_000_000_000 < t < 10_000_000_000 or t != int(t) or t in seen or len(units)>1:
            raise ProviderError('invalid/duplicate/mixed-unit candle timestamp')
        seen.add(t)
        r = dict(time=int(t),source_time_unit=unit)
        for k in ('open','close','high','low'):
            r[k] = number(c.get(k), nonnegative=True)
            if r[k] is None or r[k] <= 0:
                raise ProviderError('missing or zero candle price')
        if not r['low'] <= min(r['open'],r['close']) <= max(r['open'],r['close']) <= r['high']:
            raise ProviderError('invalid OHLC bounds')
        # Live response contradicts official units. Keep both unlabelled; OHLC-only
        # forward validation does not rely on either trading-volume field.
        r['raw_amount'] = number(c.get('amount'), nonnegative=True)
        r['raw_volume'] = number(c.get('volume'), nonnegative=True)
        result.append(r)
    return sorted(result,key=lambda c:c['time'])


class GMGN:
    """Only three read-only CLI commands are exposed. No inherited private key/config."""
    def __init__(self, raw_dir=None):
        if os.environ.get('GMGN_KEY_ROTATION_CONFIRMED') != 'true':
            raise ProviderError('A fresh GMGN key and revocation confirmation are required before live access')
        if not os.environ.get('GMGN_API_KEY'):
            raise ProviderError('GMGN_API_KEY is missing; set the GitHub Actions Secret')
        self.raw_dir = Path(raw_dir) if raw_dir else None
        self.seq = 0
        self.last = 0
        node = shutil.which('node')
        # Explicit local install; do not discover a different global CLI version.
        cli = Path(__file__).resolve().parents[1]/'node_modules/gmgn-cli/dist/index.js'
        if not node or not cli.is_file():
            raise ProviderError('pinned gmgn-cli missing; run npm ci')
        self.command = [node,str(cli)]
        package = json.loads((cli.parents[1]/'package.json').read_text(encoding='utf-8'))
        if package['version'] != CLI_VERSION:
            raise ProviderError('gmgn-cli version does not match audited contract')

    def _call(self, args):
        if tuple(args[:2]) not in {('market','hot-searches'),('market','kline'),('token','info')}:
            raise ProviderError('command not allowed')
        time.sleep(max(0, .8-(time.monotonic()-self.last)))
        started = time.time()
        # Official config gives global .env priority. Isolate HOME/cwd and strip keys.
        with tempfile.TemporaryDirectory(prefix='gmgn-readonly-') as scratch:
            env = {k:v for k,v in os.environ.items() if k.upper() in {
                'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','NODE_EXTRA_CA_CERTS'}}
            env.update(HOME=scratch, USERPROFILE=scratch, GMGN_API_KEY=os.environ['GMGN_API_KEY'],
                       NODE_OPTIONS='--dns-result-order=ipv4first')
            try:
                result = subprocess.run(self.command+args+['--raw'],cwd=scratch,env=env,
                                        capture_output=True,text=True,encoding='utf-8',timeout=90)
            except (OSError, subprocess.TimeoutExpired):
                raise ProviderError('GMGN process/timeout failure') from None
        self.last = time.monotonic()
        if result.returncode:
            # Never print raw stdout/stderr, request headers or upstream error bodies.
            category = next((s for s in ('401','403','429','RATE_LIMIT_BANNED','RATE_LIMIT_EXCEEDED')
                             if s in result.stderr), 'request_failure')
            raise ProviderError('GMGN read failed: '+category)
        try:
            data = json.loads(result.stdout.replace(os.environ['GMGN_API_KEY'],'[REDACTED]'))
        except (ValueError, TypeError):
            raise ProviderError('GMGN output is not a single JSON value') from None
        ended = time.time()
        if self.raw_dir:
            self.raw_dir.mkdir(parents=True,exist_ok=True)
            self.seq += 1
            raw = json.dumps(dict(command=args,started_at=started,received_at=ended,data=data),ensure_ascii=False)
            # Defensive redaction even if a remote response unexpectedly echoes the key.
            raw = raw.replace(os.environ['GMGN_API_KEY'],'[REDACTED]')
            with gzip.open(self.raw_dir/f'{self.seq:06d}.json.gz','wt',encoding='utf-8') as f:
                f.write(raw)
        return data, ended

    def hot(self):
        params = [dict(label='hot-search',chain='sol',interval=h,limit=500,
                       min_marketcap=30000,max_marketcap=2000000,min_created='600m') for h in ('6h','24h')]
        return self._call(['market','hot-searches','--params',json.dumps(params)])

    def info(self, mint):
        return self._call(['token','info','--chain','sol','--address',address(mint)])

    def candles(self,mint,start,end):
        # Real 180-minute queries returned only the LAST 100 candles. Request at
        # most 90 minutes (91 rows with an inclusive upper bound) to avoid truncation.
        result = {}
        for a in range(start,end,90*60):
            b = min(end,a+90*60)
            data,_ = self._call(['market','kline','--chain','sol','--address',address(mint),
                                 '--resolution','1m','--from',str(a),'--to',str(b)])
            for c in validate_candles(data):
                if a <= c['time'] < b:
                    result[c['time']] = c
        return sorted(result.values(),key=lambda c:c['time'])
