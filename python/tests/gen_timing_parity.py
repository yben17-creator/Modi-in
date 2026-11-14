"""Parity cases for the TS port of analytics/timing.py (analyze, day0_index, best_window).
Usage: python tests/gen_timing_parity.py <out.json>   (prices and events are synthetic test inputs, not market data)"""
import json, math, sys
sys.path.insert(0, '.')
import numpy as np
import pandas as pd
from evi.models import CompanyData
from evi.analytics import timing

def prices(n, seed, start="2023-01-02"):
    idx = pd.bdate_range(start, periods=n)
    x, out = 50.0, []
    for i in range(n):
        x *= 1 + 0.015 * math.sin(i * 0.37 + seed) + 0.004 * math.cos(i * 1.7 + seed)
        out.append(round(x, 4))
    return pd.DataFrame({"close": out}, index=idx)

def ev(acc): return {"accepted": acc, "filed": acc[:10], "url": f"u/{acc}"}
df = prices(900, 1)
bench = prices(905, 2, start="2022-12-26")
dates = [d.date().isoformat() for d in df.index]
events = []
for k, i in enumerate(range(60, 860, 63)):
    d = dates[i]
    t = ["16:05:12", "07:30:00", "12:00:00", "16:00:00"][k % 4]
    events.append(ev(f"{d}T{t}.000Z"))
events.append(ev("2023-07-01T10:00:00.000Z"))  # Saturday → next session
events.append(ev("2023-01-03T16:30:00.000Z"))  # too early (no 30 days before)
events.append(ev(dates[-5] + "T08:00:00.000Z"))  # too late (no 20 days after)
events.append(ev(dates[300]))  # date only → same session

cases = []
def case(name, df, bench, events, cost=15, min_events=8, max_years=10):
    cd = CompanyData("TST", 1, "T", "Nasdaq", None); cd.prices = df; cd.prices_source = "TEST"; cd.earnings_events = events
    t = timing.analyze(cd, bench, cost, min_events, max_years)
    b = timing.best_window(t)
    cases.append({"name": name, "prices": [[d.date().isoformat(), float(c)] for d, c in zip(df.index, df["close"])] if df is not None else None,
                  "bench": [[d.date().isoformat(), float(c)] for d, c in zip(bench.index, bench["close"])] if bench is not None else None,
                  "events": events, "cost": cost, "min_events": min_events, "max_years": max_years, "out": t, "best": b})
case("with_benchmark", df, bench, events)
case("no_benchmark_min3", df, None, events[:6], min_events=3)
case("few_events", df, None, events[:2])
case("no_prices", None, None, events)
case("no_events", df, None, [])
case("short_window_years", df, None, events, max_years=1)
json.dump(cases, open(sys.argv[1], "w"), ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
for c in cases: print(c["name"], c["out"].get("available"), c["out"].get("n"), c["out"].get("why"), c["best"] and c["best"]["label"])
