"""The ten screens of the application."""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..analytics.scores import CLASSES
from ..analytics.timing import best_window
from ..analytics.valuation import Assumptions, MULTIPLES
from ..fmt import DATE_STATUS, NA, PLAN, SEV, money, mult, num, pct, price, score
from ..models import now_iso, v
from ..reports import export
from ..reports.hebrew import dilution_text, earnings_text, sections, solvency_text
from ..sectors import SECTORS
from ..validation.backtest import walk_forward
from .common import (C, by_ticker, cls_badge, fig_base, lyr, need_results, recompute, resources, results, score_cfg,
                     select_company, set_override, show_alert, state, val_rows)


def _open_selected(event, tickers: list[str]) -> None:
    """Row selection in a dataframe → remember company (user then opens the report page)."""
    try:
        rows = event.selection.rows
    except AttributeError:
        rows = []
    if rows:
        state()["sel"] = tickers[rows[0]]
        st.success(f"נבחרה {tickers[rows[0]]} — פתח \"דוח מחקר\" בסרגל הצד לסקירה המלאה.")


def _date_cell(r) -> str:
    ne = r.cd.next_earnings or {}
    return ne.get("date") or NA


# =================================================================== 1. MARKET SCANNER
def page_scanner() -> None:
    st.header("סורק שוק — NASDAQ / NYSE")
    ss = state()
    for n in ss["notes"]:
        st.caption("• " + n)
    if not need_results():
        return
    rs = results()
    c1, c2, c3, c4 = st.columns([2, 2, 1, 2])
    with c1:
        win = st.slider("חלון ימים עד הדוח (סינון תצוגה)", -10, 120, (int(ss.get("dmin", 7)), int(ss.get("dmax", 30))))
    with c2:
        secs = st.multiselect("סקטורים", SECTORS, default=[])
    with c3:
        min_h = st.number_input("בריאות מינ׳", 0, 100, 0)
    with c4:
        q = st.text_input("חיפוש שם / טיקר")
    rows, tickers = [], []
    for r in rs:
        d = v(r.m["days_to_earnings"])
        in_win = d is not None and win[0] <= d <= win[1]
        if not in_win and not r.cd.manual.get("_watch_only"):
            continue
        if secs and r.cd.sector not in secs:
            continue
        if min_h and (r.h.score is None or r.h.score < min_h):
            continue
        if q and q.lower() not in (r.cd.name + r.ticker).lower():
            continue
        ne = r.cd.next_earnings or {}
        tickers.append(r.ticker)
        rows.append({"Company": r.cd.name, "Ticker": r.ticker, "מחיר": v(r.cd.price), "שווי שוק": v(r.m["mcap"]), "EV": v(r.m["ev"]),
                     "דוח הבא": ne.get("date"), "סטטוס תאריך": DATE_STATUS.get(ne.get("status"), "חסר"), "ימים": d,
                     "הכנסות (TTM)": v(r.m["revenue"]), "רווח נקי": v(r.cd.f("net_income")), "FCF": v(r.m["fcf"]),
                     "בריאות": r.h.score, "תמחור": r.val.get("score"), "הזדמנות דוח": r.e.score, "סיכון": r.r["score"],
                     "הערכה": r.fin["cls"] + (" ⤓" if r.fin.get("capped") else ""), "⚠": "⚠" if r.severe else "",
                     "דוחות כספיים נכון ל": r.m["revenue"].as_of, "מקור מחיר": (r.cd.price.source or NA) + (f" · {r.cd.price.as_of[:10]}" if r.cd.price.as_of else "")})
    df = pd.DataFrame(rows)
    if df.empty:
        st.warning("אין חברות שעומדות במסננים.")
        return
    money_fmt = st.column_config.NumberColumn(format="compact")
    ev = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
                      column_config={"מחיר": st.column_config.NumberColumn(format="$%.2f"), "שווי שוק": money_fmt, "EV": money_fmt,
                                     "הכנסות (TTM)": money_fmt, "רווח נקי": money_fmt, "FCF": money_fmt,
                                     "בריאות": score_cfg("בריאות"), "תמחור": score_cfg("תמחור"), "הזדמנות דוח": score_cfg("הזדמנות דוח"),
                                     "סיכון": score_cfg("סיכון", True)})
    _open_selected(ev, tickers)
    st.caption(f"{len(df)} חברות מוצגות מתוך {len(rs)} שנותחו. תא ריק = נתון חסר (לא הושלם). ⤓ = דירוג הוגבל ע\"י Risk Override / Value Trap. "
               "סטטוס תאריך: 'לפי ספק' = תאריך מ-Finnhub שלא אומת מול הודעת החברה; 'משוער' = חישוב מקומי; 'מאושר' = אושר ידנית.")
    st.download_button("ייצוא ל-Excel", export.scanner_xlsx([by_ticker(t) for t in tickers]), f"EVI_scanner_{date.today()}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    pts = [(r.val.get("score"), r.h.score, r.ticker) for r in rs if r.val.get("score") is not None and r.h.score is not None]
    if pts:
        fig = go.Figure(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], text=[p[2] for p in pts], mode="markers+text",
                                   textposition="top center", marker=dict(size=10, color=C["s1"], line=dict(width=2, color=C["bg"])),
                                   hovertemplate="%{text}<br>תמחור %{x:.0f} · בריאות %{y:.0f}<extra></extra>"))
        fig.update_xaxes(range=[0, 100], title="ציון תמחור")
        fig.update_yaxes(range=[0, 100], title="ציון בריאות")
        st.plotly_chart(fig_base(fig, 380, "איכות מול תמחור (חברות שחושבו להן שני הציונים)"), use_container_width=True)


# =================================================================== 2. FINANCIAL QUALITY
FIN_LABELS = {"total_assets": "סך נכסים", "total_liabilities": "סך התחייבויות", "equity": "הון עצמי", "cash": "מזומן ושווי מזומן",
              "st_investments": "השקעות לזמן קצר", "st_debt": "חוב לזמן קצר", "lt_debt": "חוב לזמן ארוך", "current_assets": "נכסים שוטפים",
              "current_liabilities": "התחייבויות שוטפות", "revenue": "הכנסות", "gross_profit": "רווח גולמי", "operating_income": "רווח תפעולי",
              "net_income": "רווח נקי", "ocf": "תזרים מפעילות שוטפת", "capex": "השקעות הוניות (CapEx)", "sbc": "תגמול מבוסס מניות",
              "interest_expense": "הוצאות ריבית", "d_and_a": "פחת והפחתות", "convertible_debt": "אג\"ח להמרה", "shares_outstanding": "מניות במחזור",
              "diluted_shares": "מניות בדילול מלא"}
CALC_LABELS = {"cash_all": "מזומן + השקעות", "total_debt": "חוב כולל", "net_debt": "חוב נטו", "current_ratio": "יחס שוטף", "quick_ratio": "יחס מהיר",
               "debt_to_equity": "חוב / הון", "nd_ebitda": "חוב נטו / EBITDA", "coverage": "כיסוי ריבית", "ebitda": "EBITDA",
               "gross_margin": "מרווח גולמי", "op_margin": "מרווח תפעולי", "ebitda_margin": "מרווח EBITDA", "net_margin": "מרווח נקי",
               "roic": "ROIC", "fcf": "FCF", "fcf_margin": "מרווח FCF", "adj_fcf": "FCF בניכוי SBC", "adj_fcf_margin": "מרווח FCF בניכוי SBC",
               "fcf_yield": "FCF Yield", "fcf_growth": "צמיחת FCF", "cash_conversion": "המרת מזומן (FCF/רווח)", "sbc_pct": "SBC / הכנסות",
               "rev_growth_1y": "צמיחת הכנסות שנתית", "rev_cagr_3y": "CAGR הכנסות 3ש׳", "rev_cagr_5y": "CAGR הכנסות 5ש׳", "dilution_rate": "דילול שנתי"}
PCT_KEYS = {"gross_margin", "op_margin", "ebitda_margin", "net_margin", "roic", "fcf_margin", "adj_fcf_margin", "fcf_yield", "fcf_growth",
            "sbc_pct", "rev_growth_1y", "rev_cagr_3y", "rev_cagr_5y", "dilution_rate"}
RATIO_KEYS = {"current_ratio", "quick_ratio", "debt_to_equity", "nd_ebitda", "coverage", "cash_conversion"}


def _fmt_any(k, x):
    if k in PCT_KEYS:
        return pct(x)
    if k in RATIO_KEYS:
        return num(x)
    if k in ("shares_outstanding", "diluted_shares"):
        return f"{x.value / 1e6:,.1f}M"
    return money(x)


def page_quality() -> None:
    st.header("ניתוח איכות פיננסית — שלב סינון מחייב")
    if not need_results():
        return
    rows, tickers = [], []
    for r in results():
        m = r.m
        tickers.append(r.ticker)
        nd = v(m["net_debt"])
        rows.append({"Company": r.cd.name, "יחס שוטף": v(m["current_ratio"]), "יחס מהיר": v(m["quick_ratio"]), "חוב/הון": v(m["debt_to_equity"]),
                     "חוב נטו/EBITDA": "מזומן נטו" if nd is not None and nd <= 0 else num(m["nd_ebitda"], 1),
                     "כיסוי ריבית": num(m["coverage"], 1), "מזומן+השקעות": v(m["cash_all"]), "חוב כולל": v(m["total_debt"]),
                     "מרווח גולמי": v(m["gross_margin"]), "מרווח תפעולי": v(m["op_margin"]), "ROIC": v(m["roic"]), "מרווח FCF": v(m["fcf_margin"]),
                     "FCF בניכוי SBC": v(m["adj_fcf_margin"]), "CAGR 3ש׳": v(m["rev_cagr_3y"]), "בריאות": r.h.score,
                     "כיסוי נתונים": r.h.coverage, "סיכון חמור": "⚠ " + "; ".join(r.severe) if r.severe else ""})
    pc = st.column_config.NumberColumn(format="percent")
    ev = st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
                      column_config={"מזומן+השקעות": st.column_config.NumberColumn(format="compact"), "חוב כולל": st.column_config.NumberColumn(format="compact"),
                                     "מרווח גולמי": pc, "מרווח תפעולי": pc, "ROIC": pc, "מרווח FCF": pc, "FCF בניכוי SBC": pc, "CAGR 3ש׳": pc,
                                     "כיסוי נתונים": pc, "בריאות": score_cfg("בריאות"),
                                     "יחס שוטף": st.column_config.NumberColumn(format="%.2f"), "יחס מהיר": st.column_config.NumberColumn(format="%.2f"),
                                     "חוב/הון": st.column_config.NumberColumn(format="%.2f")})
    _open_selected(ev, tickers)
    st.caption("חוב אינו פוסל אוטומטית: הציון מעריך חוב ביחס ל-EBITDA, לנזילות, לכיסוי הריבית ולתזרים. איכות התזרים נמדדת לאחר ניכוי SBC. "
               "רכיב שחסרים לו נתונים מוצא מהציון, והציון מחושב רק כשכיסוי הנתונים 60% ומעלה.")
    r = select_company("q_sel")
    if not r:
        return
    st.subheader(f"{r.cd.name} — פירוט ציון הבריאות")
    if r.severe:
        show_alert("⚠ <b>סיכון פיננסי חמור:</b> " + " · ".join(r.severe), "crit")
    a, b = st.columns(2)
    with a:
        for p in r.h.parts.values():
            if p["pts"] is None:
                st.markdown(f"**{p['label']}** — <span class='evi-miss'>חסר: {p['missing']}</span>", unsafe_allow_html=True)
            else:
                st.progress(p["pts"] / p["max"], text=f"{p['label']}: {p['pts']:.0f}/{p['max']} ({p['basis']})")
        st.markdown(f"<p>{solvency_text(r)}</p>", unsafe_allow_html=True)
    with b:
        if r.cd.maturities:
            fig = go.Figure(go.Bar(x=[str(x["year"]) for x in r.cd.maturities], y=[x["amount"] for x in r.cd.maturities], marker_color=C["s1"],
                                   hovertemplate="%{x}: %{y:$,.0f}<extra></extra>"))
            st.plotly_chart(fig_base(fig, 260, f"לוח פירעונות חוב (10-K, נכון ל-{r.cd.maturities_as_of})"), use_container_width=True)
        else:
            st.markdown("<span class='evi-miss'>לוח פירעונות החוב לא דווח ב-XBRL.</span>", unsafe_allow_html=True)
    st.markdown(f"#### נתונים גולמיים {lyr('RAW')} וחישובים {lyr('CALC')}", unsafe_allow_html=True)
    t1, t2 = st.tabs(["נתונים גולמיים (SEC XBRL)", "יחסים וחישובים"])
    with t1:
        st.dataframe(val_rows(r.cd.fin, FIN_LABELS, _fmt_any), hide_index=True, use_container_width=True)
    with t2:
        st.dataframe(val_rows(r.m, CALC_LABELS, _fmt_any), hide_index=True, use_container_width=True)


# =================================================================== 3. UNDERVALUED
def page_value() -> None:
    st.header("מנוע שווי הוגן ותמחור חסר")
    if not need_results():
        return
    rows = []
    for r in results():
        vv = r.val
        rows.append({"Company": r.cd.name, "מחיר": v(r.cd.price), "שווי שמרני": vv.get("low"), "שווי בסיס": vv.get("mid"), "שווי אופטימי": vv.get("high"),
                     "Margin of Safety": vv.get("mos"), "אפסייד לבסיס": vv.get("upside"), "הנחה מול עמיתים": vv.get("rel_disc"),
                     "הנחה מול היסטוריה": vv.get("hist_disc"), "ציון תמחור": vv.get("score"),
                     "אמינות DCF": ("סבירה" if vv.get("reliable") else "נמוכה") if vv.get("mid") is not None else vv.get("dcf_missing", "לא חושב")})
    pc = st.column_config.NumberColumn(format="percent")
    usd = st.column_config.NumberColumn(format="$%.2f")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"מחיר": usd, "שווי שמרני": usd, "שווי בסיס": usd, "שווי אופטימי": usd, "Margin of Safety": pc, "אפסייד לבסיס": pc,
                                "הנחה מול עמיתים": pc, "הנחה מול היסטוריה": pc, "ציון תמחור": score_cfg("ציון תמחור")})
    st.caption("DCF מבוסס הכנסות ל-10 שנים, מרווח FCF בניכוי SBC שמתכנס למרווח יעד, ושלושה תרחישים. ההשוואה לעמיתים מחושבת רק מחברות "
               "שנסרקו באותו סקטור (מינימום 3) — אין שימוש בחציונים חיצוניים או מומצאים. מכפיל נמוך לבדו אינו הוכחה לתמחור חסר: "
               "כשהצמיחה נמוכה מ-3% או שקיים דגל מבני, משקל המכפילים מופחת ב-50%. ההנחות ניתנות לשינוי בדוח המחקר.")
    st.subheader("Fallen Angels — Undervalued Quality מול Value Trap")
    fa = [r for r in results() if r.fa.get("dd") is not None and r.fa["dd"] >= 0.2]
    if not fa:
        st.info("אין חברות בירידה של 20%+ מהשיא השנתי (או שחסר מחיר / שיא 52 שבועות).")
    else:
        st.dataframe(pd.DataFrame([{"Company": r.cd.name, "ירידה מהשיא": -r.fa["dd"], "תשואה 12ח׳": v(r.m["ret1y"]), "צמיחת הכנסות": v(r.m["rev_growth_1y"]),
                                    "צמיחת FCF": v(r.m["fcf_growth"]), "שינוי מרווח תפעולי (pp)": None if r.fa["op_chg"] is None else r.fa["op_chg"] * 100,
                                    "דחיסת מכפיל מול היסטוריה": r.fa.get("mult_comp"), "פער עסק/מניה (pp)": r.fa.get("gap"), "סיווג": r.fa["cls"],
                                    "נימוק": "; ".join(r.fa["why"])} for r in sorted(fa, key=lambda x: -x.fa["dd"])]),
                     hide_index=True, use_container_width=True,
                     column_config={"ירידה מהשיא": pc, "תשואה 12ח׳": pc, "צמיחת הכנסות": pc, "צמיחת FCF": pc, "דחיסת מכפיל מול היסטוריה": pc,
                                    "שינוי מרווח תפעולי (pp)": st.column_config.NumberColumn(format="%.1f"), "פער עסק/מניה (pp)": st.column_config.NumberColumn(format="%.0f")})
        st.caption("פער עסק/מניה = צמיחת הכנסות (pp) פחות תשואת המניה ב-12 חודשים. שינויים בהנהלה, חשש מתחרות ומהשפעת AI נלקחים מדגלי 8-K "
                   "ומחדשות (מסווגים כ'מבני' כשמדובר באיום תחרותי) — יש לאמת בקריאת המקורות.")


# =================================================================== 4. UPCOMING EARNINGS + MONITOR
def page_earnings() -> None:
    st.header("דוחות רבעוניים קרובים")
    if not need_results():
        return
    up = sorted([r for r in results() if v(r.m["days_to_earnings"]) is not None and v(r.m["days_to_earnings"]) >= 0],
                key=lambda r: v(r.m["days_to_earnings"]))
    rows = []
    for r in up:
        ne, s = r.cd.next_earnings, r.cd.surprises
        rows.append({"Company": r.cd.name, "תאריך": ne.get("date"), "סטטוס": DATE_STATUS.get(ne.get("status")), "ימים": v(r.m["days_to_earnings"]),
                     "מועד": {"amc": "אחרי המסחר", "bmo": "לפני המסחר"}.get((ne.get("hour") or "").lower(), "לא ידוע"),
                     "EPS צפוי": ne.get("eps_est"), "הכנסות צפויות": ne.get("rev_est"), "שינוי קונצנזוס": r.rev_change,
                     "עקיפות EPS": f"{sum(1 for x in s if x['actual'] > x['estimate'])}/{len(s)}" if s else NA,
                     "תחזית הנהלה": {"raised": "הועלתה", "maintained": "נשמרה", "lowered": "הורדה"}.get(r.cd.manual.get("guidance"), "לא הוזנה"),
                     "תשואה 3ח׳": v(r.m["ret3m"]), "ציון הזדמנות": r.e.score, "כיסוי": r.e.coverage})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     column_config={"EPS צפוי": st.column_config.NumberColumn(format="$%.2f"), "הכנסות צפויות": st.column_config.NumberColumn(format="compact"),
                                    "שינוי קונצנזוס": st.column_config.NumberColumn(format="percent"), "תשואה 3ח׳": st.column_config.NumberColumn(format="percent"),
                                    "כיסוי": st.column_config.NumberColumn(format="percent"), "ציון הזדמנות": score_cfg("ציון הזדמנות")})
    st.caption("ציון ההזדמנות מחושב רק כשלפחות 50% מרכיביו זמינים. עדכוני אנליסטים נמדדים מצילומי קונצנזוס שהמערכת שומרת בכל סריקה "
               "(דורש 30+ יום של סריקות). תחזית הנהלה אינה זמינה כנתון מובנה בחינם — ניתן להזין אותה ידנית בדוח המחקר.")
    r = select_company("e_sel")
    if r:
        st.subheader(f"{r.cd.name} — ניתוח הזדמנות הדוח")
        a, b = st.columns(2)
        with a:
            for p in r.e.parts.values():
                if p["pts"] is None:
                    st.markdown(f"**{p['label']}** — <span class='evi-miss'>חסר: {p['missing']}</span>", unsafe_allow_html=True)
                else:
                    st.progress(min(p["pts"] / p["max"], 1.0), text=f"{p['label']}: {p['pts']:.1f}/{p['max']}")
            for n in r.e.notes:
                show_alert(n)
            st.markdown(f"<p>{earnings_text(r)}</p>", unsafe_allow_html=True)
        with b:
            s = r.cd.surprises
            if s:
                fig = go.Figure(go.Bar(x=[x["period"] for x in s], y=[x["surprise_pct"] for x in s],
                                       marker_color=[C["s1"] if (x["surprise_pct"] or 0) >= 0 else C["s2"] for x in s]))
                st.plotly_chart(fig_base(fig, 230, f"הפתעת EPS (%) — {r.cd.surprises_source}"), use_container_width=True)
            else:
                st.markdown("<span class='evi-miss'>היסטוריית הפתעות EPS חסרה (דורש Finnhub).</span>", unsafe_allow_html=True)
            if r.t.get("available"):
                ev_ = r.t["events"][-12:]
                fig = go.Figure(go.Bar(x=[e["date"] for e in ev_], y=[e["react"] * 100 for e in ev_],
                                       marker_color=[C["s1"] if e["react"] >= 0 else C["s2"] for e in ev_]))
                st.plotly_chart(fig_base(fig, 230, "תגובת המניה ביום התגובה לדוח (%) — מועדי 8-K אמיתיים"), use_container_width=True)
            else:
                st.markdown(f"<span class='evi-miss'>תגובות היסטוריות: {r.t.get('why')}</span>", unsafe_allow_html=True)
    st.subheader("Post-Earnings Momentum Monitor")
    st.caption("חברות שדיווחו ב-10 הימים האחרונים (לפי 8-K Item 2.02) וחברות ברשימת המעקב. ההתראות הן אינדיקציות — לא חיזוי ודאי של תיקון במחיר.")
    _, store, _ = resources()
    watch = set(store.watch_list())
    today = date.today()
    mon = [r for r in results() if (r.cd.earnings_events and (today - date.fromisoformat(r.cd.earnings_events[-1]["filed"])).days <= 10) or r.ticker in watch]
    if not mon:
        st.info("אין חברות שדיווחו לאחרונה או ברשימת המעקב.")
    for r in mon:
        with st.expander(f"{r.cd.name} ({r.ticker})" + (f" — דיווח ב-{r.cd.earnings_events[-1]['filed']}" if r.cd.earnings_events else ""), expanded=True):
            mo = r.mon
            if not mo.get("available"):
                st.markdown(f"<span class='evi-miss'>{mo.get('why')}</span>", unsafe_allow_html=True)
                continue
            k = st.columns(6)
            k[0].metric("Relative Strength 20י׳", pct(mo["rs"], 1, True))
            k[1].metric("RSI", f"{mo['rsi']:.0f}")
            k[2].metric("ATR", pct(mo["atr_pct"]))
            k[3].metric("מחזור 5י׳ / ממוצע", num(mo["vol_ratio"]))
            k[4].metric("שינוי קונצנזוס", pct(r.rev_change, 1, True))
            k[5].metric("שווי בסיס", price(r.val.get("mid")))
            if mo["alerts"]:
                for a in mo["alerts"]:
                    show_alert(f"⚑ <b>{a['k']}</b> · {a['he']} — {a['d']}")
            else:
                show_alert("✓ אין התראות פעילות", "ok")
            d = mo["df"]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=d.index, y=d["close"], name="מחיר", line=dict(color=C["s1"], width=2)))
            fig.add_trace(go.Scatter(x=d.index, y=d["sma20"], name="ממוצע 20", line=dict(color=C["s2"], width=2)))
            fig.add_trace(go.Scatter(x=d.index, y=d["sma50"], name="ממוצע 50", line=dict(color=C["s3"], width=2)))
            st.plotly_chart(fig_base(fig, 280, f"מחיר וממוצעים — {mo['source']}"), use_container_width=True)


# =================================================================== 5. RISK
def page_risk() -> None:
    st.header("מודיעין סיכונים ו-Risk Override")
    if not need_results():
        return
    rs = results()
    st.dataframe(pd.DataFrame([{"Company": r.cd.name, "ציון סיכון": r.r["score"], "דילול שנתי": v(r.m["dilution_rate"]), "SBC/הכנסות": v(r.m["sbc_pct"]),
                                "דגלים": len(r.cd.flags), "Risk Override": ("⛔ פסילה" if r.r["override"]["level"] == "disqualify" else "⤓ הגבלה") + " — " +
                                r.r["override"]["reason"].replace("Risk Override: ", "") if r.r["override"] else "—",
                                "הערכה": r.fin["cls"], "מקורות שנבדקו": ", ".join(r.r["checked"])} for r in sorted(rs, key=lambda x: -x.r["score"])]),
                 hide_index=True, use_container_width=True,
                 column_config={"ציון סיכון": score_cfg("ציון סיכון", True), "דילול שנתי": st.column_config.NumberColumn(format="percent"),
                                "SBC/הכנסות": st.column_config.NumberColumn(format="percent")})
    st.subheader("דגלים אדומים — הגשות רשמיות וחדשות")
    f1, f2 = st.columns(2)
    only_new = f1.checkbox("חדשים בלבד (לא ידועים לשוק)")
    min_sev = f2.select_slider("חומרה מינימלית", options=[1, 2, 3, 4], value=1, format_func=lambda x: SEV[x])
    fl = [(r, f) for r in rs for f in r.cd.flags if f.severity >= min_sev and (not only_new or not f.known)]
    fl.sort(key=lambda x: (-x[1].severity, x[1].date), reverse=False)
    if fl:
        st.dataframe(pd.DataFrame([{"Company": r.cd.name, "קטגוריה": f.category, "תיאור": f.title, "תאריך": f.date, "סטטוס": f.status,
                                    "חומרה": SEV[f.severity], "השפעה אפשרית": f.impact, "חדש/ידוע": "ידוע לשוק" if f.known else "חדש",
                                    "מקור": f.source, "קישור": f.url} for r, f in fl]), hide_index=True, use_container_width=True,
                     column_config={"קישור": st.column_config.LinkColumn("קישור", display_text="פתח מסמך")})
    else:
        st.info("לא נמצאו דגלים לפי המסננים.")
    st.caption("'מאומת' = אירוע שדווח בהגשה רשמית ל-SEC (8-K, NT 10-K וכו'). 'דיווח תקשורתי' = כותרת חדשות שזוהתה לפי מילות מפתח — טענה, לא עובדה. "
               "'ידוע לשוק' = פורסם לפני יותר מ-30 יום (הגשות) או 7 ימים (חדשות).")
    st.subheader("פעילות בעלי עניין (Form 4, 180 יום)")
    ins = [(r, t) for r in rs for t in r.cd.insiders if t.kind in ("sell", "buy", "tax")]
    if ins:
        thr = 5e6
        def interp(t):
            if t.kind == "buy":
                return "קנייה בשוק הפתוח — אות חיובי מתון"
            if t.plan == "10b5-1":
                return "מכירה מתוכננת מראש — משקל אינפורמטיבי נמוך"
            if t.plan == "tax":
                return "מכירה לכיסוי מס על הבשלת מניות — שגרתית"
            return "חריגה — מכירה גדולה מחוץ לתוכנית; מצדיקה בדיקה, לא בהכרח שלילית" if (t.value or 0) >= thr else "מכירה בשוק הפתוח"
        st.dataframe(pd.DataFrame([{"Company": r.cd.name, "תאריך": t.date, "שם": t.who, "תפקיד": t.role, "קוד": t.code,
                                    "מניות": t.shares, "מחיר": t.price, "שווי": t.value, "מסגרת": PLAN.get(t.plan, t.plan), "פרשנות": interp(t), "מקור": t.url}
                                   for r, t in sorted(ins, key=lambda x: x[1].date, reverse=True)]), hide_index=True, use_container_width=True,
                     column_config={"שווי": st.column_config.NumberColumn(format="compact"), "מחיר": st.column_config.NumberColumn(format="$%.2f"),
                                    "מקור": st.column_config.LinkColumn("מקור", display_text="Form 4")})
    else:
        st.info("לא נמצאו עסקאות Form 4 בתקופה.")
    st.subheader("דילול מניות")
    st.dataframe(pd.DataFrame([{"Company": r.cd.name, "מניות במחזור": v(r.cd.f("shares_outstanding")), "לפני 3 שנים": v(r.cd.f("shares_outstanding_3y")),
                                "קצב שנתי": v(r.m["dilution_rate"]), "SBC": v(r.cd.f("sbc")), "אופציות פתוחות": v(r.cd.f("options_outstanding")),
                                "אג\"ח להמרה": v(r.cd.f("convertible_debt")), "יתרת Buyback": v(r.cd.f("buyback_remaining")),
                                "Shelf (S-3)": len(r.cd.dilution.get("shelf_filings", [])), "תשקיפי 424B (12ח׳)": len(r.cd.dilution.get("offering_filings", [])),
                                "הערכה": dilution_text(r)} for r in rs]), hide_index=True, use_container_width=True,
                 column_config={k: st.column_config.NumberColumn(format="compact") for k in ("מניות במחזור", "לפני 3 שנים", "SBC", "אופציות פתוחות", "אג\"ח להמרה", "יתרת Buyback")}
                 | {"קצב שנתי": st.column_config.NumberColumn(format="percent")})
    st.caption("Shelf = מסגרת קיימת בלבד. 424B = תשקיף משלים שמלווה הנפקה בפועל (כולל ATM) — יש לפתוח את המסמך כדי לאמת את סוג ההנפקה.")


# =================================================================== 6. ENTRY & EXIT
def _strat_table(title: str, desc: str, rows: list[dict]) -> None:
    st.markdown(f"#### {title}")
    st.caption(desc)
    if rows and rows[0].get("n", 0) < 8:
        show_alert("⚠ אין מספיק נתונים לחיזוי אמין: פחות משמונה אירועי דוח היסטוריים. התוצאות מוצגות לעיון בלבד.")
    st.dataframe(pd.DataFrame([{"חלון": r["label"], "אירועים": r.get("n", 0), "תשואה ממוצעת": r.get("avg"), "חציון": r.get("med"), "Win Rate": r.get("win"),
                                "Max Drawdown": r.get("max_dd"), "תנודתיות": r.get("vol"), "תשואה/סיכון": r.get("risk_adj"), "החזקה (ימי מסחר)": r.get("hold"),
                                "Downside (אחוזון 10)": r.get("p10"), "עודף על SPY": r.get("excess"), "רמת ביטחון": r.get("conf", NA)} for r in rows]),
                 hide_index=True, use_container_width=True,
                 column_config={k: st.column_config.NumberColumn(format="percent") for k in ("תשואה ממוצעת", "חציון", "Win Rate", "Max Drawdown", "תנודתיות",
                                                                                              "Downside (אחוזון 10)", "עודף על SPY")}
                 | {"תשואה/סיכון": st.column_config.NumberColumn(format="%.2f")})


def page_timing() -> None:
    st.header("חלונות כניסה ויציאה סביב דוחות")
    if not need_results():
        return
    ss = state()
    s, _, _ = resources()
    c1, c2 = st.columns([3, 2])
    with c1:
        r = select_company("t_sel")
    with c2:
        current = float(ss["cost_bps"] if ss["cost_bps"] is not None else s.get("backtest.cost_bps_per_side", 15))
        cost = st.number_input("עלויות עסקה לכל צד (bps: עמלה + Slippage + Spread)", 0.0, 200.0, current, 1.0)
        if cost != current:
            ss["cost_bps"] = cost
            recompute()
            r = by_ticker(ss["sel"])
    if not r:
        return
    t = r.t
    if not t.get("available"):
        show_alert(f"ניתוח חלונות ההחזקה אינו זמין: {t.get('why')}", "crit")
        return
    st.caption(f"מבוסס על {t['n']} הודעות תוצאות אמיתיות (8-K Item 2.02, שעת הקבלה ב-EDGAR) ומחירי {t['price_source']}. "
               f"יום 0 = המסחר הראשון שמשקף את התוצאות. עלויות {t['cost_bps']:g} bps לכל צד. "
               + ("עודף מחושב מול SPY לאותו חלון." if t["benchmark"] else "אין נתוני ייחוס (SPY) — העודף חסר."))
    show_alert("אין כאן תאריך מכירה מדויק או הבטחת רווח. אלו תצפיות היסטוריות, לא תחזית.")
    days = t["days"]
    avg, sd = np.array(t["avg_path"]), np.array(t["sd_path"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=days + days[::-1], y=list(avg + sd) + list((avg - sd)[::-1]), fill="toself", fillcolor="rgba(57,135,229,0.15)",
                             line=dict(width=0), name="±1σ", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=days, y=avg, name="מסלול ממוצע (%)", line=dict(color=C["s1"], width=2)))
    fig.update_xaxes(title="ימי מסחר ביחס לדוח")
    fig.update_yaxes(title="שינוי מצטבר מיום −30 (%)")
    st.plotly_chart(fig_base(fig, 320), use_container_width=True)
    _strat_table("Strategy A — Pre-Earnings Run-Up", "כניסה לפני הדוח ויציאה ביום המסחר שלפני התגובה (ללא חשיפה לאירוע).", t["A"])
    _strat_table("Strategy B — Earnings Event", "כניסה לפני הדוח והחזקה במהלך פרסום התוצאות.", t["B"])
    _strat_table("Strategy C — Post-Earnings Drift", "כניסה רק אחרי תגובה חיובית ביום התגובה, ובחינת המשך המומנטום.", t["C"])
    b = best_window(t)
    if t["n"] < 8:
        st.markdown(f"<p>קיימים רק {t['n']} דוחות עם נתוני מחיר — אין מספיק נתונים כדי להעדיף חלון כלשהו.</p>", unsafe_allow_html=True)
    elif b:
        st.markdown(f"<p>החלון עם יחס התשואה/סיכון ההיסטורי הגבוה ביותר: \"{b['label']}\" (ממוצע {pct(b['avg'], 2, True)}, Win Rate {pct(b['win'], 0)}, "
                    f"{b['n']} אירועים, רמת ביטחון {b['conf']}). זו תצפית עבר; ראה מסך אימות המודלים לבדיקה מחוץ למדגם.</p>", unsafe_allow_html=True)


# =================================================================== 7. WATCHLIST
def page_watch() -> None:
    st.header("רשימת מעקב והתראות")
    s, store, hub = resources()
    w = store.watch_list()
    c1, c2 = st.columns([2, 3])
    with c1:
        add = st.text_input("הוסף טיקר לרשימה").strip().upper()
        if st.button("הוסף") and add:
            r = by_ticker(add)
            base = r.snapshot_row() if r else {}
            store.watch_add(add, now_iso(), base)
            st.rerun()
    with c2:
        st.caption("חברות ברשימה נטענות בכל סריקה גם אם אינן בחלון הדוחות. התראה נוצרת כשציון משתנה ב-"
                   f"{s.get('alerts.score_change', 10)}+ נקודות, כשהסיווג משתנה, כשמופיע דגל חדש בחומרה גבוהה או התראת מומנטום. "
                   "לסריקות אוטומטיות והתראות ב-Telegram/דוא\"ל ראה README (python -m evi.monitor.scan).")
    if not w:
        st.info("הרשימה ריקה.")
        return
    rows = []
    for t, info in w.items():
        r = by_ticker(t)
        base = info["base"]
        if not r:
            rows.append({"Ticker": t, "נוספה": info["added"][:10], "סטטוס": "לא נטען בסריקה הנוכחית — הרץ סריקה"})
            continue
        cur = r.snapshot_row()
        def d(k):
            a, b = base.get(k), cur.get(k)
            return None if a is None or b is None else b - a
        alerts = [f"{he} {d(k):+.0f}" for k, he in (("health", "בריאות"), ("valuation", "תמחור"), ("earnings", "הזדמנות"), ("risk", "סיכון"))
                  if d(k) is not None and abs(d(k)) >= float(s.get("alerts.score_change", 10))]
        if base.get("cls_idx") is not None and base["cls_idx"] != cur["cls_idx"]:
            alerts.append(f"סיווג: {CLASSES[base['cls_idx']]} → {CLASSES[cur['cls_idx']]}")
        alerts += [a["k"] for a in r.mon.get("alerts", [])]
        rows.append({"Ticker": t, "Company": r.cd.name, "נוספה": info["added"][:10], "בריאות": cur["health"], "Δ בריאות": d("health"),
                     "תמחור": cur["valuation"], "Δ תמחור": d("valuation"), "הזדמנות": cur["earnings"], "סיכון": cur["risk"], "Δ סיכון": d("risk"),
                     "הערכה": r.fin["cls"], "דוח הבא": _date_cell(r), "התראות": " · ".join(alerts) or "—"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"בריאות": score_cfg("בריאות"), "תמחור": score_cfg("תמחור"), "הזדמנות": score_cfg("הזדמנות"), "סיכון": score_cfg("סיכון", True)})
    c1, c2 = st.columns(2)
    with c1:
        t = st.selectbox("פעולה על", list(w))
        a, b = st.columns(2)
        if a.button("אפס בסיס להשוואה") and by_ticker(t):
            store.watch_add(t, now_iso(), by_ticker(t).snapshot_row())
            st.rerun()
        if b.button("הסר מהרשימה"):
            store.watch_remove(t)
            st.rerun()
    with c2:
        al = store.alerts_recent(50)
        st.markdown("**היסטוריית התראות (סריקות מתוזמנות)**")
        st.dataframe(pd.DataFrame(al) if al else pd.DataFrame({"הודעה": ["אין עדיין"]}), hide_index=True, use_container_width=True)


# =================================================================== 8. COMPANY REPORT
def page_report() -> None:
    st.header("דוח מחקר")
    if not need_results():
        return
    s, store, _ = resources()
    r = select_company("r_sel")
    if not r:
        return
    cd, m, val = r.cd, r.m, r.val
    st.markdown(f"### {cd.name} <span class='evi-en evi-src'>{cd.ticker} · {cd.exchange or ''} · {cd.sector or 'סקטור לא מסווג'}</span>", unsafe_allow_html=True)
    k = st.columns(6)
    k[0].markdown(f"הערכה סופית<br>{cls_badge(r.fin)}", unsafe_allow_html=True)
    k[1].metric("בריאות", score(r.h.score))
    k[2].metric("תמחור", score(val.get("score")))
    k[3].metric("הזדמנות דוח", score(r.e.score))
    k[4].metric("סיכון", score(r.r["score"]))
    ne = cd.next_earnings or {}
    k[5].metric("דוח הבא", ne.get("date") or NA, DATE_STATUS.get(ne.get("status"), ""), delta_color="off")
    watch = store.watch_list()
    b1, b2, b3, b4 = st.columns(4)
    if b1.button("★ הסר ממעקב" if cd.ticker in watch else "☆ הוסף למעקב"):
        store.watch_remove(cd.ticker) if cd.ticker in watch else store.watch_add(cd.ticker, now_iso(), r.snapshot_row())
        st.rerun()
    pdf = export.report_pdf(r)
    if pdf:
        b2.download_button("ייצוא PDF", pdf, f"EVI_{cd.ticker}_report.pdf", "application/pdf")
    else:
        b2.caption("PDF: לא נמצא גופן עברי במערכת — השתמש בייצוא HTML והדפס ל-PDF")
    b3.download_button("ייצוא HTML", export.report_html(r).encode("utf-8"), f"EVI_{cd.ticker}_report.html", "text/html")
    b4.download_button("ייצוא Excel", export.company_xlsx(r), f"EVI_{cd.ticker}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.markdown('<div class="evi-banner">הסקירה נוצרת אוטומטית מנתונים אמיתיים ומחישובי מודל. אינה ייעוץ השקעות ואינה המלצה לקנייה או למכירה. '
                'כל נתון חסר מצוין במפורש.</div>', unsafe_allow_html=True)
    with st.expander("הזנות ידניות של החוקר (נשמרות מקומית ומסומנות כהזנה ידנית)"):
        with st.form(f"manual_{cd.ticker}"):
            cdate = st.text_input("תאריך דוח מאושר (YYYY-MM-DD) — לפי הודעת החברה", cd.manual.get("confirmed_date", ""))
            g_opts = ["", "raised", "maintained", "lowered"]
            g = st.selectbox("תחזית הנהלה אחרונה", g_opts, index=g_opts.index(cd.manual.get("guidance", "")),
                             format_func=lambda x: {"": "לא ידוע", "raised": "הועלתה", "maintained": "נשמרה", "lowered": "הורדה"}[x])
            moat = st.text_area("מוצרים ויתרון תחרותי (הערת חוקר)", cd.manual.get("moat", ""))
            if st.form_submit_button("שמור"):
                ok_date = True
                if cdate:
                    try:
                        date.fromisoformat(cdate)
                    except ValueError:
                        ok_date = False
                        st.error("פורמט תאריך לא תקין")
                if ok_date:
                    for key, val_ in (("confirmed_date", cdate), ("guidance", g), ("moat", moat)):
                        store.manual_set(cd.ticker, key, val_, now_iso())
                    cd.manual = store.manual_get(cd.ticker)
                    if cdate:
                        cd.next_earnings = {**cd.next_earnings, "date": cdate, "status": "confirmed_manual", "source": "אושר ידנית ע\"י המשתמש"}
                    recompute()
                    st.rerun()
    st.markdown('<div class="evi-report">', unsafe_allow_html=True)
    for h, en, text in sections(r):
        st.markdown(f"#### {h} <span class='evi-src evi-en'>{en}</span> {lyr('AI')}", unsafe_allow_html=True)
        st.markdown(f"<p>{text}</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("מודל DCF ורגישות")
    a = r.a
    if a is None:
        show_alert(val.get("dcf_missing") or "אין מספיק נתוני צמיחה להגדרת הנחות DCF", "crit")
    else:
        c1, c2 = st.columns(2)
        with c1:
            with st.form(f"dcf_{cd.ticker}"):
                g1 = st.slider("צמיחת הכנסות שנה 1", -0.10, 0.50, float(round(a.g1, 3)), 0.005, format="%.3f")
                gT = st.slider("צמיחה טרמינלית", 0.0, 0.04, float(a.gT), 0.0025, format="%.4f")
                wacc = st.slider("שיעור היוון (WACC)", 0.06, 0.16, float(round(a.wacc, 4)), 0.0025, format="%.4f")
                mt = st.slider("מרווח FCF יעד (שנה 5)", -0.05, 0.50, float(round(a.m_target, 3)), 0.005, format="%.3f")
                adj = st.checkbox("ניכוי SBC מה-FCF (שמרני)", a.use_adj)
                x1, x2 = st.columns(2)
                if x1.form_submit_button("עדכן מודל"):
                    set_override(cd.ticker, Assumptions(g1, gT, wacc, mt, adj, a.years))
                    st.rerun()
                if x2.form_submit_button("החזר לברירת מחדל"):
                    set_override(cd.ticker, None)
                    st.rerun()
            if val.get("mid") is not None:
                st.dataframe(pd.DataFrame([["שווי — שמרני", price(val["low"])], ["שווי — בסיס", price(val["mid"])], ["שווי — אופטימי", price(val["high"])],
                                           ["מחיר שוק", price(cd.price)], ["Margin of Safety", pct(val.get("mos"), 0)], ["אפסייד לבסיס", pct(val.get("upside"), 0, True)],
                                           ["דאונסייד לתרחיש שמרני", pct(val.get("downside_cons"), 0, True)], ["חלק הערך הטרמינלי", pct(val["base"].get("tv_share"), 0)],
                                           ["מניות בדילול מלא", f"{v(cd.f('diluted_shares')) / 1e6:,.1f}M"]], columns=["", "ערך"]), hide_index=True, use_container_width=True)
                st.caption(val.get("reliability_note", "") + " שמרני: צמיחה ×0.6, מרווח −3pp, WACC +1pp · אופטימי: צמיחה ×1.25, מרווח +3pp, WACC −0.75pp.")
            else:
                show_alert(val.get("dcf_missing", "DCF לא חושב"), "crit")
        with c2:
            if val.get("grid"):
                g = val["grid"]
                px_ = v(cd.price)
                grid = pd.DataFrame(g["cells"], index=[f"{w:.2%}" for w in g["waccs"]], columns=[f"g={x:.1%}" for x in g["gts"]])
                st.markdown("**רגישות השווי למניה: WACC (שורות) × צמיחה טרמינלית (עמודות)**")
                def color(xv):
                    if xv is None or px_ is None or (isinstance(xv, float) and math.isnan(xv)):
                        return ""
                    rr = xv / px_ - 1
                    a_ = min(abs(rr), 1) * 0.45
                    return f"background-color: rgba(57,135,229,{a_})" if rr >= 0 else f"background-color: rgba(217,89,38,{a_})"
                st.dataframe(grid.style.format("${:,.2f}", na_rep=NA).map(color), use_container_width=True)
                st.caption("כחול = מעל מחיר השוק, כתום = מתחת. עוצמה לפי גודל הפער." if px_ else "אין מחיר שוק להשוואה.")
            st.markdown("**מכפילים יחסיים**")
            hr = {x["k"]: x for x in val.get("hist_rel", [])}
            st.dataframe(pd.DataFrame([{"מכפיל": x["label"], "חברה": mult(x["own"]), "חציון עמיתים בסריקה": mult(x["peer"]), "מס׳ עמיתים": x["n_peers"],
                                        "ממוצע היסטורי של החברה": mult(hr[x["k"]]["hist"]) if x["k"] in hr else "—"} for x in val.get("rel", [])]),
                         hide_index=True, use_container_width=True)
            if val.get("hist", {}).get("note"):
                st.caption("מכפילים היסטוריים: " + val["hist"]["note"])
    st.subheader("הכנסות ותזרים (שנים פיסקליות, SEC XBRL)")
    ann = cd.annual.get("revenue", [])[-6:]
    if ann:
        ocf = {x["end"]: x["val"] for x in cd.annual.get("ocf", [])}
        cap = {x["end"]: x["val"] for x in cd.annual.get("capex", [])}
        fig = go.Figure()
        fig.add_trace(go.Bar(x=[x["end"][:4] for x in ann], y=[x["val"] for x in ann], name="הכנסות", marker_color=C["s1"]))
        fig.add_trace(go.Bar(x=[x["end"][:4] for x in ann], y=[(ocf[x["end"]] - cap[x["end"]]) if x["end"] in ocf and x["end"] in cap else None for x in ann],
                             name="FCF", marker_color=C["s2"]))
        st.plotly_chart(fig_base(fig, 280), use_container_width=True)
    else:
        st.markdown("<span class='evi-miss'>אין הכנסות שנתיות ב-XBRL.</span>", unsafe_allow_html=True)
    st.subheader("מקורות, תאריכי עדכון ונתונים חסרים")
    st.dataframe(pd.DataFrame([{"קבוצת נתונים": k, "מקור ועדכון": s_} for k, s_ in cd.sources_used.items()]
                              + [{"קבוצת נתונים": "מחיר עדכני", "מקור ועדכון": f"{cd.price.source or NA} · {cd.price.as_of or ''}"},
                                 {"קבוצת נתונים": "מועד דוח", "מקור ועדכון": f"{ne.get('source') or NA} · {DATE_STATUS.get(ne.get('status'), '')} {ne.get('basis', '')}"}]),
                 hide_index=True, use_container_width=True)
    if cd.gaps:
        st.markdown("**נתונים חסרים:** " + " · ".join(cd.gaps))
    if cd.errors:
        with st.expander("שגיאות טעינה"):
            for e in cd.errors:
                st.text(e)


# =================================================================== 9. VALIDATION
def page_validation() -> None:
    st.header("אימות מודלים — Backtesting & Walk-Forward")
    if not need_results():
        return
    s, _, _ = resources()
    ss = state()
    cost = ss["cost_bps"] if ss["cost_bps"] is not None else float(s.get("backtest.cost_bps_per_side", 15))
    wf = walk_forward(results(), ss["bench"], cost)
    if not wf.get("available"):
        show_alert(wf.get("why", ""), "crit")
        return
    st.caption(f"{wf['n']} אירועי דוח אמיתיים מכל החברות שנסרקו. מחוץ למדגם (OOS) = 30% האירועים המאוחרים ביותר, החל מ-{wf['split_date']}. "
               "כל החלטה משתמשת רק באירועים שקדמו לה (Walk-Forward).")
    for key, rule in wf["rules"].items():
        st.subheader(rule["name"])
        st.dataframe(pd.DataFrame([{"מדגם": name, "אירועים": x.get("n_all"), "אותות": x.get("n_sig"), "ייחוס (כל האירועים)": x.get("base"),
                                    "אות": x.get("sig"), "יתרון": x.get("edge"), "t": x.get("t"), "עודף על SPY (אות)": x.get("excess")}
                                   for name, x in (("In-Sample", rule["ins"]), ("Out-of-Sample", rule["oos"]))]), hide_index=True, use_container_width=True,
                     column_config={k: st.column_config.NumberColumn(format="percent") for k in ("ייחוס (כל האירועים)", "אות", "יתרון", "עודף על SPY (אות)")}
                     | {"t": st.column_config.NumberColumn(format="%.2f")})
        ok_ = (rule["oos"].get("t") or 0) >= 2 and (rule["oos"].get("edge") or 0) > 0
        show_alert(f"<b>מסקנה:</b> {rule['verdict']}", "ok" if ok_ else "crit")
        tabs = st.tabs(["לפי סקטור", "לפי גודל חברה", "לפי תנודתיות", "לפי מצב שוק"])
        for tab, g in zip(tabs, ("sector", "cap", "vol", "regime")):
            with tab:
                st.dataframe(pd.DataFrame([{"קבוצה": x["k"], "אירועים": x.get("n_all"), "אותות": x.get("n_sig"), "ייחוס": x.get("base"), "אות": x.get("sig"),
                                            "יתרון": x.get("edge"), "t": x.get("t")} for x in rule["groups"][g]]), hide_index=True, use_container_width=True,
                             column_config={k: st.column_config.NumberColumn(format="percent") for k in ("ייחוס", "אות", "יתרון")})
    st.subheader("מגבלות ידועות")
    for l in wf["limitations"]:
        st.markdown(f"- {l}")


# =================================================================== 10. METHODOLOGY & DATA
def page_method() -> None:
    st.header("נתונים, מקורות ומתודולוגיה")
    s, store, hub = resources()
    st.subheader("מצב ספקי הנתונים")
    st.dataframe(pd.DataFrame([{"קבוצת נתונים": p["group"], "ספק": p["provider"], "פעיל": "✓" if p["active"] else "✗", "הערה": p["note"]}
                               for p in hub.provider_status()]), hide_index=True, use_container_width=True)
    ls = store.last_scan()
    if ls:
        st.caption(f"סריקה אחרונה: {ls['ts']} · {ls['n']} חברות · {ls['duration']:.0f} שניות")
        if ls["errors"]:
            with st.expander(f"שגיאות בסריקה האחרונה ({len(ls['errors'])})"):
                st.text("\n".join(ls["errors"]))
    st.subheader("ארבע שכבות מידע")
    st.markdown(f"""
{lyr('RAW')} **נתונים גולמיים** — כפי שהתקבלו מהספק, עם מקור (כולל תג XBRL) ותאריך התקופה.<br>
{lyr('CALC')} **חישובים** — יחסים ומכפילים דטרמיניסטיים. חסר קלט → חסר פלט.<br>
{lyr('MODEL')} **הערכות מודל** — ציונים, DCF, Backtest; תלויים בהנחות המפורטות.<br>
{lyr('AI')} **פרשנות** — טקסט הסקירה, נגזר מהשכבות שמעליו ואינו מוסיף נתונים.""", unsafe_allow_html=True)
    st.subheader("כללי נתונים חסרים")
    st.markdown("""
- ערך שלא נמצא בספק נשאר **חסר** — לעולם אינו מוחלף בנתון הדגמה, בממוצע או באפס.
- חריג אחד, מסומן בהערה: כשחברה מדווחת מזומן אך אין לה תג XBRL של השקעות קצרות/חוב, אלה נחשבים 0 (פרקטיקת דיווח: רכיב שלא קיים לא מתויג).
- ציון מחושב רק מעל סף כיסוי (בריאות 60%, הזדמנות דוח 50%); רכיבים חסרים מוצאים והמשקל מנורמל.
- חברה ללא ציון בריאות או תמחור מסווגת "לא ניתן להעריך — נתונים חסרים".""")
    st.subheader("נוסחאות")
    st.dataframe(pd.DataFrame([
        ["ציון בריאות", "איתנות מאזן 20 · נזילות 15 · רווחיות 20 · איכות תזרים בניכוי SBC 20 · יציבות הכנסות 10 · יכולת פירעון 15"],
        ["ציון תמחור", "50% MoS מול DCF בסיס · 25% הנחה מול חציון עמיתים בסריקה (≥3) · 25% הנחה מול מכפילים היסטוריים; מופחת כשהצמיחה <3% או דגל מבני"],
        ["ציון הזדמנות דוח", "עקיפות 25 · גודל הפתעה 10 · עדכוני קונצנזוס 20 · תחזית הנהלה 10 · ציפיות לא מתומחרות 15 · תגובות עבר 10 · הערכה מחודשת 10"],
        ["ציון סיכון", "דגלים (חומרה × סטטוס × חדשות) + דילול + Shelf/424B + מכירות חריגות + פער בריאות + תנודתיות"],
        ["Risk Override", "דגל קריטי מאומת או סיכון מעל 70 ← פסילה · סיכון פיננסי חמור או אירוע חדש בחומרה גבוהה ← הגבלה ל'מועמדת למעקב'"],
        ["הערכה סופית", "בריאות <45 ← לא עומדת בסינון · משוקלל ≥65 + MoS ≥15% + סיכון <50 ← עדיפות גבוהה · משוקלל ≥55 ותמחור ≥40 ← מעקב · Value Trap מגביל"],
        ["DCF", "הכנסות TTM × צמיחה דועכת ל-10 שנים; מרווח FCF מתכנס ליעד בשנה 5; ערך טרמינלי גורדון; חוב נטו מנוכה; מניות בדילול מלא"],
    ], columns=["מודל", "הגדרה"]), hide_index=True, use_container_width=True)
    st.caption("כל המשקלות והספים ניתנים לשינוי ב-config.yaml. הם הנחות עבודה ולא תוצאה של אופטימיזציה; יש לכייל אותם רק בתהליך Walk-Forward.")
    if st.button("נקה מטמון נתונים (יאלץ הורדה מחדש)"):
        store.cache_clear()
        st.success("המטמון נוקה.")
