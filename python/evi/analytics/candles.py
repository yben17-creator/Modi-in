"""Module 10 — Candlestick & volume layer (post-buy management).

Outputs for one company (all computed only from daily OHLCV; every value carries its method in Hebrew):
  * patterns   — recent candlestick patterns (engulfing, hammer, shooting star, doji), with volume confirmation
  * floor      — current support floor: highest confirmed swing-low cluster below price; ATR stop as fallback
  * target     — sell target: nearest confirmed swing-high cluster above price, optionally capped by fair value
  * flow       — quiet accumulation / distribution from volume (CMF-20, OBV slope vs price slope, up/down volume)
  * trend      — long-term direction from SMA50/SMA200
  * short      — short interest: MISSING until a source is connected (never estimated)
And a point-in-time study (`signal_study`) that checks on past data whether these signals had an edge:
  forward returns after each signal vs. the unconditional baseline, and how often the floor actually held.
Signals are indications, not predictions. The user makes the buy/sell decisions.
"""
from __future__ import annotations

import math
from statistics import mean, stdev
from typing import Any

import numpy as np
import pandas as pd

from .momentum import atr

PIVOT_K = 3          # a swing low/high needs K lower/higher bars on each side → confirmed K bars later
CLUSTER_PCT = 0.02   # pivots within 2% are one level
LOOKBACK = 250       # bars used for support/resistance
MIN_BARS = 60


# ------------------------------------------------------------------ candlestick patterns
def pattern_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Boolean columns per bar. Causal: bar i uses bars ≤ i only."""
    o, h, l, c, vol = (df[k].astype(float) for k in ("open", "high", "low", "close", "volume"))
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    upper = h - pd.concat([o, c], axis=1).max(axis=1)
    lower = pd.concat([o, c], axis=1).min(axis=1) - l
    po, pc = o.shift(), c.shift()
    sma20 = c.rolling(20).mean()
    down_ctx = c < sma20          # pattern context: hammer only matters after weakness, shooting star after strength
    up_ctx = c > sma20
    vol_avg = vol.rolling(20).mean().shift()
    out = pd.DataFrame(index=df.index)
    out["bull_engulf"] = (pc < po) & (c > o) & (o <= pc) & (c >= po) & (body > (pc - po).abs())
    out["bear_engulf"] = (pc > po) & (c < o) & (o >= pc) & (c <= po) & (body > (pc - po).abs())
    out["hammer"] = down_ctx & (lower >= 2 * body) & (upper <= 0.3 * rng) & (body > 0)
    out["shooting_star"] = up_ctx & (upper >= 2 * body) & (lower <= 0.3 * rng) & (body > 0)
    out["doji"] = body <= 0.1 * rng
    out["vol_confirm"] = vol > 1.5 * vol_avg
    return out.fillna(False)


PATTERN_HE = {
    "bull_engulf": ("Bullish Engulfing", "בליעה עולה", +1),
    "bear_engulf": ("Bearish Engulfing", "בליעה יורדת", -1),
    "hammer": ("Hammer", "פטיש (אחרי ירידה)", +1),
    "shooting_star": ("Shooting Star", "כוכב נופל (אחרי עלייה)", -1),
    "doji": ("Doji", "דוג'י — היסוס", 0),
}


def recent_patterns(df: pd.DataFrame, days: int = 10) -> list[dict[str, Any]]:
    pf = pattern_frame(df).tail(days)
    out = []
    for d, row in pf.iterrows():
        for k, (en, he, sign) in PATTERN_HE.items():
            if row[k]:
                out.append({"date": d.date().isoformat(), "k": en, "he": he, "dir": sign, "vol_confirm": bool(row["vol_confirm"])})
    return out


# ------------------------------------------------------------------ support / resistance
def pivots(df: pd.DataFrame, k: int = PIVOT_K) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Swing lows / highs as (index, level). Pivot at i is known only at bar i+k."""
    lo, hi = df["low"].to_numpy(float), df["high"].to_numpy(float)
    lows, highs = [], []
    for i in range(k, len(df) - k):
        w_lo, w_hi = lo[i - k:i + k + 1], hi[i - k:i + k + 1]
        if lo[i] == w_lo.min() and (w_lo > lo[i]).sum() >= 2 * k - 1:
            lows.append((i, lo[i]))
        if hi[i] == w_hi.max() and (w_hi < hi[i]).sum() >= 2 * k - 1:
            highs.append((i, hi[i]))
    return lows, highs


def _clusters(levels: list[float]) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for x in sorted(levels):
        if out and x <= out[-1]["top"] * (1 + CLUSTER_PCT):
            c = out[-1]
            c["n"] += 1
            c["top"] = x
            c["level"] = (c["level"] * (c["n"] - 1) + x) / c["n"]
        else:
            out.append({"level": x, "top": x, "n": 1})
    return out


def levels_at(df: pd.DataFrame, i: int, piv: tuple[list, list] | None = None) -> dict[str, Any]:
    """Floor and resistance as known at the close of bar i (point-in-time)."""
    lows, highs = piv or pivots(df)
    start = max(0, i - LOOKBACK)
    known_lo = [lv for j, lv in lows if start <= j <= i - PIVOT_K]
    known_hi = [lv for j, lv in highs if start <= j <= i - PIVOT_K]
    close = float(df["close"].iloc[i])
    a = float(atr(df.iloc[:i + 1]).iloc[-1])
    below = [c for c in _clusters(known_lo) if c["level"] < close]
    above = [c for c in _clusters(known_hi) if c["level"] > close]
    sup = max(below, key=lambda c: c["level"]) if below else None
    res = min(above, key=lambda c: c["level"]) if above else None
    atr_stop = close - 2.5 * a
    if sup and sup["level"] >= atr_stop - 2 * a:
        floor, how = sup["level"], f"שפל נדנדה מאושר ({sup['n']} נגיעות)"
    else:
        floor, how = atr_stop, "אין שפל קרוב — 2.5×ATR מתחת לסגירה"
    return {"close": close, "atr": a, "floor": floor, "floor_how": how, "support": sup["level"] if sup else None,
            "support_touches": sup["n"] if sup else 0, "resistance": res["level"] if res else None,
            "resistance_touches": res["n"] if res else 0}


# ------------------------------------------------------------------ volume flow
def flow_frame(df: pd.DataFrame) -> pd.DataFrame:
    h, l, c, vol = (df[k].astype(float) for k in ("high", "low", "close", "volume"))
    rng = (h - l).replace(0, np.nan)
    mfv = ((c - l) - (h - c)) / rng * vol
    out = pd.DataFrame(index=df.index)
    out["cmf20"] = mfv.rolling(20).sum() / vol.rolling(20).sum()
    obv = (np.sign(c.diff()).fillna(0) * vol).cumsum()
    out["obv_slope"] = (obv - obv.shift(20)) / vol.rolling(20).sum()      # net signed volume share over 20 days
    out["ret20"] = c / c.shift(20) - 1
    up = vol.where(c.diff() > 0, 0).rolling(20).sum()
    dn = vol.where(c.diff() < 0, 0).rolling(20).sum()
    out["updown"] = up / dn.replace(0, np.nan)
    flat = out["ret20"].abs() <= 0.04
    out["quiet_dist"] = (flat | (out["ret20"] > 0)) & (out["cmf20"] < -0.10) & (out["obv_slope"] < -0.10)
    out["quiet_accum"] = (flat | (out["ret20"] < 0)) & (out["cmf20"] > 0.10) & (out["obv_slope"] > 0.10)
    out[["quiet_dist", "quiet_accum"]] = out[["quiet_dist", "quiet_accum"]].fillna(False)
    return out


def flow_state(df: pd.DataFrame) -> dict[str, Any]:
    f = flow_frame(df).iloc[-1]
    if bool(f["quiet_dist"]):
        state, he = "distribution", "פיזור שקט — המחיר מחזיק אבל הנפח נוטה למכירה"
    elif bool(f["quiet_accum"]):
        state, he = "accumulation", "צבירה שקטה — המחיר לא עולה אבל הנפח נוטה לקנייה"
    else:
        state, he = "neutral", "אין סימן ברור לצבירה או פיזור"
    return {"state": state, "he": he, "cmf20": _f(f["cmf20"]), "obv_slope": _f(f["obv_slope"]), "ret20": _f(f["ret20"]),
            "updown": _f(f["updown"]), "method": "CMF-20, שיפוע OBV ל-20 יום ויחס נפח ימים עולים/יורדים"}


def _f(x) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


# ------------------------------------------------------------------ main entry
def analyze(prices: pd.DataFrame | None, fair_value: float | None = None) -> dict[str, Any]:
    if prices is None or len(prices) < MIN_BARS:
        return {"available": False, "why": f"דורש לפחות {MIN_BARS} ימי מסחר של היסטוריית מחירים"}
    df = prices
    lv = levels_at(df, len(df) - 1)
    close = lv["close"]
    target, t_how = lv["resistance"], "התנגדות קרובה (שיא נדנדה מאושר)"
    if fair_value and fair_value > close and (target is None or fair_value < target):
        target, t_how = fair_value, "שווי הוגן (בסיס) — נמוך מההתנגדות"
    if target is None:
        t_how = "אין התנגדות מעל המחיר ואין שווי הוגן מעליו — יעד חסר"
    rr = (target - close) / (close - lv["floor"]) if target and close > lv["floor"] else None
    c = df["close"].astype(float)
    s50, s200 = c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1] if len(c) >= 200 else float("nan")
    if math.isnan(s200):
        trend = "לא ידוע (פחות מ-200 ימים)"
    else:
        trend = "עולה (50 מעל 200, מחיר מעל 200)" if s50 > s200 and close > s200 else \
                "יורד (50 מתחת ל-200, מחיר מתחת ל-200)" if s50 < s200 and close < s200 else "מעורב"
    return {"available": True, "as_of": df.index[-1].date().isoformat(), "close": close,
            "floor": lv["floor"], "floor_how": lv["floor_how"], "floor_pct": lv["floor"] / close - 1,
            "target": target, "target_how": t_how, "target_pct": (target / close - 1) if target else None, "rr": rr,
            "patterns": recent_patterns(df), "flow": flow_state(df), "trend": trend,
            "short": {"value": None, "note": "חסר — לא מחובר מקור Short Interest (FINRA מפרסם חינם פעמיים בחודש; טרם חובר)"}}


# ------------------------------------------------------------------ point-in-time validation on past data
def _t(xs: list[float], base: float) -> float | None:
    if len(xs) < 3:
        return None
    s = stdev(xs)
    return (mean(xs) - base) / (s / math.sqrt(len(xs))) if s else None


def signal_study(prices: pd.DataFrame, horizons: tuple[int, ...] = (5, 10, 20), floor_days: int = 20, step: int = 5) -> dict[str, Any]:
    """For every past bar: did a signal at that bar (using only data up to it) precede better/worse returns?
    Also: how often did the floor computed at that bar hold for the next `floor_days` closes."""
    df = prices
    n = len(df)
    hmax = max(horizons)
    if n < MIN_BARS + hmax + 20:
        return {"available": False, "why": "היסטוריית מחירים קצרה מדי לבדיקה"}
    c = df["close"].to_numpy(float)
    pf, ff = pattern_frame(df), flow_frame(df)
    sigs = {k: pf[k].to_numpy(bool) for k in PATTERN_HE}
    sigs.update({k + "+vol": (pf[k] & pf["vol_confirm"]).to_numpy(bool) for k in ("bull_engulf", "bear_engulf", "hammer", "shooting_star")})
    sigs["quiet_accum"] = ff["quiet_accum"].to_numpy(bool)
    sigs["quiet_dist"] = ff["quiet_dist"].to_numpy(bool)
    rng = range(MIN_BARS, n - hmax)
    fwd = {h: np.array([c[i + h] / c[i] - 1 for i in rng]) for h in horizons}
    base = {h: float(fwd[h].mean()) for h in horizons}
    out_sig = {}
    for k, arr in sigs.items():
        idx = [j for j, i in enumerate(rng) if arr[i]]
        row = {"n": len(idx)}
        for h in horizons:
            xs = [float(fwd[h][j]) for j in idx]
            row[f"r{h}"] = mean(xs) if xs else None
            row[f"edge{h}"] = (mean(xs) - base[h]) if xs else None
            row[f"t{h}"] = _t(xs, base[h])
            row[f"hit{h}"] = (sum(x > 0 for x in xs) / len(xs)) if xs else None
        out_sig[k] = row
    piv = pivots(df)
    held, total, swing_held, swing_total, dist = 0, 0, 0, 0, []
    for i in range(MIN_BARS, n - floor_days, step):
        lv = levels_at(df, i, piv)
        ok = bool((c[i + 1:i + 1 + floor_days] >= lv["floor"]).all())
        total += 1
        held += ok
        dist.append(lv["floor"] / lv["close"] - 1)
        if lv["support"] is not None and lv["floor"] == lv["support"]:
            swing_total += 1
            swing_held += ok
    return {"available": True, "bars": n, "from": df.index[0].date().isoformat(), "to": df.index[-1].date().isoformat(),
            "baseline": base, "signals": out_sig,
            "floor": {"n": total, "held": held / total if total else None, "avg_dist": mean(dist) if dist else None,
                      "swing_n": swing_total, "swing_held": swing_held / swing_total if swing_total else None, "days": floor_days},
            "notes": ["כל אות מחושב רק מנתונים עד אותו יום (Point-in-Time); שפל/שיא נדנדה נחשב ידוע רק 3 ימים אחריו.",
                      "תשואות ללא עלויות מסחר; ההשוואה היא מול תשואה ממוצעת של כל הימים באותה מניה.",
                      "t ≥ 2 על מדגם קטן עדיין אינו הוכחה — יש לבחון על יקום רחב."]}


def pool_studies(studies: dict[str, dict]) -> dict[str, Any]:
    """Aggregate per-ticker studies: weighted by signal count."""
    ok = {t: s for t, s in studies.items() if s.get("available")}
    if not ok:
        return {"available": False}
    agg: dict[str, dict] = {}
    for s in ok.values():
        for k, row in s["signals"].items():
            a = agg.setdefault(k, {"n": 0, "edge10": 0.0, "edge20": 0.0, "hit10": 0.0})
            if row["n"] and row["edge10"] is not None:
                a["n"] += row["n"]
                a["edge10"] += row["edge10"] * row["n"]
                a["edge20"] += (row["edge20"] or 0) * row["n"]
                a["hit10"] += (row["hit10"] or 0) * row["n"]
    for a in agg.values():
        if a["n"]:
            a["edge10"] /= a["n"]
            a["edge20"] /= a["n"]
            a["hit10"] /= a["n"]
    fl_n = sum(s["floor"]["n"] for s in ok.values())
    fl_h = sum(s["floor"]["held"] * s["floor"]["n"] for s in ok.values() if s["floor"]["held"] is not None)
    return {"available": True, "tickers": len(ok), "signals": agg, "floor_held": fl_h / fl_n if fl_n else None, "floor_n": fl_n}
