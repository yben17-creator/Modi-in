"""Parity cases for the TS port of reports/hebrew.py (text generation) and scores.final (classification).
Usage: python tests/gen_report_parity.py <out.json>
Inputs come from the offline test fixtures (tests/fixtures_builder: synthetic company "TSTC") plus variants — not real data."""
import copy, json, math, os, sys, tempfile
from datetime import date
from pathlib import Path
sys.path.insert(0, '.')
os.environ["SEC_USER_AGENT"] = "Test test@example.com"
os.environ.pop("FINNHUB_API_KEY", None); os.environ.pop("MASSIVE_API_KEY", None)
from tests import fixtures_builder as fx
from evi.config import load_settings
from evi.store import Store
from evi.providers.router import DataHub
from evi.analytics.pipeline import analyze_all
from evi.analytics import scores
from evi.analytics.timing import best_window
from evi.models import Val, Flag, InsiderTx
from evi.reports.hebrew import sections

settings = load_settings(reload=True)
store = Store(Path(tempfile.mkdtemp()) / "t.sqlite"); fx.seed_cache(store)
def run(with_prices):
    hub = DataHub(settings, store, today=date(2026, 11, 14)); hub.finnhub = None
    hub.price_sources = [fx.FakePrices({"TSTC": fx.prices(1), "SPY": fx.prices(2)})] if with_prices else []
    cd = hub.load("TSTC")
    return analyze_all([cd], settings, hub.benchmark() if with_prices else None)[0]

def enc(x):
    if isinstance(x, Val): x = x.value if x.ok else None
    if isinstance(x, float):
        if math.isinf(x): return "inf" if x > 0 else "-inf"
        if math.isnan(x): return None
    return x

M_KEYS = ["net_debt", "nd_ebitda", "coverage", "current_ratio", "total_debt", "cash_all", "fcf", "revenue", "rev_growth_1y", "rev_cagr_3y",
          "op_margin", "op_margin_prev", "fcf_margin", "adj_fcf", "mcap", "ev", "ev_rev", "ev_fcf", "pe", "ret3m", "sbc_pct", "dilution_rate"]
def report_input(r):
    cd = r.cd
    b = best_window(r.t) if r.t.get("available") else None
    return {
        "name": cd.name, "ticker": cd.ticker, "exchange": cd.exchange, "sector": cd.sector, "sectorSource": cd.sources_used.get("סיווג סקטור", ""),
        "sicDesc": cd.sic_desc, "manual": {k: cd.manual.get(k) for k in ("moat", "guidance") if cd.manual.get(k)},
        "raw": {k: enc(cd.f(k)) for k in ("operating_income", "net_income", "sbc", "convertible_debt", "buyback_remaining")},
        "hasMaturities": bool(cd.maturities), "price": enc(cd.price), "next": {k: cd.next_earnings.get(k) for k in ("date", "hour", "status", "eps_est", "rev_est")},
        "surprises": cd.surprises, "flags": [{"title": f.title, "status": f.status, "severity": f.severity, "known": f.known, "date": f.date, "impact": f.impact} for f in cd.flags],
        "dilution": {k: cd.dilution.get(k) for k in ("has_recent_offering", "has_shelf")},
        "m": {k: enc(r.m[k]) for k in M_KEYS},
        "h": {"score": r.h.score, "coverage": r.h.coverage, "notes": r.h.notes}, "severe": r.severe, "nearMaturities": r.near_maturities,
        "val": {k: enc(r.val.get(k)) for k in ("mid", "low", "high", "mos", "reliability_note", "dcf_missing", "rel_disc", "hist_disc", "damp", "upside")},
        "fa": {"cls": r.fa.get("cls"), "why": r.fa.get("why", [])},
        "risk": {"score": r.r["score"], "checked": r.r["checked"], "override": r.r["override"], "unusual": [{"who": t.who, "value": t.value} for t in r.r["unusual"]]},
        "timing": {"available": bool(r.t.get("available")), "why": r.t.get("why"), "n": r.t.get("n"), "priceSource": r.t.get("price_source"),
                   "best": None if not b else {k: b[k] for k in ("label", "avg", "win", "conf")}},
        "monAlerts": [a["he"] for a in r.mon.get("alerts", [])] if r.mon.get("available") else [],
        "fin": r.fin, "revChange": r.rev_change,
    }

base_p, base_np = run(True), run(False)
variants = []
def add(name, r):
    variants.append({"name": name, "input": report_input(r), "sections": [list(s) for s in sections(r)]})
add("with_prices", base_p)
add("without_prices", base_np)
r = copy.deepcopy(base_p); r.cd.manual = {"moat": "הערה", "guidance": "raised"}; r.rev_change = 0.05
r.cd.surprises = [{"period": "2026-06-30", "actual": 1.2, "estimate": 1.0, "surprise_pct": 20.0}] * 9; r.cd.next_earnings = {**r.cd.next_earnings, "hour": "AMC", "eps_est": 1.1, "rev_est": 2.5e9}
add("manual_and_surprises", r)
r = copy.deepcopy(base_p); r.rev_change = -0.04; r.cd.manual = {"guidance": "lowered"}; r.severe = ["כיסוי ריבית נמוך מ-1.5"]; r.near_maturities = 5e12
r.fin = {**r.fin, "idx": 1, "capped": True, "reason": "Risk Override: test", "composite": 61.26, "missing_parts": ["e"]}
r.cd.insiders = []; r.r = {**r.r, "unusual": [InsiderTx("2026-10-01", "Doe J", "CEO", "S", "sell", 1e5, 80.0, 8e6, "open", "x")]}
add("capped_severe_revdown", r)
r = copy.deepcopy(base_np); r.cd.flags = []; r.cd.next_earnings = {}; r.fin = {**r.fin, "idx": 2, "composite": 48.0, "capped": False, "reason": "", "missing_parts": []}
r.val = {**r.val, "rel_disc": -0.12, "hist_disc": 0.3, "damp": 0.5}; r.fa = {"cls": "Value Trap Risk", "why": ["a", "b"]}
add("mixed_no_flags", r)
r = copy.deepcopy(base_p); r.fin = {**r.fin, "idx": 0, "composite": 70.5, "capped": False, "reason": "", "missing_parts": []}; r.rev_change = 0.0
add("high_priority", r)

# scores.final cases
cfg_cls = settings.get("classification") if hasattr(settings, "get") else {}
from evi.analytics.scores import Score
fcases = []
def fin_case(name, h, vs, mos, e, rs, override, fallen_cls):
    out = scores.final(Score(h), {"score": vs, "mos": mos}, Score(e), {"score": rs, "override": override}, {"cls": fallen_cls}, cfg_cls)
    fcases.append({"name": name, "h": h, "v": vs, "mos": mos, "e": e, "risk": rs, "override": override, "fallen": fallen_cls, "out": out})
fin_case("disqualified", 80, 70, 0.3, 60, 75, {"level": "disqualify", "reason": "R"}, None)
fin_case("missing_valuation", 80, None, None, 60, 10, None, None)
fin_case("low_health", 40, 70, 0.3, 60, 10, None, None)
fin_case("high_priority", 80, 75, 0.3, 70, 20, None, "Undervalued Quality")
fin_case("high_capped_by_override", 80, 75, 0.3, 70, 20, {"level": "cap", "reason": "C"}, None)
fin_case("high_capped_value_trap", 80, 75, 0.3, 70, 20, None, "Value Trap Risk")
fin_case("watch", 60, 55, 0.05, None, 30, None, None)
fin_case("uncertain", 50, 30, 0.0, 40, 60, None, None)
fin_case("high_comp_low_mos", 85, 80, 0.1, 80, 10, None, None)
json.dump({"cfg": cfg_cls, "reports": variants, "final": fcases}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
for v_ in variants: print(v_["name"], v_["input"]["fin"]["idx"], len(v_["sections"]))
for c in fcases: print(c["name"], c["out"])
