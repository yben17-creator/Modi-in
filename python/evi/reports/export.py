"""Exports: Excel (scanner + company), standalone HTML report, PDF report (Hebrew, RTL)."""
from __future__ import annotations

import html
import io
import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..analytics.pipeline import Result
from ..fmt import DATE_STATUS, money, pct, price, score
from ..models import Val, v
from .hebrew import sections

DISCLAIMER = "נתונים מ-SEC EDGAR ומספקים נוספים כמפורט. אינו ייעוץ השקעות. ערכים חסרים מסומנים 'חסר' ולא הושלמו."


def scanner_frame(results: list[Result]) -> pd.DataFrame:
    rows = []
    for r in results:
        cd, m, ne = r.cd, r.m, r.cd.next_earnings or {}
        rows.append({
            "Company": cd.name, "Ticker": cd.ticker, "Exchange": cd.exchange, "Sector": cd.sector,
            "Price": v(cd.price), "Price Source": cd.price.source, "Price As Of": cd.price.as_of,
            "Market Cap": v(m["mcap"]), "Enterprise Value": v(m["ev"]),
            "Next Earnings": ne.get("date"), "Date Status": DATE_STATUS.get(ne.get("status"), ne.get("status")), "Date Source": ne.get("source"),
            "Days Until": v(m["days_to_earnings"]),
            "Revenue (TTM)": v(m["revenue"]), "Revenue As Of": m["revenue"].as_of, "Net Income (TTM)": v(cd.f("net_income")),
            "FCF (TTM)": v(m["fcf"]), "FCF after SBC": v(m["adj_fcf"]),
            "Health Score": r.h.score, "Valuation Score": r.val.get("score"), "Earnings Score": r.e.score, "Risk Score": r.r["score"],
            "FV Low": r.val.get("low"), "FV Base": r.val.get("mid"), "FV High": r.val.get("high"), "Margin of Safety": r.val.get("mos"),
            "Assessment": r.fin["cls"], "Financials Source": cd.sources_used.get("דוחות כספיים (XBRL)", "חסר"),
        })
    return pd.DataFrame(rows)


def scanner_xlsx(results: list[Result]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        scanner_frame(results).to_excel(xw, sheet_name="Scanner", index=False)
        pd.DataFrame({"Note": [DISCLAIMER, "Missing values are left blank — never filled."]}).to_excel(xw, sheet_name="About", index=False)
    return buf.getvalue()


def company_xlsx(r: Result) -> bytes:
    buf = io.BytesIO()
    def vrows(d: dict[str, Val]) -> pd.DataFrame:
        return pd.DataFrame([{"Field": k, "Value": x.value if isinstance(x, Val) else x, "Layer": getattr(x, "layer", ""), "Source": getattr(x, "source", ""),
                              "As Of": getattr(x, "as_of", ""), "Note": getattr(x, "note", "")} for k, x in d.items()])
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        scanner_frame([r]).to_excel(xw, sheet_name="Summary", index=False)
        vrows(r.cd.fin).to_excel(xw, sheet_name="Raw (XBRL)", index=False)
        vrows(r.m).to_excel(xw, sheet_name="Calculations", index=False)
        if r.val.get("base"):
            pd.DataFrame(r.val["base"]["rows"]).to_excel(xw, sheet_name="DCF Base", index=False)
            pd.DataFrame([{"Scenario": k, **s} for k, s in r.val["scenarios"].items()]).to_excel(xw, sheet_name="DCF Assumptions", index=False)
        if r.t.get("available"):
            pd.DataFrame(r.t["A"] + r.t["B"] + r.t["C"]).to_excel(xw, sheet_name="Timing", index=False)
            pd.DataFrame(r.t["events"]).drop(columns=["i0"]).to_excel(xw, sheet_name="Earnings Events", index=False)
        pd.DataFrame([f.__dict__ for f in r.cd.flags]).to_excel(xw, sheet_name="Red Flags", index=False)
        pd.DataFrame([t.__dict__ for t in r.cd.insiders]).to_excel(xw, sheet_name="Insiders", index=False)
        pd.DataFrame([{"Group": k, "Source": s} for k, s in r.cd.sources_used.items()] + [{"Group": "Gap", "Source": g} for g in r.cd.gaps]).to_excel(xw, sheet_name="Sources & Gaps", index=False)
    return buf.getvalue()


def report_html(r: Result) -> str:
    secs = sections(r)
    body = "".join(f"<h2>{h} <small>{en}</small></h2><p>{t}</p>" for h, en, t in secs)
    src = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(s)}</td></tr>" for k, s in r.cd.sources_used.items())
    gaps = "".join(f"<li>{html.escape(g)}</li>" for g in r.cd.gaps) or "<li>—</li>"
    return f"""<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8"><title>{html.escape(r.cd.name)} — EVI</title>
<style>body{{font-family:Arial,Heebo,sans-serif;max-width:900px;margin:30px auto;line-height:1.7;color:#111}}h1{{margin-bottom:0}}
h2{{border-top:1px solid #ccc;padding-top:10px;font-size:18px}}h2 small{{color:#888;font-weight:normal}}table{{border-collapse:collapse}}td{{border:1px solid #ddd;padding:4px 8px}}
.k{{display:flex;gap:24px;margin:10px 0}}.d{{background:#fff8e1;padding:8px;border:1px solid #f0d78c}}</style></head><body>
<h1>{html.escape(r.cd.name)} ({r.cd.ticker})</h1><div>{r.cd.exchange or ''} · {r.cd.sector or ''}</div>
<div class="k"><div>הערכה: <b>{r.fin['cls']}</b></div><div>בריאות: {score(r.h.score)}</div><div>תמחור: {score(r.val.get('score'))}</div>
<div>הזדמנות דוח: {score(r.e.score)}</div><div>סיכון: {score(r.r['score'])}</div></div>
<div class="d">{DISCLAIMER}</div>{body}<h2>מקורות</h2><table>{src}</table><h2>נתונים חסרים</h2><ul>{gaps}</ul></body></html>"""


# ------------------------------------------------------------------ PDF
FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
    "/Library/Fonts/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/noto/NotoSansHebrew-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]
_HEB = re.compile(r"[\u0590-\u05FF]")


def rtl(text: str) -> str:
    """Visual reordering for PDF. Uses python-bidi when installed; otherwise a simple fallback."""
    try:
        from bidi.algorithm import get_display
        return get_display(text)
    except ImportError:
        pass
    if not _HEB.search(text):
        return text
    # fallback: reverse the order of runs; reverse characters inside Hebrew runs only
    tokens = re.findall(r"[\u0590-\u05FF]+|[^\u0590-\u05FF]+", text)
    out = []
    for tok in reversed(tokens):
        if _HEB.search(tok):
            out.append(tok[::-1])
        else:
            lead = re.match(r"^\s*", tok).group(0)
            trail = re.search(r"\s*$", tok).group(0)
            core = tok.strip()
            mirror = core.translate(str.maketrans("()[]{}<>", ")(][}{><"))
            out.append(trail + mirror + lead)
    return "".join(out)


def _font() -> str | None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                pdfmetrics.registerFont(TTFont("HebFont", p))
                return "HebFont"
            except Exception:
                continue
    return None


def _wrap(text: str, width: float, font: str, size: float) -> list[str]:
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if stringWidth(cand, font, size) <= width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def report_pdf(r: Result) -> bytes | None:
    """Returns PDF bytes, or None if no Hebrew-capable font was found (use HTML export instead)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    font = _font()
    if not font:
        return None
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    margin, y = 50, H - 50
    def line(t: str, size: float = 10.5, gap: float = 15) -> None:
        nonlocal y
        if y < 60:
            c.showPage()
            y = H - 50
        c.setFont(font, size)
        c.drawRightString(W - margin, y, rtl(t))
        y -= gap
    def para(t: str, size: float = 10.5) -> None:
        t = re.sub(r"<[^>]+>", "", t)
        for ln in _wrap(t, W - 2 * margin, font, size):
            line(ln, size)
        line("", gap=6)
    line(f"{r.cd.name} ({r.cd.ticker}) — Earnings Value Intelligence", 15, 22)
    line(f"הערכה: {r.fin['cls']} · בריאות {score(r.h.score)} · תמחור {score(r.val.get('score'))} · הזדמנות {score(r.e.score)} · סיכון {score(r.r['score'])}", 10, 16)
    para(DISCLAIMER, 9)
    for h, en, t in sections(r):
        line(f"{h} — {en}", 12.5, 18)
        para(t)
    line("מקורות", 12.5, 18)
    for k, s in r.cd.sources_used.items():
        para(f"{k}: {s}", 9)
    if r.cd.gaps:
        line("נתונים חסרים", 12.5, 18)
        for g in r.cd.gaps:
            para(g, 9)
    c.save()
    return buf.getvalue()
