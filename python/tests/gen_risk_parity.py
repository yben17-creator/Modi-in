"""Parity cases for the TS port of scores.risk + fallen.fallen_angel.
Usage: python tests/gen_risk_parity.py <out.json>   (all inputs are arbitrary test values, not company data)"""
import json, sys
from dataclasses import asdict
sys.path.insert(0, '.')
import yaml
from evi.models import CompanyData, Val, Flag, InsiderTx
from evi.analytics import scores
from evi.analytics.scores import Score
from evi.analytics.fallen import fallen_angel

cfg = yaml.safe_load(open('config.yaml'))['risk']

def fl(sev, status="מאומת", known=True, structural=False, cat="Impairment", source="SEC EDGAR · 8-K"):
    return Flag("2026-10-01", cat, f"t{sev}{cat}", status, sev, "", source, None, known, structural)
def ins(kind, plan, value):
    return InsiderTx("2026-10-01", "x", "Officer", "S", kind, None, None, value, plan, "SEC EDGAR · Form 4", None)

M = ["dilution_rate", "drawdown", "rev_growth_1y", "fcf_growth", "op_margin", "op_margin_prev", "ret1y"]
def case(name, flags=(), m=None, dil=None, insiders=(), h=70.0, severe=(), vol=None, surprises=None, hist_disc=None):
    cd = CompanyData("TST", 1, "T", "Nasdaq", "Software & SaaS")
    cd.flags = list(flags); cd.dilution = dil or {}; cd.insiders = list(insiders); cd.surprises_source = surprises
    mm = {k: None for k in M}; mm.update(m or {})
    mv = {k: Val(x) for k, x in mm.items()}
    hs = Score(h)
    r = scores.risk(cd, mv, hs, list(severe), vol, cfg)
    fa = fallen_angel(cd, mv, h, {"hist_disc": hist_disc})
    return {"name": name, "flags": [asdict(f) for f in flags], "m": mm, "dil": dil or {}, "insiders": [asdict(t) for t in insiders],
            "h": h, "severe": list(severe), "vol": vol, "surprises": surprises, "hist_disc": hist_disc,
            "risk": {**r, "unusual": [asdict(t) for t in r["unusual"]]}, "fallen": fa}

Q = {"drawdown": 0.35, "rev_growth_1y": 0.2, "fcf_growth": 0.1, "op_margin": 0.2, "op_margin_prev": 0.19, "ret1y": -0.25}
cases = [
    case("clean_quality_fallen", m={**Q, "dilution_rate": -0.01}, hist_disc=0.2),
    case("critical_flag_disqualifies", flags=[fl(4, cat="Accounting Issues"), fl(2, known=False)], m={**Q, "dilution_rate": 0.06}),
    case("score_over_threshold", flags=[fl(3, known=False), fl(3), fl(2, status="דיווח תקשורתי")], m={"dilution_rate": 0.03, "drawdown": 0.1},
         dil={"has_recent_offering": True, "has_shelf": True}, insiders=[ins("sell", "open", 6e6), ins("sell", "10b5-1", 9e6)], h=20.0, vol=0.04),
    case("severe_caps", m={**Q, "dilution_rate": 0.01}, severe=["כיסוי ריבית נמוך מ-1.5"], vol=0.03, surprises="Finnhub"),
    case("new_sev3_caps", flags=[fl(3, known=False, cat="Auditor Change")], m=Q, h=55.0),
    case("structural_value_trap", flags=[fl(4, structural=True, cat="Bankruptcy")], m={**Q, "rev_growth_1y": 0.01, "op_margin_prev": 0.3}, h=40.0),
    case("no_price", m={"rev_growth_1y": 0.1}),
    case("small_drop", m={**Q, "drawdown": 0.1}),
    case("missing_growth", m={**Q, "rev_growth_1y": None}),
    case("mixed_signals", m={**Q, "rev_growth_1y": 0.04, "fcf_growth": -0.2}, h=55.0),
    case("no_health", m=Q, h=None),
    case("finnhub_news_flag", flags=[fl(1, status="ספקולטיבי", source="Finnhub · news", cat="Activist / Control")], m=Q),
]
json.dump({"cfg": cfg, "cases": cases}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
for c in cases: print(c["name"], c["risk"]["score"], c["risk"]["override"], c["fallen"]["cls"])
