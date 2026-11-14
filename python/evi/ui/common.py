"""Shared Streamlit helpers: state, styling, provenance rendering, charts."""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..analytics.pipeline import Result, analyze_all
from ..analytics.valuation import Assumptions
from ..config import load_settings
from ..fmt import NA
from ..models import Val
from ..providers.router import DataHub
from ..store import get_store

C = {"s1": "#3987e5", "s2": "#d95926", "s3": "#199e70", "good": "#0ca30c", "warn": "#fab219", "serious": "#ec835a", "crit": "#d03b3b",
     "grid": "#2a2b2e", "ink2": "#a9a8a0", "bg": "#111214"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, label, p, li { font-family: Heebo, sans-serif; }
[data-testid="stAppViewContainer"], [data-testid="stSidebar"], [data-testid="stHeader"] { direction: rtl; }
[data-testid="stSidebar"] * { text-align: right; }
[data-testid="stDataFrame"], .js-plotly-plot, [data-testid="stMetricValue"], code { direction: ltr; }
.evi-num { font-family: 'IBM Plex Mono', monospace; direction: ltr; unicode-bidi: isolate; }
.evi-en { direction: ltr; unicode-bidi: isolate; }
.evi-banner { background: #1d1a10; border: 1px solid #6b5414; color: #ffd99a; padding: 6px 12px; border-radius: 4px; font-size: 13px; margin-bottom: 8px; }
.evi-crit { background: #220d0d; border: 1px solid #7a2a2a; color: #ffb0b0; padding: 8px 12px; border-radius: 4px; margin: 6px 0; }
.evi-warn { background: #1f1905; border: 1px solid #6b5414; color: #ffd99a; padding: 8px 12px; border-radius: 4px; margin: 6px 0; }
.evi-ok { background: #0e1d0e; border: 1px solid #2e6b2e; color: #9fdc9f; padding: 8px 12px; border-radius: 4px; margin: 6px 0; }
.evi-miss { color: #8a8984; font-style: italic; }
.evi-lyr { display:inline-block; font: 600 10px 'IBM Plex Mono', monospace; padding: 0 5px; border-radius: 2px; border: 1px solid; margin-inline-end: 4px; }
.evi-RAW { color:#9ec5f4; border-color:#256abf } .evi-CALC { color:#8fe0bf; border-color:#199e70 }
.evi-MODEL { color:#ffc58f; border-color:#a0521f } .evi-AI { color:#c9c1ff; border-color:#6250d6 }
.evi-cls { display:inline-block; padding:3px 10px; border-radius:3px; border:1px solid; font-weight:500 }
.evi-cls0 { color:#7fd17f; border-color:#2e6b2e; background:#102410 } .evi-cls1 { color:#ffd27a; border-color:#6b5414; background:#231c06 }
.evi-cls2 { color:#a9a8a0; border-color:#44454a; background:#1a1b1e } .evi-cls3 { color:#ff8b8b; border-color:#7a2a2a; background:#2a1010 }
.evi-cls4 { color:#a9a8a0; border-color:#44454a; background:#1a1b1e; border-style: dashed }
.evi-report p { line-height: 1.8; max-width: 920px; }
.evi-src { color:#76756f; font-size: 12px; }
</style>
"""


def setup_page() -> None:
    st.set_page_config(page_title="Earnings Value Intelligence", page_icon="📈", layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource
def resources() -> tuple[Any, Any, DataHub]:
    s = load_settings()
    store = get_store()
    return s, store, DataHub(s, store)


def state() -> dict:
    ss = st.session_state
    ss.setdefault("cds", [])
    ss.setdefault("results", [])
    ss.setdefault("notes", [])
    ss.setdefault("scan_ts", None)
    ss.setdefault("bench", None)
    ss.setdefault("overrides", {})
    ss.setdefault("cost_bps", None)
    ss.setdefault("sel", None)
    return ss


def recompute() -> None:
    s, _, _ = resources()
    ss = state()
    ss["results"] = analyze_all(ss["cds"], s, ss["bench"], ss["overrides"], ss["cost_bps"])


def results() -> list[Result]:
    return state()["results"]


def by_ticker(t: str | None) -> Result | None:
    return next((r for r in results() if r.ticker == t), None)


def select_company(key: str, label: str = "חברה") -> Result | None:
    rs = results()
    if not rs:
        return None
    tickers = [r.ticker for r in rs]
    ss = state()
    cur = ss["sel"] if ss["sel"] in tickers else tickers[0]
    names = {r.ticker: f"{r.cd.name} ({r.ticker})" for r in rs}
    t = st.selectbox(label, tickers, index=tickers.index(cur), format_func=lambda x: names[x], key=key)
    ss["sel"] = t
    return by_ticker(t)


def need_results() -> bool:
    if not results():
        st.info("עדיין לא בוצעה סריקה. הגדר חלון זמן וסקטורים בסרגל הצד ולחץ \"הרץ סריקה\", או טען חברה בודדת לפי טיקר.")
        return False
    return True


# ------------------------------------------------------------------ rendering helpers
def lyr(layer: str) -> str:
    return f'<span class="evi-lyr evi-{layer}">{layer}</span>'


def cls_badge(fin: dict) -> str:
    return f'<span class="evi-cls evi-cls{fin["idx"]}">{fin["cls"]}{" ⤓" if fin.get("capped") else ""}</span>'


def val_rows(d: dict[str, Val], labels: dict[str, str], fmt) -> pd.DataFrame:
    rows = []
    for k, lab in labels.items():
        x = d.get(k)
        if not isinstance(x, Val):
            continue
        rows.append({"שדה": lab, "ערך": fmt(k, x) if x.ok else NA, "שכבה": x.layer, "מקור": x.source or "—",
                     "נכון ל": x.as_of or "—", "הערה": x.note})
    return pd.DataFrame(rows)


def fig_base(fig: go.Figure, height: int = 320, title: str | None = None) -> go.Figure:
    fig.update_layout(template="plotly_dark", height=height, margin=dict(l=40, r=20, t=40 if title else 20, b=30),
                      paper_bgcolor=C["bg"], plot_bgcolor=C["bg"], font=dict(family="Heebo", color="#ecebe6"),
                      title=title, legend=dict(orientation="h", y=1.08, x=1, xanchor="right"), hovermode="x unified")
    fig.update_xaxes(gridcolor=C["grid"])
    fig.update_yaxes(gridcolor=C["grid"])
    return fig


def show_alert(text: str, kind: str = "warn") -> None:
    st.markdown(f'<div class="evi-{kind}">{text}</div>', unsafe_allow_html=True)


def score_cfg(label: str, invert: bool = False):
    help_ = "0–100; גבוה = סיכון גבוה" if invert else "0–100; גבוה = טוב"
    return st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%.0f", help=help_)


def set_override(t: str, a: Assumptions | None) -> None:
    ss = state()
    if a is None:
        ss["overrides"].pop(t, None)
    else:
        ss["overrides"][t] = a
    recompute()
