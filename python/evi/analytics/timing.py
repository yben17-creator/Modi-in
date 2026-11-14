"""Module 7 — Entry & exit windows around earnings, using REAL announcement times (SEC 8-K Item 2.02 acceptance
time) and real daily prices. Day 0 = first trading session that can react to the results:
  accepted ≥ 16:00 ET (after close) or on a non-trading day → next session; accepted before 16:00 → same session.
Returns are net of round-trip costs and also shown in excess of the benchmark (SPY by default) for the same window."""
from __future__ import annotations

import math
from datetime import datetime
from statistics import mean, median, stdev
from typing import Any

import numpy as np
import pandas as pd

from ..models import CompanyData

PRE = [30, 21, 14, 7]


def day0_index(idx: pd.DatetimeIndex, accepted: str) -> int | None:
    """Map an EDGAR acceptance timestamp to the position of the reaction session in `idx`."""
    # EDGAR's acceptanceDateTime carries a trailing "Z" but the clock time is US Eastern (a known EDGAR quirk),
    # so the suffix is dropped and the time is read as Eastern.
    try:
        ts = pd.Timestamp(accepted.replace("Z", "")[:19])
    except Exception:
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    d = ts.normalize()
    pos = idx.searchsorted(d)
    if pos >= len(idx):
        return None
    same_day = idx[pos] == d
    has_time = len(accepted) > 10
    if same_day and has_time and (ts.hour, ts.minute) >= (16, 0):
        pos += 1
    return pos if pos < len(idx) else None


def _trade(close: np.ndarray, i_in: int, i_out: int, cost_bps: float) -> tuple[float, float]:
    seg = close[i_in:i_out + 1]
    peak, dd = seg[0], 0.0
    for p in seg:
        peak = max(peak, p)
        dd = min(dd, p / peak - 1)
    return float(seg[-1] / seg[0] - 1 - 2 * cost_bps / 10000), dd


def _stats(rets: list[float], dds: list[float], excess: list[float], hold: int, min_n: int) -> dict[str, Any]:
    n = len(rets)
    if n == 0:
        return {"n": 0, "hold": hold}
    s: dict[str, Any] = {"n": n, "hold": hold, "avg": mean(rets), "med": median(rets), "win": sum(r > 0 for r in rets) / n,
                         "max_dd": min(dds), "vol": stdev(rets) if n > 1 else None,
                         "p10": float(np.percentile(rets, 10)), "excess": mean(excess) if excess else None}
    s["risk_adj"] = s["avg"] / s["vol"] if s["vol"] else None
    s["t"] = s["avg"] / (s["vol"] / math.sqrt(n)) if s["vol"] else None
    if n < min_n:
        s["conf"] = "אין מספיק נתונים"
    else:
        t = abs(s["t"] or 0)
        s["conf"] = "בינונית" if t >= 2.5 else "נמוכה–בינונית" if t >= 1.5 else "נמוכה"
    return s


def analyze(cd: CompanyData, bench: pd.DataFrame | None, cost_bps: float = 15, min_events: int = 8, max_years: int = 10) -> dict[str, Any]:
    df = cd.prices
    if df is None or df.empty:
        return {"available": False, "why": "אין היסטוריית מחירים — הגדר ספק מחירים (Massive או yfinance)"}
    if not cd.earnings_events:
        return {"available": False, "why": "לא נמצאו הודעות תוצאות (8-K Item 2.02) ב-EDGAR"}
    idx, close = df.index, df["close"].to_numpy(dtype=float)
    b_close = bench["close"].reindex(idx).ffill().to_numpy(dtype=float) if bench is not None else None
    cutoff = idx[-1] - pd.Timedelta(days=365 * max_years)
    events = []
    for e in cd.earnings_events:
        i0 = day0_index(idx, e["accepted"])
        if i0 is None or idx[i0] < cutoff or i0 - 31 < 0 or i0 + 20 >= len(idx):
            continue
        react = close[i0] / close[i0 - 1] - 1
        events.append({"i0": i0, "date": idx[i0].date().isoformat(), "accepted": e["accepted"], "react": react, "url": e["url"]})
    if not events:
        return {"available": False, "why": "אין אירועי דוח עם 30 ימי מסחר לפני ו-20 אחרי בטווח המחירים הזמין"}

    def run(entry: int, exit_: int, cond=None) -> dict[str, Any]:
        rets, dds, exc = [], [], []
        for ev in events:
            if cond and not cond(ev):
                continue
            a, b = ev["i0"] + entry, ev["i0"] + exit_
            r, dd = _trade(close, a, b, cost_bps)
            rets.append(r)
            dds.append(dd)
            if b_close is not None and not np.isnan(b_close[a]) and not np.isnan(b_close[b]):
                exc.append(r - (b_close[b] / b_close[a] - 1))
        return _stats(rets, dds, exc, exit_ - entry, min_events)

    A = [{"label": f"כניסה {k} ימי מסחר לפני → יציאה יום לפני הדוח", **run(-k, -1)} for k in PRE]
    B = []
    for k in (14, 7):
        for x in (0, 1, 3):
            B.append({"label": f"כניסה {k} ימים לפני → יציאה {'ביום התגובה' if x == 0 else f'{x} ימים אחרי'}", **run(-k, x)})
    C = [{"label": f"כניסה יום 1 אחרי תגובה חיובית → יציאה {x} ימים אחרי", **run(1, x, lambda e: e["react"] > 0)} for x in (5, 10, 20)]
    days = list(range(-30, 21))
    paths = np.array([[close[ev["i0"] + d] / close[ev["i0"] - 30] - 1 for d in days] for ev in events]) * 100
    return {"available": True, "A": A, "B": B, "C": C, "days": days, "avg_path": paths.mean(axis=0).tolist(),
            "sd_path": paths.std(axis=0, ddof=1).tolist() if len(events) > 1 else [0.0] * len(days),
            "reactions": [ev["react"] for ev in events], "events": events, "n": len(events), "cost_bps": cost_bps,
            "benchmark": bench is not None, "price_source": cd.prices_source}


def best_window(t: dict[str, Any], min_n: int = 3) -> dict | None:
    if not t.get("available"):
        return None
    rows = [r for r in t["A"] + t["B"] + t["C"] if r.get("n", 0) >= min_n and r.get("risk_adj") is not None]
    return max(rows, key=lambda r: r["risk_adj"]) if rows else None
