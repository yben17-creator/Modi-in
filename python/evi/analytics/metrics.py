"""Layer 2 — deterministic calculations from raw data. Every output is a CALC `Val`; missing inputs → missing output."""
from __future__ import annotations

import math
from datetime import date

from ..models import CompanyData, Val, calc, missing, v


def _div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def compute_metrics(cd: CompanyData) -> dict[str, Val]:
    f = cd.f
    m: dict[str, Val] = {}
    price, sh_out, sh_dil = cd.price, f("shares_outstanding"), f("diluted_shares")
    cash, sti, std_, ltd = f("cash"), f("st_investments"), f("st_debt"), f("lt_debt")
    rev, rev_prev = f("revenue"), f("revenue_prev")

    # ---- capital structure
    m["mcap"] = calc(v(price) * v(sh_out) if price and sh_out else None, "מחיר × מניות במחזור", [price, sh_out])
    # Missing short-term investments / debt tags are treated as zero ONLY if cash is reported (common XBRL practice:
    # untagged = not present). This assumption is flagged in the note.
    zero_note = []
    sti_v = v(sti) if sti else (0.0 if cash else None)
    if not sti and cash:
        zero_note.append("השקעות קצרות לא דווחו → 0")
    std_v = v(std_) if std_ else (0.0 if cash else None)
    if not std_ and cash:
        zero_note.append("חוב קצר לא דווח → 0")
    ltd_v = v(ltd) if ltd else (0.0 if cash else None)
    if not ltd and cash:
        zero_note.append("חוב ארוך לא דווח → 0")
    note = "; ".join(zero_note)
    m["cash_all"] = calc(v(cash) + sti_v if cash and sti_v is not None else None, "מזומן + השקעות לזמן קצר", [cash], note)
    m["total_debt"] = calc(std_v + ltd_v if std_v is not None and ltd_v is not None else None, "חוב קצר + חוב ארוך", [cash], note)
    m["net_debt"] = calc(v(m["total_debt"]) - v(m["cash_all"]) if m["total_debt"] and m["cash_all"] else None,
                         "חוב כולל − מזומן והשקעות", [m["total_debt"], m["cash_all"]], note)
    m["ev"] = calc(v(m["mcap"]) + v(m["net_debt"]) if m["mcap"] and m["net_debt"] else None, "שווי שוק + חוב נטו", [m["mcap"], m["net_debt"]])
    eq = f("equity")
    m["equity"] = eq

    # ---- flows
    ocf, capex, sbc, ni, opi = f("ocf"), f("capex"), f("sbc"), f("net_income"), f("operating_income")
    m["revenue"] = rev
    m["fcf"] = calc(v(ocf) - v(capex) if ocf and capex else None, "תזרים מפעילות − CapEx", [ocf, capex])
    m["fcf_prev"] = calc(v(f("ocf_prev")) - v(f("capex_prev")) if f("ocf_prev") and f("capex_prev") else None, "FCF שנה קודמת",
                         [f("ocf_prev"), f("capex_prev")])
    m["adj_fcf"] = calc(v(m["fcf"]) - v(sbc) if m["fcf"] and sbc else None, "FCF − תגמול מבוסס מניות", [m["fcf"], sbc])
    da = f("d_and_a")
    m["ebitda"] = calc(v(opi) + v(da) if opi and da else None, "רווח תפעולי + פחת והפחתות", [opi, da])

    # ---- ratios
    def ratio(key, a, b, label, inputs):
        m[key] = calc(_div(a, b), label, inputs)
    ratio("current_ratio", v(f("current_assets")), v(f("current_liabilities")), "נכסים שוטפים / התחייבויות שוטפות", [f("current_assets"), f("current_liabilities")])
    quick_num = (v(cash) + (sti_v or 0) + (v(f("receivables")) or 0)) if cash else None
    ratio("quick_ratio", quick_num, v(f("current_liabilities")), "(מזומן + השקעות + לקוחות) / התחייבויות שוטפות", [cash, f("current_liabilities")])
    ratio("debt_to_equity", v(m["total_debt"]), v(eq) if eq and v(eq) > 0 else None, "חוב כולל / הון עצמי", [m["total_debt"], eq])
    if m["net_debt"] and m["ebitda"]:
        nd, e = v(m["net_debt"]), v(m["ebitda"])
        m["nd_ebitda"] = calc(nd / e if e > 0 else (-math.inf if nd <= 0 else math.inf), "חוב נטו / EBITDA", [m["net_debt"], m["ebitda"]],
                              "" if e > 0 else "EBITDA שלילי")
    else:
        m["nd_ebitda"] = calc(None, "חוב נטו / EBITDA", [m["net_debt"], m["ebitda"]])
    ie = f("interest_expense")
    if opi and ie and v(ie) > 0:
        m["coverage"] = calc(v(opi) / v(ie), "רווח תפעולי / הוצאות ריבית", [opi, ie])
    elif opi and m["total_debt"] and v(m["total_debt"]) == 0:
        m["coverage"] = Val(math.inf, "אין חוב", layer="CALC")
    else:
        m["coverage"] = calc(None, "רווח תפעולי / הוצאות ריבית", [opi, ie], "הוצאות ריבית לא דווחו")
    for key, num, label in (("gross_margin", f("gross_profit"), "רווח גולמי / הכנסות"), ("op_margin", opi, "רווח תפעולי / הכנסות"),
                            ("ebitda_margin", m["ebitda"], "EBITDA / הכנסות"), ("net_margin", ni, "רווח נקי / הכנסות"),
                            ("fcf_margin", m["fcf"], "FCF / הכנסות"), ("adj_fcf_margin", m["adj_fcf"], "FCF בניכוי SBC / הכנסות"),
                            ("sbc_pct", sbc, "SBC / הכנסות")):
        m[key] = calc(_div(v(num), v(rev)), label, [num, rev])
    opi_prev = f("operating_income_prev")
    m["op_margin_prev"] = calc(_div(v(opi_prev), v(rev_prev)), "מרווח תפעולי שנה קודמת", [opi_prev, rev_prev])
    # ROIC = NOPAT / (equity + debt − cash); effective tax rate if available else 21% (flagged)
    tax_rate = None
    if f("income_tax") and f("pretax_income") and v(f("pretax_income")) > 0:
        tax_rate = min(max(v(f("income_tax")) / v(f("pretax_income")), 0.0), 0.35)
    ic = v(eq) + v(m["net_debt"]) if eq and m["net_debt"] else None
    tr = tax_rate if tax_rate is not None else 0.21
    m["roic"] = calc(_div(v(opi) * (1 - tr), ic) if opi and ic and ic > 0 else None, "NOPAT / הון מושקע (הון + חוב נטו)",
                     [opi, eq, m["net_debt"]], "" if tax_rate is not None else "שיעור מס 21% (סטטוטורי) — מס אפקטיבי לא זמין")

    # ---- growth
    m["rev_growth_1y"] = calc(_div(v(rev), v(rev_prev)) - 1 if rev and rev_prev and v(rev_prev) > 0 else None, "צמיחת הכנסות שנתית", [rev, rev_prev])
    ann = cd.annual.get("revenue", [])
    m["rev_cagr_3y"] = calc((ann[-1]["val"] / ann[-4]["val"]) ** (1 / 3) - 1 if len(ann) >= 4 and ann[-4]["val"] > 0 else None,
                            "CAGR הכנסות 3 שנים (שנים פיסקליות)", [], "" if len(ann) >= 4 else "פחות מ-4 שנים פיסקליות")
    m["rev_cagr_5y"] = calc((ann[-1]["val"] / ann[-6]["val"]) ** (1 / 5) - 1 if len(ann) >= 6 and ann[-6]["val"] > 0 else None,
                            "CAGR הכנסות 5 שנים", [], "" if len(ann) >= 6 else "פחות מ-6 שנים פיסקליות")
    yoy = [ann[i]["val"] / ann[i - 1]["val"] - 1 for i in range(max(1, len(ann) - 5), len(ann)) if ann[i - 1]["val"] > 0]
    m["min_yoy"] = calc(min(yoy) if yoy else None, "צמיחה שנתית מינימלית (עד 5 שנים)", [])
    fp = v(m["fcf_prev"])
    m["fcf_growth"] = calc(v(m["fcf"]) / fp - 1 if m["fcf"] and fp and fp > 0 else None, "צמיחת FCF", [m["fcf"], m["fcf_prev"]],
                           "" if fp is None or fp > 0 else "FCF קודם שלילי — צמיחה באחוזים אינה מוגדרת")
    m["cash_conversion"] = calc(_div(v(m["fcf"]), v(ni)) if ni and v(ni) > 0 else None, "FCF / רווח נקי", [m["fcf"], ni])
    s0, s3 = f("shares_outstanding"), f("shares_outstanding_3y")
    m["dilution_rate"] = calc((v(s0) / v(s3)) ** (1 / 3) - 1 if s0 and s3 and v(s3) > 0 else None, "שינוי שנתי במספר המניות (3 שנים)", [s0, s3])
    m["fcf_yield"] = calc(_div(v(m["fcf"]), v(m["mcap"])), "FCF / שווי שוק", [m["fcf"], m["mcap"]])
    m["adj_fcf_yield"] = calc(_div(v(m["adj_fcf"]), v(m["mcap"])), "FCF בניכוי SBC / שווי שוק", [m["adj_fcf"], m["mcap"]])
    burn = -v(m["fcf"]) if m["fcf"] and v(m["fcf"]) < 0 else None
    m["runway_years"] = calc(v(m["cash_all"]) / burn if burn and m["cash_all"] else (math.inf if m["fcf"] and v(m["fcf"]) >= 0 else None),
                             "מזומן / שריפת מזומנים שנתית", [m["cash_all"], m["fcf"]])

    # ---- multiples
    eps_q = cd.quarterly.get("eps_diluted", [])
    eps_ttm = sum(x["val"] for x in eps_q[-4:]) if len(eps_q) >= 4 else None
    m["eps_ttm"] = Val(eps_ttm, "SEC EDGAR · EPS מדולל, 4 רבעונים אחרונים", eps_q[-1]["end"] if eps_q else None, "CALC") if eps_ttm is not None \
        else missing("אין 4 רבעוני EPS מדווחים")
    def mult(key, num, den, label, inputs, positive_den=True):
        a, b = v(num), v(den)
        m[key] = calc(a / b if a is not None and b is not None and (b > 0 or not positive_den) else None, label, inputs,
                      "" if b is None or b > 0 else "מכנה שלילי — מכפיל לא משמעותי")
    mult("pe", price, m["eps_ttm"], "מחיר / EPS 12 חודשים", [price, m["eps_ttm"]])
    eps_next = _forward_eps(cd)
    m["fwd_eps"] = eps_next
    mult("fpe", price, eps_next, "מחיר / EPS צפוי (שנתי)", [price, eps_next])
    mult("ev_rev", m["ev"], rev, "EV / הכנסות", [m["ev"], rev])
    mult("ev_ebitda", m["ev"], m["ebitda"], "EV / EBITDA", [m["ev"], m["ebitda"]])
    mult("ev_fcf", m["ev"], m["fcf"], "EV / FCF", [m["ev"], m["fcf"]])
    mult("p_fcf", m["mcap"], m["fcf"], "שווי שוק / FCF", [m["mcap"], m["fcf"]])
    mult("ps", m["mcap"], rev, "שווי שוק / הכנסות", [m["mcap"], rev])

    # ---- market data
    q = cd.quote_meta
    hi = q.get("high52")
    m["drawdown"] = calc(1 - v(price) / v(hi) if price and hi and v(hi) > 0 else None, "ירידה מהשיא השנתי", [price, hi])
    m["ret1y"], m["ret3m"] = q.get("ret1y") or missing("חסר"), q.get("ret3m") or missing("חסר")

    # ---- earnings date
    ne = cd.next_earnings or {}
    m["days_to_earnings"] = Val((date.fromisoformat(ne["date"]) - date.today()).days, ne.get("source", ""), ne["date"], "CALC") \
        if ne.get("date") else missing(ne.get("basis") or "אין תאריך דוח")
    return m


def _forward_eps(cd: CompanyData) -> Val:
    """Annualized forward EPS is only available from a consensus provider; we do NOT extrapolate it ourselves.
    If the next-quarter consensus exists, forward P/E is approximated as price / (next-quarter EPS × 4) and labeled."""
    ne = cd.next_earnings or {}
    e = ne.get("eps_est")
    if e is None:
        return missing("אין קונצנזוס EPS (דורש Finnhub)")
    return Val(float(e) * 4, source=f"{ne.get('source', '')} · EPS רבעון הבא × 4 (קירוב)", as_of=ne.get("date"), layer="CALC",
               note="קירוב: קונצנזוס הרבעון הבא כפול 4")
