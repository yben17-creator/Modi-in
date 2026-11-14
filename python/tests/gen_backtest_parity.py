"""Parity cases for the TS port of validation/backtest.py (walk_forward).
Usage: python tests/gen_backtest_parity.py <out.json>   (prices/events are synthetic test inputs, not market data)"""
import json, math, sys
from types import SimpleNamespace
sys.path.insert(0, '.')
import pandas as pd
from evi.models import CompanyData, Val
from evi.analytics import timing
from evi.validation.backtest import walk_forward

def prices(n, seed, start="2021-01-04"):
    idx = pd.bdate_range(start, periods=n)
    x, out = 40.0 + seed, []
    for i in range(n):
        x *= 1 + 0.014 * math.sin(i * 0.31 + seed) + 0.005 * math.cos(i * 1.9 * (seed + 1))
        out.append(round(x, 4))
    return pd.DataFrame({"close": out}, index=idx)

def company(tk, seed, sector, mcap, vol, n=1300, step=63, start_i=70):
    df = prices(n, seed)
    dates = [d.date().isoformat() for d in df.index]
    evs = [{"accepted": f"{dates[i]}T{'16:05:00' if k % 2 else '08:00:00'}.000Z", "filed": dates[i], "url": f"u/{tk}/{i}"}
           for k, i in enumerate(range(start_i, n - 25, step))]
    cd = CompanyData(tk, 1, tk, "Nasdaq", sector); cd.prices = df; cd.prices_source = "TEST"; cd.earnings_events = evs
    return cd

bench = prices(1500, 9, start="2020-06-01")
def res(cd, mcap, vol, b):
    t = timing.analyze(cd, b, 15, 8, 10)
    return SimpleNamespace(t=t, cd=cd, m={"mcap": Val(mcap)}, vol=vol, ticker=cd.ticker)

specs = [("AAA", 1, "Software & SaaS", 2e11, 0.02), ("BBB", 2, "Semiconductors", 5e9, 0.04), ("CCC", 3, None, 1e9, None), ("DDD", 4, "Software & SaaS", None, 0.025)]
cases = []
for name, b in (("with_benchmark", bench), ("no_benchmark", None)):
    cds = [company(tk, s, sec, m, v) for tk, s, sec, m, v in specs]
    rs = [res(cd, m, v, b) for cd, (_, _, _, m, v) in zip(cds, specs)]
    out = walk_forward(rs, b)
    cases.append({"name": name, "bench": [[d.date().isoformat(), float(c)] for d, c in zip(b.index, b["close"])] if b is not None else None,
                  "companies": [{"ticker": cd.ticker, "sector": cd.sector, "mcap": m, "vol": v,
                                 "prices": [[d.date().isoformat(), float(c)] for d, c in zip(cd.prices.index, cd.prices["close"])],
                                 "events": cd.earnings_events} for cd, (_, _, _, m, v) in zip(cds, specs)], "out": out})
# too few events
cd = company("EEE", 5, "Cybersecurity", 3e9, 0.02, n=400, step=90)
out = walk_forward([res(cd, 3e9, 0.02, None)], None)
cases.append({"name": "too_few_events", "bench": None, "companies": [{"ticker": "EEE", "sector": "Cybersecurity", "mcap": 3e9, "vol": 0.02,
              "prices": [[d.date().isoformat(), float(c)] for d, c in zip(cd.prices.index, cd.prices["close"])], "events": cd.earnings_events}], "out": out})
json.dump(cases, open(sys.argv[1], "w"), ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
for c in cases: print(c["name"], c["out"].get("available"), c["out"].get("n"), c["out"].get("split_date"), c["out"].get("why"))
