"""Module 9 — Walk-forward validation on real announcement times and prices.

Rules tested (all point-in-time: each decision uses only events BEFORE the event being traded):
  R1 "Reaction persistence": hold Strategy B (enter −7, exit +1) only if the mean day-0 reaction of the company's
     previous 4 announcements was positive.
  R2 "Post-earnings drift": after a positive day-0 reaction, hold days +1…+10.
Baseline for R1 = Strategy B on every event; baseline for R2 = days +1…+10 after every event.
Excess vs benchmark (SPY) is reported. Out-of-sample = the latest 30% of events by date (chronological split).
Known limitations are reported, never hidden: survivorship bias (current listings only), no point-in-time scores.
"""
from __future__ import annotations

import math
from statistics import mean, stdev
from typing import Any

import numpy as np
import pandas as pd

from ..analytics.pipeline import Result
from ..models import v


def _t(xs: list[float], base: float) -> float | None:
    if len(xs) < 3:
        return None
    s = stdev(xs)
    return (mean(xs) - base) / (s / math.sqrt(len(xs))) if s else None


def _summ(rs: list[dict], key: str = "r1") -> dict[str, Any]:
    allr = [x[f"{key}_base"] for x in rs]
    sig = [x[f"{key}_base"] for x in rs if x[f"{key}_sig"]]
    exc = [x[f"{key}_exc"] for x in rs if x[f"{key}_sig"] and x[f"{key}_exc"] is not None]
    if not allr:
        return {"n_all": 0, "n_sig": 0}
    base = mean(allr)
    return {"n_all": len(allr), "n_sig": len(sig), "base": base, "sig": mean(sig) if sig else None,
            "edge": (mean(sig) - base) if sig else None, "t": _t(sig, base), "excess": mean(exc) if exc else None}


def walk_forward(results: list[Result], bench: pd.DataFrame | None, cost_bps: float = 15, oos_frac: float = 0.3) -> dict[str, Any]:
    recs: list[dict] = []
    for res in results:
        t = res.t
        if not t.get("available"):
            continue
        df = res.cd.prices
        close = df["close"].to_numpy(dtype=float)
        bclose = bench["close"].reindex(df.index).ffill().to_numpy(dtype=float) if bench is not None else None
        bsma200 = bench["close"].rolling(200).mean().reindex(df.index).ffill().to_numpy(dtype=float) if bench is not None else None
        evs = t["events"]
        mcap = v(res.m["mcap"])
        cap = "Large" if mcap and mcap >= 10e9 else "Mid" if mcap and mcap >= 2e9 else "Small" if mcap else "לא ידוע"
        volb = "גבוהה" if res.vol and res.vol > 0.03 else "רגילה" if res.vol else "לא ידוע"
        for i, ev in enumerate(evs):
            i0 = ev["i0"]
            if i < 4 or i0 + 10 >= len(close):
                continue
            prior = [e["react"] for e in evs[i - 4:i]]
            cost = 2 * cost_bps / 10000
            r1 = close[i0 + 1] / close[i0 - 7] - 1 - cost
            r2 = close[i0 + 10] / close[i0 + 1] - 1 - cost
            def exc(a, b, r):
                if bclose is None or np.isnan(bclose[a]) or np.isnan(bclose[b]):
                    return None
                return r - (bclose[b] / bclose[a] - 1)
            regime = "לא ידוע"
            if bsma200 is not None and not np.isnan(bsma200[i0]):
                regime = "שוק עולה (SPY מעל ממוצע 200)" if bclose[i0] > bsma200[i0] else "שוק יורד (SPY מתחת לממוצע 200)"
            recs.append({"ticker": res.ticker, "date": ev["date"], "sector": res.cd.sector or "—", "cap": cap, "vol": volb, "regime": regime,
                         "r1_sig": mean(prior) > 0, "r1_base": r1, "r1_exc": exc(i0 - 7, i0 + 1, r1),
                         "r2_sig": ev["react"] > 0, "r2_base": r2, "r2_exc": exc(i0 + 1, i0 + 10, r2)})
    if not recs:
        return {"available": False, "why": "אין מספיק אירועים עם היסטוריית מחירים (נדרשים לפחות 5 דוחות לחברה)."}
    recs.sort(key=lambda r: r["date"])
    split = int(len(recs) * (1 - oos_frac))
    ins, oos = recs[:split], recs[split:]
    out: dict[str, Any] = {"available": True, "n": len(recs), "split_date": recs[split]["date"] if split < len(recs) else None, "rules": {}}
    for key, name in (("r1", "R1 — המשכיות תגובה (אסטרטגיה B)"), ("r2", "R2 — Post-Earnings Drift")):
        o = _summ(oos, key)
        verdict = ("יתרון חיובי מחוץ למדגם (t ≥ 2) — עדיין יש לאמת לאורך זמן ועל יקום רחב יותר."
                   if (o.get("t") or 0) >= 2 and (o.get("edge") or 0) > 0 else
                   "אין יתרון מובהק על אסטרטגיית הייחוס מחוץ למדגם — אין להציג את הכלל כמוצלח.")
        groups = {}
        for g in ("sector", "cap", "vol", "regime"):
            vals = sorted({r[g] for r in recs})
            groups[g] = [{"k": val, **_summ([r for r in recs if r[g] == val], key)} for val in vals]
        out["rules"][key] = {"name": name, "ins": _summ(ins, key), "oos": o, "verdict": verdict, "groups": groups}
    out["limitations"] = [
        "Survivorship bias: היקום כולל רק חברות הנסחרות היום (רשימת SEC עדכנית). חברות שנמחקו חסרות — התוצאות עלולות להיות מוטות כלפי מעלה.",
        "הציונים הפונדמנטליים (בריאות/תמחור) אינם משוחזרים Point-in-Time, ולכן אינם נבדקים כאן — רק כללים מבוססי מחיר ותזמון הודעות.",
        "מחירים מתואמים לפיצולים ודיבידנדים (Corporate Actions) לפי הספק.",
        f"עלויות: {cost_bps:g} bps לכל צד (עמלה + Slippage + Spread).",
    ]
    out["records"] = recs
    return out
