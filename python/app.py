"""Earnings Value Intelligence — Streamlit entry point.

Run:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from evi.analytics.pipeline import run_scan
from evi.sectors import SECTORS
from evi.ui import pages
from evi.ui.common import recompute, resources, setup_page, state

setup_page()
settings, store, hub = resources()
ss = state()

PAGES = {
    "סורק שוק · Market Scanner": pages.page_scanner,
    "איכות פיננסית · Financial Quality": pages.page_quality,
    "תמחור חסר · Undervalued Stocks": pages.page_value,
    "דוחות קרובים · Upcoming Earnings": pages.page_earnings,
    "מודיעין סיכונים · Risk Intelligence": pages.page_risk,
    "כניסה ויציאה · Entry & Exit": pages.page_timing,
    "רשימת מעקב · Watchlist": pages.page_watch,
    "דוח מחקר · Company Report": pages.page_report,
    "אימות מודלים · Validation": pages.page_validation,
    "נתונים ומתודולוגיה · Data & Methods": pages.page_method,
}

with st.sidebar:
    st.markdown("## EVI\n**Earnings Value Intelligence**")
    if not hub.edgar:
        st.error("חסר SEC_USER_AGENT בקובץ .env — ראה README.")
    status = hub.provider_status()
    st.caption(" · ".join(("✓ " if p["active"] else "✗ ") + p["provider"].split(" ")[0] for p in status))
    page = st.radio("מסך", list(PAGES), label_visibility="collapsed")
    st.divider()
    st.markdown("**סריקה**")
    dmin, dmax = st.slider("ימים עד הדוח", 0, 90, (int(settings.get("scan.days_min", 7)), int(settings.get("scan.days_max", 30))))
    secs = st.multiselect("סקטורים (ריק = כולם)", SECTORS)
    recent = st.checkbox("כלול חברות שדיווחו ב-10 הימים האחרונים", True)
    st.caption(f"מצב: {'לוח דוחות Finnhub' if hub.mode() == 'calendar' else 'רשימת מניות (data/universe.csv)'}")
    if st.button("הרץ סריקה", type="primary", disabled=hub.edgar is None, use_container_width=True):
        bar = st.progress(0.0, "מתחיל…")
        out = run_scan(hub, store, settings, dmin, dmax, set(secs) or None, recent, lambda f, msg: bar.progress(min(f, 1.0), msg),
                       ss["overrides"], extra_tickers=list(store.watch_list()))
        ss["cds"] = [r.cd for r in out["results"]]
        ss["results"], ss["notes"], ss["scan_ts"], ss["bench"] = out["results"], out["notes"], out["ts"], out["bench"]
        ss["dmin"], ss["dmax"] = dmin, dmax
        bar.empty()
        if out["errors"]:
            st.warning(f"{len(out['errors'])} שגיאות טעינה — פירוט במסך 'נתונים ומתודולוגיה'.")
    st.divider()
    one = st.text_input("טען חברה בודדת (טיקר)").strip().upper()
    if st.button("טען", disabled=hub.edgar is None) and one:
        with st.spinner(f"טוען {one} מ-SEC…"):
            cd = hub.load(one)
        if cd.cik is None:
            st.error(f"{one}: {'; '.join(cd.errors) or 'לא נמצא'}")
        else:
            cd.manual["_watch_only"] = True  # always visible in the scanner, regardless of the date window
            ss["cds"] = [c for c in ss["cds"] if c.ticker != one] + [cd]
            if ss["bench"] is None:
                ss["bench"] = hub.benchmark()
            recompute()
            ss["sel"] = one
            st.success(f"{cd.name} נטענה — פתח 'דוח מחקר'.")
    if ss["scan_ts"]:
        st.caption(f"סריקה אחרונה: {ss['scan_ts']}")

PAGES[page]()
