"""Parity cases for the TS port of momentum.daily_vol (pandas pct_change().tail(days).std(), ddof=1).
Usage: python tests/gen_prices_parity.py <out.json>   (price series are synthetic test inputs, not market data)"""
import json, math, sys
sys.path.insert(0, '.')
import pandas as pd
from evi.analytics.momentum import daily_vol

def series(n, seed):
    x, out = 100.0, []
    for i in range(n):
        x *= 1 + 0.02 * math.sin(i * 0.7 + seed) + 0.003 * math.cos(i * 1.3 * seed)
        out.append(round(x, 4))
    return out
cases = []
for n, seed in ((10, 1), (29, 2), (30, 3), (60, 4), (120, 5), (121, 6), (300, 7)):
    closes = series(n, seed)
    df = pd.DataFrame({"close": closes})
    cases.append({"n": n, "closes": closes, "vol": daily_vol(df), "vol60": daily_vol(df, 60) if n >= 30 else None})
json.dump(cases, open(sys.argv[1], "w"), indent=1)
for c in cases: print(c["n"], c["vol"], c["vol60"])
