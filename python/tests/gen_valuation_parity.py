"""Parity cases for the TS port of analytics/valuation.py (default_assumptions, dcf, scenarios, peer_medians, valuation).
Usage: python tests/gen_valuation_parity.py <out.json>   (all numbers are arbitrary test inputs, not company data)"""
import json, math, sys
sys.path.insert(0, '.')
import yaml
from evi.models import CompanyData, Val, Flag
from evi.analytics import valuation as V

cfg = yaml.safe_load(open('config.yaml'))['valuation']
MKEYS = ["revenue", "net_debt", "adj_fcf_margin", "fcf_margin", "rev_growth_1y", "rev_cagr_3y"] + list(V.MULTIPLES)

def enc(x):
    if isinstance(x, float) and math.isinf(x): return "inf" if x > 0 else "-inf"
    if isinstance(x, dict): return {k: enc(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [enc(v) for v in x]
    return x

base_m = {"revenue": 4.0e9, "net_debt": -1.2e9, "adj_fcf_margin": 0.14, "fcf_margin": 0.22, "rev_growth_1y": 0.18, "rev_cagr_3y": 0.21,
          "pe": 45.0, "fpe": 32.0, "ev_rev": 8.5, "ev_ebitda": 40.0, "ev_fcf": 38.0, "p_fcf": 41.0, "ps": 9.0}
peers_in = [("Software & SaaS", {"pe": 30, "fpe": 25, "ev_rev": 6, "ev_ebitda": 25, "ev_fcf": 30, "p_fcf": 32, "ps": 7}),
            ("Software & SaaS", {"pe": 50, "fpe": None, "ev_rev": 10, "ev_ebitda": 600, "ev_fcf": 45, "p_fcf": 47, "ps": 11}),
            ("Software & SaaS", {"pe": -5, "fpe": 20, "ev_rev": 4, "ev_ebitda": 18, "ev_fcf": None, "p_fcf": 20, "ps": 5}),
            ("Software & SaaS", {"pe": 22, "fpe": 18, "ev_rev": 3, "ev_ebitda": 15, "ev_fcf": 25, "p_fcf": 26, "ps": 3.5}),
            ("Semiconductors", {"pe": 20, "fpe": 18, "ev_rev": 5, "ev_ebitda": 12, "ev_fcf": 22, "p_fcf": 23, "ps": 5}),
            (None, {"pe": 10, "fpe": 10, "ev_rev": 1, "ev_ebitda": 5, "ev_fcf": 8, "p_fcf": 8, "ps": 1})]
peers_out = V.peer_medians([(s, {k: Val(v) for k, v in m.items()}) for s, m in peers_in], int(cfg["min_peers"]))

def case(name, over=None, price=120.0, shares=2.5e8, sector="Software & SaaS", flags=(), hist=None, daily_vol=None, peers=True):
    m = {**base_m, **(over or {})}
    cd = CompanyData("TST", 1, "T", "Nasdaq", sector)
    cd.price = Val(price) if price is not None else Val(None)
    if shares is not None: cd.fin["diluted_shares"] = Val(shares)
    cd.flags = [Flag("2026-01-01", "x", "t", "מאומת", sev, "", "", structural=st) for sev, st in flags]
    mv = {k: Val(m.get(k)) for k in MKEYS}
    orig = V.historical_multiples
    if hist is not None: V.historical_multiples = lambda cd, years=5: hist
    a = V.default_assumptions(cd, mv, daily_vol, cfg)
    out = V.valuation(cd, mv, a, peers_out if peers else None, cfg)
    V.historical_multiples = orig
    return {"name": name, "m": m, "price": price, "shares": shares, "sector": sector, "severe_structural": any(st and sev >= 3 for sev, st in flags),
            "hist_in": hist, "daily_vol": daily_vol, "use_peers": peers, "assumptions": a.to_dict() if a else None, "out": enc(out)}

H = {"ps": 12.0, "ev_rev": 11.0, "ev_fcf": 50.0, "points": [], "note": ""}
cases = [
    case("base_growth"),
    case("with_history_and_vol", hist=H, daily_vol=0.025),
    case("high_vol_wacc_cap", daily_vol=0.08),
    case("negative_adj_margin", {"adj_fcf_margin": -0.05}),
    case("negative_growth_damped", {"rev_cagr_3y": -0.04, "rev_growth_1y": 0.01}, hist=H),
    case("growth_from_1y_only", {"rev_cagr_3y": None, "rev_growth_1y": 0.5}),
    case("no_growth_data", {"rev_cagr_3y": None, "rev_growth_1y": None}),
    case("no_price", price=None),
    case("missing_shares", shares=None),
    case("structural_flag_damps", flags=[(3, True)], hist=H),
    case("other_sector_no_peers", sector="Cybersecurity"),
    case("no_peers_no_hist_no_price", price=None, peers=False),
    case("terminal_heavy", {"rev_cagr_3y": 0.45, "adj_fcf_margin": 0.02}, hist=H),
    case("net_debt_positive_large", {"net_debt": 9e10}),
]
json.dump({"peers_in": peers_in, "peers_out": enc(peers_out), "cfg": cfg, "cases": cases}, open(sys.argv[1], "w"), ensure_ascii=False)
for c in cases: print(c["name"], c["out"].get("mid"), c["out"].get("score"))
