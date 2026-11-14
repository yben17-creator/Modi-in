"""Module 3 — Fair value & undervaluation: revenue-driven DCF (3 scenarios + sensitivity), relative and historical multiples."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from statistics import mean, median
from typing import Any

import pandas as pd

from ..models import CompanyData, v

MULTIPLES = {"pe": "P/E", "fpe": "Forward P/E", "ev_rev": "EV/Revenue", "ev_ebitda": "EV/EBITDA", "ev_fcf": "EV/FCF", "p_fcf": "Price/FCF", "ps": "Price/Sales"}


@dataclass
class Assumptions:
    g1: float
    gT: float
    wacc: float
    m_target: float
    use_adj: bool = True
    years: int = 10

    def to_dict(self) -> dict:
        return asdict(self)


def default_assumptions(cd: CompanyData, m: dict, daily_vol: float | None, cfg: dict) -> Assumptions | None:
    cagr = v(m["rev_cagr_3y"])
    if cagr is None:
        cagr = v(m["rev_growth_1y"])
    if cagr is None:
        return None
    g1 = min(max(cagr * 0.85, -0.03), 0.35)
    base = float(cfg.get("base_wacc", 0.085))
    if daily_vol is not None:
        wacc = min(max(base + (daily_vol * 100 - 2) * 0.0075, 0.08), 0.125)
    else:
        wacc = float(cfg.get("default_wacc_no_prices", 0.095))
    m0 = v(m["adj_fcf_margin"])
    target = min(max(m0 + 0.03, 0.08), 0.40) if m0 is not None and m0 > 0 else float(cfg.get("target_margin_if_negative", 0.12))
    return Assumptions(g1, float(cfg.get("terminal_growth", 0.025)), wacc, target, True, int(cfg.get("years", 10)))


def dcf(revenue: float, m0: float, net_debt: float, shares: float, a: Assumptions) -> dict[str, Any]:
    if a.wacc <= a.gT:
        return {"per_share": None, "invalid": "WACC ≤ צמיחה טרמינלית"}
    rev, pv, rows, fcf = revenue, 0.0, [], 0.0
    for t in range(1, a.years + 1):
        g = a.g1 + (a.gT - a.g1) * (t - 1) / (a.years - 1)
        rev *= 1 + g
        mt = m0 + (a.m_target - m0) * t / 5 if t <= 5 else a.m_target
        fcf = rev * mt
        df = (1 + a.wacc) ** t
        pv += fcf / df
        rows.append({"year": t, "growth": g, "revenue": rev, "margin": mt, "fcf": fcf, "pv": fcf / df})
    tv = fcf * (1 + a.gT) / (a.wacc - a.gT)
    pv_tv = tv / (1 + a.wacc) ** a.years
    ev = pv + pv_tv
    eq = ev - net_debt
    return {"ev": ev, "equity": eq, "per_share": eq / shares, "pv_tv": pv_tv, "tv_share": pv_tv / ev if ev else None, "rows": rows}


def scenarios(a: Assumptions) -> dict[str, Assumptions]:
    return {"cons": Assumptions(a.g1 * 0.6 if a.g1 > 0 else a.g1 - 0.02, a.gT, a.wacc + 0.01, a.m_target - 0.03, a.use_adj, a.years),
            "base": a,
            "opt": Assumptions(a.g1 * 1.25 if a.g1 > 0 else a.g1 + 0.02, a.gT, a.wacc - 0.0075, a.m_target + 0.03, a.use_adj, a.years)}


def peer_medians(all_metrics: list[tuple[str, dict]], min_peers: int = 3) -> dict[str, dict[str, Any]]:
    """sector → {multiple: (median, n)} from the companies analyzed in this scan (real data only)."""
    out: dict[str, dict[str, Any]] = {}
    by_sector: dict[str, list[dict]] = {}
    for sector, m in all_metrics:
        if sector:
            by_sector.setdefault(sector, []).append(m)
    for sector, ms in by_sector.items():
        out[sector] = {}
        for k in MULTIPLES:
            vals = [v(m[k]) for m in ms if v(m[k]) is not None and 0 < v(m[k]) < 500]
            out[sector][k] = (median(vals), len(vals)) if len(vals) >= min_peers else (None, len(vals))
    return out


def historical_multiples(cd: CompanyData, years: int = 5) -> dict[str, Any]:
    """Own average P/S, EV/Revenue and EV/FCF at fiscal year-ends (requires price history covering those dates)."""
    df = cd.prices
    if df is None or df.empty:
        return {"note": "דורש היסטוריית מחירים", "ps": None, "ev_rev": None, "ev_fcf": None, "points": []}
    rev = {r["end"]: r["val"] for r in cd.annual.get("revenue", [])}
    ocf = {r["end"]: r["val"] for r in cd.annual.get("ocf", [])}
    capex = {r["end"]: r["val"] for r in cd.annual.get("capex", [])}
    shares = cd.annual.get("diluted_shares", [])
    def inst(key: str, end: str) -> float | None:
        s = [x for x in cd.annual.get(key + "_instant", []) if x["end"] == end]
        return s[0]["val"] if s else None
    pts = []
    for end in sorted(rev)[-years - 1:-1] if len(rev) > 1 else []:  # exclude latest year (current multiples cover it)
        ts = pd.Timestamp(end)
        px = df[df.index <= ts]["close"]
        sh = [x for x in shares if x["end"] == end]
        if px.empty or (ts - px.index[-1]).days > 7 or not sh:
            continue
        mcap = float(px.iloc[-1]) * sh[0]["val"]
        cash = (inst("cash", end) or 0) + (inst("st_investments", end) or 0)
        debt = (inst("st_debt", end) or 0) + (inst("lt_debt_noncurrent", end) or inst("lt_debt_total", end) or 0)
        ev = mcap + debt - cash
        p = {"end": end, "ps": mcap / rev[end] if rev[end] > 0 else None, "ev_rev": ev / rev[end] if rev[end] > 0 else None}
        f = (ocf.get(end) or 0) - (capex.get(end) or 0) if end in ocf and end in capex else None
        p["ev_fcf"] = ev / f if f and f > 0 else None
        pts.append(p)
    res: dict[str, Any] = {"points": pts, "note": "" if pts else "אין חפיפה בין היסטוריית המחירים לסופי השנים הפיסקליות"}
    for k in ("ps", "ev_rev", "ev_fcf"):
        xs = [p[k] for p in pts if p.get(k)]
        res[k] = mean(xs) if len(xs) >= 2 else None
    return res


def valuation(cd: CompanyData, m: dict, a: Assumptions | None, peers: dict | None, cfg: dict) -> dict[str, Any]:
    out: dict[str, Any] = {"assumptions": a.to_dict() if a else None, "mos": None, "score": None, "parts": {}}
    price = v(cd.price)
    rev, nd, sh = v(m["revenue"]), v(m["net_debt"]), v(cd.f("diluted_shares"))
    m0 = v(m["adj_fcf_margin"]) if (a and a.use_adj) else v(m["fcf_margin"])
    missing_in = [n for n, x in (("הכנסות", rev), ("חוב נטו", nd), ("מניות בדילול מלא", sh), ("מרווח FCF", m0), ("הנחות צמיחה", a)) if x is None]
    if missing_in:
        out["dcf_missing"] = "DCF לא חושב — חסר: " + ", ".join(missing_in)
    else:
        sc = scenarios(a)
        res = {k: dcf(rev, m0, nd, sh, s) for k, s in sc.items()}
        out.update({"cons": res["cons"], "base": res["base"], "opt": res["opt"], "scenarios": {k: s.to_dict() for k, s in sc.items()}})
        out["low"], out["mid"], out["high"] = res["cons"]["per_share"], res["base"]["per_share"], res["opt"]["per_share"]
        if price and out["mid"] and out["mid"] > 0:
            out["mos"] = (out["mid"] - price) / out["mid"]
            out["upside"] = out["mid"] / price - 1
            out["downside_cons"] = out["low"] / price - 1 if out["low"] is not None else None
        tvs = res["base"].get("tv_share")
        out["reliable"] = m0 > 0 and tvs is not None and tvs < 0.8 and (out["mid"] or 0) > 0
        out["reliability_note"] = ("תזרים מתואם שלילי — הערכת ה-DCF נשענת על הנחת מרווח יעד ולכן אמינותה נמוכה." if m0 <= 0 else
                                   "מעל 80% מהשווי נובע מהערך הטרמינלי — רגישות גבוהה מאוד להנחות." if tvs and tvs >= 0.8 else
                                   "השווי רגיש להנחות; ראה טבלת רגישות.")
        waccs = [a.wacc + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
        gts = [0.015, 0.02, 0.025, 0.03, 0.035]
        out["grid"] = {"waccs": waccs, "gts": gts,
                       "cells": [[dcf(rev, m0, nd, sh, Assumptions(a.g1, g, w, a.m_target, a.use_adj, a.years)).get("per_share") for g in gts] for w in waccs]}
    # relative
    pm = (peers or {}).get(cd.sector or "", {})
    rel = []
    for k, label in MULTIPLES.items():
        own = v(m[k])
        med, n = pm.get(k, (None, 0))
        rel.append({"k": k, "label": label, "own": own, "peer": med, "n_peers": n,
                    "disc": (1 - own / med) if own and med and own > 0 else None})
    out["rel"] = rel
    hist = historical_multiples(cd)
    out["hist"] = hist
    hrel = []
    for k in ("ps", "ev_rev", "ev_fcf"):
        own = v(m[k])
        hv = hist.get(k)
        hrel.append({"k": k, "label": MULTIPLES[k], "own": own, "hist": hv, "disc": (1 - own / hv) if own and hv and own > 0 else None})
    out["hist_rel"] = hrel
    rd = [r["disc"] for r in rel if r["k"] in ("ev_rev", "ev_ebitda", "ev_fcf") and r["disc"] is not None]
    hd = [r["disc"] for r in hrel if r["disc"] is not None]
    out["rel_disc"] = mean(rd) if rd else None
    out["hist_disc"] = mean(hd) if hd else None
    # score — a low multiple alone is not proof of undervaluation
    g1 = v(m["rev_growth_1y"])
    damp = 0.5 if ((g1 is not None and g1 < 0.03) or any(f.structural and f.severity >= 3 for f in cd.flags)) else 1.0
    parts = {"mos": (0.5, None if out["mos"] is None else min(max(50 + out["mos"] * 150, 0), 100)),
             "rel": (0.25, None if out["rel_disc"] is None else min(max(50 + out["rel_disc"] * 100 * damp, 0), 100)),
             "hist": (0.25, None if out["hist_disc"] is None else min(max(50 + out["hist_disc"] * 100 * damp, 0), 100))}
    out["parts"] = {k: {"weight": w, "score": s} for k, (w, s) in parts.items()}
    out["damp"] = damp
    avail = [(w, s) for w, s in parts.values() if s is not None]
    if parts["mos"][1] is not None or len(avail) >= 2:  # need DCF, or both relative measures
        out["score"] = round(sum(w * s for w, s in avail) / sum(w for w, _ in avail), 1)
    else:
        out["score_missing"] = "ציון תמחור לא חושב: אין DCF ואין מספיק מכפילי השוואה"
    return out
