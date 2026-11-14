"""Layer 3 — model scores. Components with missing inputs are excluded and the score is re-normalized over the
available components; `coverage` reports what share of the model could be evaluated. Below the minimum coverage
the score is None (not computable) rather than a guess."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from statistics import mean
from typing import Any

from ..models import CompanyData, v

CLASSES = ["עדיפות גבוהה למחקר", "מועמדת למעקב", "הזדמנות לא ודאית", "סיכון גבוה / לא עומדת בתנאי הסינון", "לא ניתן להעריך — נתונים חסרים"]


@dataclass
class Score:
    score: float | None
    parts: dict[str, dict[str, Any]] = field(default_factory=dict)
    coverage: float = 0.0
    notes: list[str] = field(default_factory=list)

    @staticmethod
    def build(parts: dict[str, dict[str, Any]], min_cov: float) -> "Score":
        avail = {k: p for k, p in parts.items() if p.get("pts") is not None}
        tot_max = sum(p["max"] for p in parts.values())
        got_max = sum(p["max"] for p in avail.values())
        cov = got_max / tot_max if tot_max else 0.0
        if cov < min_cov or got_max == 0:
            return Score(None, parts, cov, [f"כיסוי נתונים {cov:.0%} — מתחת לסף {min_cov:.0%}; הציון לא חושב"])
        return Score(round(100 * sum(p["pts"] for p in avail.values()) / got_max, 1), parts, cov)


def _part(label: str, mx: float, pts: float | None, basis: str, missing_why: str = "") -> dict[str, Any]:
    return {"label": label, "max": mx, "pts": pts, "basis": basis, "missing": missing_why if pts is None else ""}


# ----------------------------------------------------------------- Financial Health
def health(cd: CompanyData, m: dict, min_cov: float = 0.6) -> tuple[Score, list[str], float | None]:
    nd, ndE, cr = v(m["net_debt"]), v(m["nd_ebitda"]), v(m["current_ratio"])
    om, am, cov_, runway = v(m["op_margin"]), v(m["adj_fcf_margin"]), v(m["coverage"]), v(m["runway_years"])
    eq, opi, td, ca = v(m["equity"]), v(cd.f("operating_income")), v(m["total_debt"]), v(m["cash_all"])
    p: dict[str, dict] = {}
    if nd is None:
        p["balance"] = _part("איתנות מאזן", 20, None, "חוב נטו / EBITDA", "חוב נטו לא ניתן לחישוב")
    else:
        if nd <= 0:
            pts = 20
        elif ndE is None or ndE == math.inf:
            pts = 0
        else:
            pts = 16 if ndE < 1 else 12 if ndE < 2 else 8 if ndE < 3 else 4 if ndE < 4 else 0
        if eq is not None and eq <= 0:
            pts = min(pts, 4)
        p["balance"] = _part("איתנות מאזן", 20, pts, "מזומן נטו" if nd <= 0 else "חוב נטו / EBITDA")
    p["liquidity"] = _part("נזילות", 15, None if cr is None else (15 if cr >= 2 else 12 if cr >= 1.5 else 9 if cr >= 1.2 else 6 if cr >= 1 else 2),
                           "יחס שוטף", "יחס שוטף חסר")
    p["profit"] = _part("רווחיות", 20, None if om is None else (20 if om > .25 else 16 if om > .15 else 12 if om > .05 else 8 if om > 0 else 4 if om > -.1 else 0),
                        "מרווח תפעולי", "מרווח תפעולי חסר")
    p["cash"] = _part("איכות תזרים", 20, None if am is None else (20 if am > .2 else 16 if am > .1 else 12 if am > .05 else 8 if am > 0 else 4 if am > -.05 else 0),
                      "מרווח FCF בניכוי SBC", "FCF או SBC חסרים")
    mn, cagr = v(m["min_yoy"]), v(m["rev_cagr_3y"])
    if mn is None:
        p["stability"] = _part("יציבות הכנסות", 10, None, "צמיחה שנתית", "פחות משנתיים של הכנסות שנתיות")
    else:
        g = cagr if cagr is not None else v(m["rev_growth_1y"]) or 0
        p["stability"] = _part("יציבות הכנסות", 10, (6 + (4 if g > .15 else 2 if g > .05 else 0)) if mn > 0 else (3 if g > 0 else 0), "צמיחה ומינימום YoY")
    if td == 0 or cov_ == math.inf:
        ds = 15
    elif opi is not None and opi <= 0:
        ds = 6 if (runway is not None and runway > 3 and ca is not None and td is not None and ca > td) else 2
    elif cov_ is None:
        ds = None
    else:
        ds = 15 if cov_ > 20 else 12 if cov_ > 10 else 9 if cov_ > 5 else 5 if cov_ > 2 else 0
    p["debt"] = _part("יכולת פירעון", 15, ds, "כיסוי ריבית / runway", "הוצאות ריבית לא דווחו")
    sc = Score.build(p, min_cov)
    severe: list[str] = []
    if cr is not None and cr < 1 and ndE is not None and ndE > 4:
        severe.append("נזילות נמוכה לצד מינוף גבוה")
    if cov_ is not None and cov_ < 1.5 and (td or 0) > 0:
        severe.append("כיסוי ריבית נמוך מ-1.5")
    if v(m["fcf"]) is not None and v(m["fcf"]) < 0 and runway is not None and runway < 2:
        severe.append("תזרים שלילי ו-runway קצר משנתיים")
    near = None
    if cd.maturities:
        yr = date.today().year
        near = sum(x["amount"] for x in cd.maturities if isinstance(x["year"], int) and x["year"] <= yr + 1)
        if ca is not None and near > ca + max(v(m["fcf"]) or 0, 0):
            severe.append(f"פירעונות חוב עד סוף {yr + 1} גבוהים מהמזומן והתזרים")
    return sc, severe, near


# ----------------------------------------------------------------- Earnings Opportunity
def earnings(cd: CompanyData, m: dict, val, timing, min_cov: float = 0.5) -> Score:
    s = cd.surprises
    p: dict[str, dict] = {}
    if s:
        beat = sum(1 for x in s if (x["actual"] - x["estimate"]) > 0) / len(s)
        sp = [x["surprise_pct"] for x in s if x.get("surprise_pct") is not None]
        p["beat"] = _part(f"עקיפת תחזיות EPS ({len(s)} רבעונים)", 25, 25 * beat, "Finnhub")
        p["surprise"] = _part("גודל הפתעה ממוצע", 10, 10 * min(max(mean(sp) / 10, 0), 1) if sp else None, "Finnhub", "חסר")
    else:
        p["beat"] = _part("עקיפת תחזיות EPS", 25, None, "", "אין היסטוריית הפתעות (דורש Finnhub)")
        p["surprise"] = _part("גודל הפתעה ממוצע", 10, None, "", "אין היסטוריית הפתעות")
    rev = estimate_revision(cd)
    p["revisions"] = _part("כיוון עדכוני תחזיות EPS", 20, None if rev is None else 20 * min(max((rev * 100 + 5) / 10, 0), 1),
                           "צילומי קונצנזוס מקומיים", "נדרשים צילומי קונצנזוס של 30+ יום (נאספים בכל סריקה)")
    g = cd.manual.get("guidance")
    p["guidance"] = _part("תחזית הנהלה", 10, {"raised": 10, "maintained": 5, "lowered": 0}.get(g), "הזנה ידנית",
                          "לא הוזנה — תחזיות הנהלה אינן זמינות כנתון מובנה בחינם")
    r3 = v(m["ret3m"])
    p["priced"] = _part("ציפיות שטרם תומחרו (מומנטום 3ח׳)", 15, None if r3 is None else (15 if r3 <= 0 else 15 * (1 - min(r3 / .15, 1))),
                        "תשואה 3 חודשים", "תשואת 3 חודשים חסרה")
    rx = timing.get("reactions") if timing else None
    p["react"] = _part("תגובות מחיר היסטוריות", 10, 10 * sum(1 for r in rx if r > 0) / len(rx) if rx else None,
                       "8-K Item 2.02 + מחירים", "דורש היסטוריית מחירים")
    mos = val.get("mos") if val else None
    p["rerate"] = _part("פוטנציאל הערכה מחודשת", 10, None if mos is None else (10 * min(max(mos, 0) / .3, 1)), "MoS מול DCF", "DCF לא חושב")
    sc = Score.build(p, min_cov)
    if s and len(s) < 8:
        sc.notes.append(f"זמינים {len(s)} רבעוני הפתעה בלבד (פחות משמונה) — ניתוח חלקי")
    return sc


def estimate_revision(cd: CompanyData, min_days: int = 30) -> float | None:
    """% change in consensus EPS for the same fiscal period across local snapshots spanning ≥ min_days."""
    h = cd.estimate_history
    if not h:
        return None
    period = h[-1]["period"]
    same = [x for x in h if x["period"] == period and x["eps_est"] is not None]
    if len(same) < 2:
        return None
    a, b = same[0], same[-1]
    if (date.fromisoformat(b["day"]) - date.fromisoformat(a["day"])).days < min_days or not a["eps_est"]:
        return None
    return (b["eps_est"] - a["eps_est"]) / abs(a["eps_est"])


# ----------------------------------------------------------------- Risk
SEV_PTS = {1: 3, 2: 8, 3: 15, 4: 35}
STATUS_W = {"מאומת": 1.0, "דיווח תקשורתי": 0.6, "ספקולטיבי": 0.4}


def risk(cd: CompanyData, m: dict, h: Score, severe: list[str], vol: float | None, cfg: dict) -> dict[str, Any]:
    items: list[dict] = []
    for fl in cd.flags:
        items.append({"src": fl.title, "pts": SEV_PTS[fl.severity] * STATUS_W.get(fl.status, .5) * (1 if fl.known else 1.2)})
    dr = v(m["dilution_rate"])
    if dr is not None:
        if dr > .05:
            items.append({"src": "דילול שנתי מעל 5%", "pts": 15})
        elif dr > .02:
            items.append({"src": "דילול שנתי 2–5%", "pts": 8})
        elif dr > 0:
            items.append({"src": "דילול שנתי חיובי", "pts": 3})
    d = cd.dilution
    if d.get("has_recent_offering"):
        items.append({"src": "תשקיף הנפקה (424B) ב-12 החודשים האחרונים", "pts": 8})
    if d.get("has_shelf"):
        items.append({"src": "מסגרת Shelf קיימת", "pts": 3})
    thr = float(cfg.get("unusual_insider_sale_usd", 5_000_000))
    unusual = [t for t in cd.insiders if t.kind == "sell" and t.plan == "open" and (t.value or 0) >= thr]
    if unusual:
        items.append({"src": "מכירות חריגות של בעלי עניין מחוץ לתוכנית 10b5-1", "pts": 8})
    if h.score is not None:
        items.append({"src": "פער באיתנות פיננסית", "pts": (100 - h.score) * .25})
    if vol is not None:
        if vol > .035:
            items.append({"src": "תנודתיות יומית גבוהה", "pts": 8})
        elif vol > .025:
            items.append({"src": "תנודתיות יומית בינונית-גבוהה", "pts": 4})
    if severe:
        items.append({"src": "סיכון פיננסי חמור", "pts": 15})
    checked = ["הגשות 8-K (SEC)", "Form 4 (SEC)", "הנפקות S-3/424B (SEC)"] + (["חדשות (Finnhub)"] if any("Finnhub" in f.source for f in cd.flags) or cd.surprises_source else [])
    score = round(min(max(sum(i["pts"] for i in items), 0), 100), 1)
    override = None
    crit = next((f for f in cd.flags if f.severity == 4 and f.status == "מאומת"), None)
    if crit:
        override = {"level": "disqualify", "reason": f"Risk Override: {crit.title}"}
    elif score > float(cfg.get("disqualify_score", 70)):
        override = {"level": "disqualify", "reason": "Risk Override: ציון סיכון מעל הסף"}
    elif severe:
        override = {"level": "cap", "reason": "Risk Override: " + severe[0]}
    else:
        new3 = next((f for f in cd.flags if f.severity >= 3 and not f.known), None)
        if new3:
            override = {"level": "cap", "reason": f"Risk Override: אירוע חדש בחומרה גבוהה — {new3.title}"}
    return {"score": score, "items": items, "override": override, "unusual": unusual, "checked": checked}


# ----------------------------------------------------------------- Final
def final(h: Score, val: dict, e: Score, r: dict, fallen: dict, cfg: dict) -> dict[str, Any]:
    hs, vs, es = h.score, val.get("score"), e.score
    min_h = float(cfg.get("min_health", 45))
    if r["override"] and r["override"]["level"] == "disqualify":
        return {"composite": None, "idx": 3, "cls": CLASSES[3], "capped": False, "reason": r["override"]["reason"]}
    if hs is None or vs is None:
        return {"composite": None, "idx": 4, "cls": CLASSES[4], "capped": False,
                "reason": "ציון בריאות או ציון תמחור לא חושבו בגלל נתונים חסרים — המערכת אינה מדרגת חברה ללא בסיס איכות ותמחור."}
    if hs < min_h:
        return {"composite": None, "idx": 3, "cls": CLASSES[3], "capped": False, "reason": f"ציון בריאות {hs:.0f} מתחת לסף {min_h:.0f}"}
    w = {"h": .35, "v": .35, "e": .2, "r": .1}
    parts = {"h": hs, "v": vs, "e": es, "r": 100 - r["score"]}
    avail = {k: x for k, x in parts.items() if x is not None}
    comp = round(sum(w[k] * x for k, x in avail.items()) / sum(w[k] for k in avail), 1)
    mos = val.get("mos")
    if comp >= cfg.get("high_priority_composite", 65) and mos is not None and mos >= cfg.get("high_priority_mos", .15) and r["score"] < 50:
        idx = 0
    elif comp >= cfg.get("watch_composite", 55) and vs >= cfg.get("watch_min_valuation", 40):
        idx = 1
    else:
        idx = 2
    cap = None
    if idx < 1 and r["override"] and r["override"]["level"] == "cap":
        cap = r["override"]["reason"]
    elif idx < 1 and fallen.get("cls") == "Value Trap Risk":
        cap = "סימני Value Trap — נדרש אימות שהפגיעה אינה מבנית"
    if cap:
        idx = 1
    return {"composite": comp, "idx": idx, "cls": CLASSES[idx], "capped": bool(cap), "reason": cap or "",
            "missing_parts": [k for k, x in parts.items() if x is None]}
