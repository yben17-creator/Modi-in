"""Parity cases for the TS port of scores.earnings + estimate_revision.
Usage: python tests/gen_earnings_score_parity.py <out.json>   (all inputs are arbitrary test values, not company data)"""
import json, sys
from dataclasses import asdict
sys.path.insert(0, '.')
from evi.models import CompanyData, Val
from evi.analytics import scores

def sur(n, beat_every=1, sp=5.0):
    return [{"period": f"2024-{(i % 12) + 1:02d}-28", "actual": 1.0 + (0.1 if i % beat_every == 0 else -0.1), "estimate": 1.0,
             "surprise_pct": None if sp is None else sp + i * 0.7} for i in range(n)]
def hist(*rows):
    return [{"day": d, "period": p, "eps_est": e, "rev_est": None, "source": "t"} for d, p, e in rows]

def case(name, surprises=(), history=(), guidance=None, ret3m=None, reactions=None, mos=None):
    cd = CompanyData("TST", 1, "T", "Nasdaq", "Software & SaaS")
    cd.surprises = list(surprises); cd.estimate_history = list(history)
    if guidance: cd.manual = {"guidance": guidance}
    m = {"ret3m": Val(ret3m)}
    t = {"reactions": reactions} if reactions is not None else None
    sc = scores.earnings(cd, m, {"mos": mos}, t)
    return {"name": name, "surprises": list(surprises), "history": list(history), "guidance": guidance, "ret3m": ret3m,
            "reactions": reactions, "mos": mos, "revision": scores.estimate_revision(cd), "score": asdict(sc)}

H_UP = hist(("2026-09-01", "2026Q4", 1.00), ("2026-09-20", "2026Q4", 1.02), ("2026-10-15", "2026Q4", 1.06))
cases = [
    case("full_8_quarters", sur(8), H_UP, "raised", 0.05, [0.03, -0.01, 0.02], 0.25),
    case("few_quarters_partial", sur(4, 2), ret3m=-0.1, mos=0.5),
    case("no_surprise_pct", sur(8, 3, sp=None), ret3m=0.2),
    case("negative_surprises", [{"period": "2025-03-31", "actual": 0.5, "estimate": 1.0, "surprise_pct": -50.0}] * 3, ret3m=0.0, mos=-0.2),
    case("no_finnhub_low_coverage", ret3m=0.1, mos=0.1),
    case("revision_too_short", sur(8), hist(("2026-10-01", "2026Q4", 1.0), ("2026-10-20", "2026Q4", 1.1)), ret3m=0.1),
    case("revision_down_other_period_last", sur(8), hist(("2026-08-01", "2026Q3", 2.0), ("2026-09-15", "2026Q3", 1.7),
         ("2026-07-01", "2026Q4", 1.0)), ret3m=0.1),
    case("revision_down", sur(8), hist(("2026-08-01", "2026Q4", 2.0), ("2026-09-15", "2026Q4", 1.7)), "lowered", 0.1, [], 0.1),
    case("zero_base_estimate", sur(6), hist(("2026-01-01", "2026Q1", 0.0), ("2026-03-01", "2026Q1", 0.2)), "maintained", 0.3, [0.1], None),
]
json.dump(cases, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
for c in cases: print(c["name"], c["score"]["score"], round(c["score"]["coverage"], 3), c["revision"], c["score"]["notes"])
