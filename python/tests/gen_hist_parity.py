"""Parity cases for the TS port of analytics/valuation.py historical_multiples (own average P/S, EV/Revenue, EV/FCF at
fiscal year-ends). Usage: python tests/gen_hist_parity.py <out.json>   (all numbers are arbitrary test inputs, not company data)"""
import json, math, sys
sys.path.insert(0, '.')
import pandas as pd
from evi.models import CompanyData
from evi.analytics import valuation as V

ENDS = ["2019-12-31", "2020-12-31", "2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"]


def prices(start="2019-06-03", end="2026-03-31", gap=None):
    days = pd.bdate_range(start, end)
    px = [round(40 + 0.03 * i + 6 * math.sin(i / 37.0), 4) for i in range(len(days))]
    rows = [(d.strftime("%Y-%m-%d"), p) for d, p in zip(days, px)]
    if gap:
        rows = [r for r in rows if not (gap[0] <= r[0] <= gap[1])]
    return rows


def series(vals, ends=ENDS):
    return [{"end": e, "val": v} for e, v in zip(ends, vals) if v is not None]


BASE = {
    "revenue": series([1.0e9, 1.2e9, 1.5e9, 1.7e9, 2.0e9, 2.3e9, 2.6e9]),
    "ocf": series([2.0e8, 2.6e8, 3.1e8, 3.3e8, 4.2e8, 5.0e8, 5.9e8]),
    "capex": series([5.0e7, 6.0e7, 7.0e7, 9.0e7, 1.0e8, 1.1e8, 1.2e8]),
    "diluted_shares": series([1.00e8, 1.01e8, 1.03e8, 1.04e8, 1.05e8, 1.06e8, 1.07e8]),
    "cash_instant": series([3.0e8, 3.5e8, 4.0e8, 5.0e8, 6.0e8, 7.0e8, 8.0e8]),
    "st_investments_instant": series([1.0e8, 1.0e8, 1.5e8, 2.0e8, 2.0e8, 2.5e8, 3.0e8]),
    "st_debt_instant": series([5.0e7, 5.0e7, 0, 2.0e7, 2.0e7, 3.0e7, 3.0e7]),
    "lt_debt_noncurrent_instant": series([4.0e8, 4.0e8, 3.5e8, 3.0e8, None, 2.0e8, 2.0e8]),
    "lt_debt_total_instant": series([None, None, None, None, 3.0e8, None, None]),
}


def case(name, annual_over=None, px="default", years=5):
    annual = {**BASE, **(annual_over or {})}
    cd = CompanyData("TST", 1, "T", "Nasdaq", "Software & SaaS")
    cd.annual = {k: [dict(x) for x in v] for k, v in annual.items()}
    rows = prices() if px == "default" else px
    cd.prices = None if rows is None else pd.DataFrame({"close": [p for _, p in rows]}, index=pd.to_datetime([d for d, _ in rows]))
    out = V.historical_multiples(cd, years)
    return {"name": name, "annual": annual, "prices": rows, "years": years, "out": out}


cases = [
    case("base"),
    case("three_years", years=3),
    case("split_10_for_1_unrestated", {"diluted_shares": series([1.0e8, 1.01e8, 1.02e8, 1.03e9, 1.04e9, 1.05e9, 1.06e9])}),
    case("price_gap_skips_year", px=prices(gap=("2021-12-20", "2022-01-10"))),
    case("negative_fcf_year", {"capex": series([5.0e7, 6.0e7, 4.0e8, 9.0e7, 1.0e8, 1.1e8, 1.2e8])}),
    case("missing_ocf_and_cash", {"ocf": series([2.0e8, 2.6e8, None, 3.3e8, 4.2e8, 5.0e8, 5.9e8]),
                                  "cash_instant": series([3.0e8, None, 4.0e8, 5.0e8, 6.0e8, 7.0e8, 8.0e8])}),
    case("missing_shares_year", {"diluted_shares": series([1.00e8, 1.01e8, None, 1.04e8, 1.05e8, 1.06e8, 1.07e8])}),
    case("one_point_only", px=prices(start="2024-06-03")),
    case("no_overlap", px=prices(start="2025-06-02")),
    case("no_prices", px=None),
    case("single_revenue_year", {"revenue": series([2.6e9], ["2025-12-31"])}),
]
json.dump({"cases": cases}, open(sys.argv[1], "w"), ensure_ascii=False)
for c in cases:
    o = c["out"]
    print(c["name"], len(o["points"]), o["ps"], o["ev_rev"], o["ev_fcf"], o["note"])
