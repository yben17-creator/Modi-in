"""Module 4 — Fallen Angels: undervalued quality vs value trap."""
from __future__ import annotations

from typing import Any

from ..models import CompanyData, v


def fallen_angel(cd: CompanyData, m: dict, h_score: float | None, val: dict, min_dd: float = 0.2) -> dict[str, Any]:
    dd = v(m["drawdown"])
    if dd is None:
        return {"cls": "לא ניתן לחשב", "why": ["חסר מחיר או שיא 52 שבועות"], "dd": None}
    g, fg = v(m["rev_growth_1y"]), v(m["fcf_growth"])
    om, omp = v(m["op_margin"]), v(m["op_margin_prev"])
    op_chg = om - omp if om is not None and omp is not None else None
    structural = [f for f in cd.flags if f.structural and f.severity >= 3]
    ret1y = v(m["ret1y"])
    gap = (g - ret1y) * 100 if g is not None and ret1y is not None else None
    res = {"dd": dd, "op_chg": op_chg, "gap": gap, "mult_comp": val.get("hist_disc"), "structural": bool(structural)}
    why: list[str] = []
    if dd < min_dd:
        res.update(cls="לא רלוונטי", why=[f"ירידה של פחות מ-{min_dd:.0%} מהשיא השנתי"])
        return res
    if None in (g, h_score):
        res.update(cls="לא חד-משמעי", why=["חסרים נתוני צמיחה או ציון בריאות לסיווג"])
        return res
    quality = h_score >= 60 and g >= 0.05 and (fg is None or fg > 0) and not structural and (op_chg is None or op_chg > -0.03)
    if quality:
        why.append("העסק ממשיך לצמוח" + (" ולהגדיל תזרים" if fg and fg > 0 else "") + " בזמן שהמניה ירדה")
        if fg is None:
            why.append("צמיחת FCF לא זמינה")
        res.update(cls="Undervalued Quality", why=why)
        return res
    if g < 0.03:
        why.append("צמיחת הכנסות כמעט אפסית או שלילית")
    if op_chg is not None and op_chg < -0.03:
        why.append("שחיקה במרווח התפעולי")
    if structural:
        why.append("סימנים לפגיעה מבנית: " + "; ".join(f.category for f in structural))
    if h_score < 50:
        why.append("איתנות פיננסית חלשה")
    res.update(cls="Value Trap Risk" if why else "לא חד-משמעי", why=why or ["ירידה משמעותית, אך הנתונים העסקיים מעורבים"])
    return res
