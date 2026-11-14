"""Module 8 — Post-earnings momentum monitor (technical indicators + alerts). Alerts are indications, not predictions."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..models import CompanyData, v


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["sma20"] = df["close"].rolling(20).mean()
    out["sma50"] = df["close"].rolling(50).mean()
    out["sma200"] = df["close"].rolling(200).mean()
    out["rsi"] = rsi(df["close"])
    out["atr"] = atr(df)
    return out


def daily_vol(df: pd.DataFrame | None, days: int = 120) -> float | None:
    if df is None or len(df) < 30:
        return None
    return float(df["close"].pct_change().tail(days).std())


def monitor(cd: CompanyData, m: dict, val: dict, bench: pd.DataFrame | None, rev_change: float | None) -> dict[str, Any]:
    df = cd.prices
    if df is None or len(df) < 70:
        return {"available": False, "why": "דורש לפחות 70 ימי מסחר של היסטוריית מחירים", "alerts": []}
    x = indicators(df)
    last = x.iloc[-1]
    c = x["close"]
    ret20 = c.iloc[-1] / c.iloc[-21] - 1
    rs = None
    if bench is not None:
        b = bench["close"].reindex(x.index).ffill()
        if not np.isnan(b.iloc[-21]):
            rs = ret20 - (b.iloc[-1] / b.iloc[-21] - 1)
    atr_pct = last["atr"] / last["close"]
    hist_atr = (x["atr"] / x["close"]).iloc[-65:-5].mean()
    vol_ratio = df["volume"].tail(5).mean() / df["volume"].iloc[-65:-5].mean() if df["volume"].iloc[-65:-5].mean() else None
    alerts = []
    rsi_max10 = x["rsi"].iloc[-11:-1].max()
    if last["close"] < last["sma20"] and last["rsi"] < 50 and rsi_max10 > 60:
        alerts.append({"k": "Momentum Weakening", "he": "היחלשות מומנטום",
                       "d": f"מחיר מתחת לממוצע 20 יום ו-RSI ירד ל-{last['rsi']:.0f} אחרי שיא {rsi_max10:.0f} ב-10 הימים האחרונים"})
    mid, price = val.get("mid"), v(cd.price)
    if mid and price and mid > 0 and price >= 0.9 * mid:
        alerts.append({"k": "Valuation Gap Closing", "he": "פער השווי נסגר", "d": f"המחיר {price:.2f} קרוב או מעל 90% משווי הבסיס ({mid:.2f})"})
    if cd.manual.get("guidance") == "lowered" or (rev_change is not None and rev_change < -0.02) or _rec_downgrade(cd):
        alerts.append({"k": "Negative Guidance Revision", "he": "עדכון תחזיות שלילי",
                       "d": "תחזית הנהלה הורדה (הזנה ידנית), ירידה בקונצנזוס EPS, או ירידה בהמלצות האנליסטים"})
    if hist_atr and atr_pct > 1.5 * hist_atr:
        alerts.append({"k": "Elevated Volatility", "he": "תנודתיות מוגברת", "d": f"ATR {atr_pct:.1%} לעומת ממוצע {hist_atr:.1%}"})
    if mid and price and not np.isnan(last["sma50"]):
        up, dn = mid - price, price - last["sma50"]
        if dn > 0 and up / dn < 1:
            alerts.append({"k": "Risk/Reward Deterioration", "he": "הרעה ביחס סיכוי/סיכון",
                           "d": f"מרחק לשווי הבסיס {up:.2f}$ לעומת מרחק לממוצע 50 יום {dn:.2f}$"})
    last_ev = cd.earnings_events[-1] if cd.earnings_events else None
    return {"available": True, "df": x.tail(130), "ret20": ret20, "rs": rs, "rsi": float(last["rsi"]), "atr_pct": float(atr_pct),
            "vol_ratio": vol_ratio, "alerts": alerts, "last_event": last_ev, "source": cd.prices_source}


def _rec_downgrade(cd: CompanyData) -> bool:
    r = cd.recommendations
    if len(r) < 2:
        return False
    def bull(x):
        tot = sum(x.get(k, 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
        return (x.get("strongBuy", 0) + x.get("buy", 0)) / tot if tot else None
    a, b = bull(r[-2]), bull(r[-1])
    return a is not None and b is not None and b < a - 0.1
