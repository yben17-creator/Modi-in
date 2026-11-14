"""Display formatting. Missing values always render as 'חסר' (never 0)."""
from __future__ import annotations

import math
from typing import Any

from .models import Val

NA = "חסר"


def _x(x: Any) -> Any:
    return x.value if isinstance(x, Val) else x


def ok(x: Any) -> bool:
    x = _x(x)
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def money(x: Any) -> str:
    x = _x(x)
    if not ok(x):
        return NA
    if x == math.inf:
        return "∞"
    s = "−" if x < 0 else ""
    a = abs(x)
    if a >= 1e9:
        return f"{s}${a / 1e9:,.2f}B"
    if a >= 1e6:
        return f"{s}${a / 1e6:,.0f}M"
    return f"{s}${a:,.0f}"


def price(x: Any) -> str:
    x = _x(x)
    return NA if not ok(x) else f"${x:,.2f}"


def pct(x: Any, d: int = 1, signed: bool = False) -> str:
    x = _x(x)
    if not ok(x):
        return NA
    if x in (math.inf, -math.inf):
        return "∞" if x > 0 else "−∞"
    return f"{'+' if signed and x > 0 else ''}{x * 100:.{d}f}%"


def num(x: Any, d: int = 2) -> str:
    x = _x(x)
    if not ok(x):
        return NA
    if x == math.inf:
        return "∞"
    if x == -math.inf:
        return "−∞"
    return f"{x:,.{d}f}"


def mult(x: Any) -> str:
    x = _x(x)
    return NA if not ok(x) or x <= 0 or x == math.inf else f"{x:.1f}x"


def score(x: Any) -> str:
    return NA if not ok(x) else f"{x:.0f}"


SEV = {1: "נמוכה", 2: "בינונית", 3: "גבוהה", 4: "קריטית"}
PLAN = {"10b5-1": "תוכנית 10b5-1 (מתוכננת)", "tax": "לצורכי מס (F)", "open": "שוק פתוח", "unknown": "אחר"}
DATE_STATUS = {"provider": "לפי ספק (לא אומת)", "estimated_local": "משוער (חישוב מקומי)", "confirmed_manual": "מאושר", "missing": "חסר"}
