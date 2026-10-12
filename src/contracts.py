import math
import re


class ContractError(ValueError):
    pass


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{32,44}', value):
        raise ContractError('invalid Solana address')
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    n = 0
    for c in value:
        n = n * 58 + alphabet.index(c)
    size = (n.bit_length() + 7) // 8 + len(value) - len(value.lstrip('1'))
    if size != 32:
        raise ContractError('Solana address must decode to 32 bytes')
    return value


def number(value, *, nonnegative=False):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ContractError('boolean numeric field')
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise ContractError('invalid numeric field') from None
    if not math.isfinite(n) or (nonnegative and n < 0):
        raise ContractError('nonfinite or negative numeric field')
    return n


def hot_tokens(data, interval):
    if not isinstance(data, list):
        raise ContractError('hot-search data must be blocks')
    blocks = [b for b in data if b.get('chain') == 'sol' and b.get('interval') == interval]
    if len(blocks) != 1 or not isinstance(blocks[0].get('tokens'), list):
        raise ContractError('missing or duplicated SOL interval block')
    rows = blocks[0]['tokens']
    seen = set()
    for r in rows:
        mint = address(r.get('address'))
        if mint in seen or r.get('chain', 'sol') != 'sol':
            raise ContractError('duplicate mint or wrong chain')
        seen.add(mint)
    return rows


def normalize_info(data, observed_at):
    """Use prices at both window starts; never infer percent units."""
    mint = address(data.get('address'))
    p = data.get('price')
    if not isinstance(p, dict):
        raise ContractError('token-info price must be an object')
    price = number(p.get('price'), nonnegative=True)
    supply = number(data.get('circulating_supply'), nonnegative=True)
    created = number(data.get('creation_timestamp'), nonnegative=True)
    if created is not None and (created > observed_at or created < 1_000):
        raise ContractError('invalid creation timestamp; expected Unix seconds')
    row = dict(mint=mint, symbol=str(data.get('symbol', ''))[:80], price=price,
               observed_at=observed_at, market_cap=number(price*supply,nonnegative=True) if price is not None and supply is not None else None,
               liquidity=number(data.get('liquidity'), nonnegative=True),
               age_minutes=(observed_at-created)/60 if created is not None else None)
    for h in (6, 24):
        start = number(p.get(f'price_{h}h'), nonnegative=True)
        row[f'r{h}'] = number(price/start-1) if price is not None and start and price > 0 else None
        row[f'r{h}_api'] = row[f'r{h}']
        row[f'complete_{h}h'] = row['age_minutes'] is not None and row['age_minutes'] >= h*60
        if not row[f'complete_{h}h']:
            row[f'r{h}'] = None
        row[f'v{h}'] = number(p.get(f'volume_{h}h'), nonnegative=True)
        for field in ('buy_volume', 'sell_volume', 'buys', 'sells'):
            row[f'{field}{h}'] = number(p.get(f'{field}_{h}h'), nonnegative=True)
    # The API does not document an as-of timestamp for these rolling fields.
    row['source_asof'] = None
    row['time_basis'] = 'same-response rolling windows; upstream as-of unavailable'
    return row
