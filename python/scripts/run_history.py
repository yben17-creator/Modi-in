"""Run EVI on real historical data and write a Hebrew validation report.

    python scripts/run_history.py --tickers MSFT NVDA CRWD --out out/

Needs SEC_USER_AGENT (always) and TIINGO_API_KEY (price history). No key → that data is reported missing, never faked.
Outputs: out/history_report.md (Hebrew), out/history_report.json (raw numbers).
What is tested:
  1. walk-forward of the earnings-timing rules (R1, R2) on real 8-K announcement times and real prices
  2. point-in-time study of the candlestick/volume signals and of the support floor
What is NOT tested yet (written into the report): fundamental scores point-in-time.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evi.analytics import candles  # noqa: E402
from evi.analytics.pipeline import analyze_all  # noqa: E402
from evi.config import load_settings  # noqa: E402
from evi.providers.router import DataHub  # noqa: E402
from evi.store import Store  # noqa: E402
from evi.validation.backtest import walk_forward  # noqa: E402

DEFAULT = ["MSFT", "NVDA", "CRWD", "AAPL", "AMZN", "GOOGL", "META", "AMD", "ADBE", "CRM",
           "ORCL", "INTC", "CSCO", "QCOM", "AVGO", "NOW", "PANW", "SNOW", "DDOG", "ZS"]


def pct(x, d=1):
    return "חסר" if x is None else f"{x * 100:.{d}f}%"


def num(x, d=2):
    return "חסר" if x is None else f"{x:.{d}f}"


def run(tickers: list[str], out: Path, hub: DataHub | None = None, settings=None) -> dict:
    settings = settings or load_settings()
    if hub is None:
        store = Store(out / "cache.sqlite")
        hub = DataHub(settings, store)
    cds = []
    for t in tickers:
        print(f"loading {t}", flush=True)
        cds.append(hub.load(t))
    bench = hub.benchmark()
    results = analyze_all(cds, settings, bench)
    wf = walk_forward(results, bench, float(settings.get("backtest.cost_bps_per_side", 15)))
    studies = {r.ticker: candles.signal_study(r.cd.prices) if r.cd.prices is not None else {"available": False, "why": "אין מחירים"}
               for r in results}
    pooled = candles.pool_studies(studies)
    rows = []
    for r in results:
        c = r.extras.get("candles", {})
        rows.append({"ticker": r.ticker, "prices": r.cd.prices_source, "bars": 0 if r.cd.prices is None else len(r.cd.prices),
                     "events": len(r.cd.earnings_events), "health": r.h.score, "valuation": r.val.get("score"),
                     "cls": r.fin.get("cls"), "floor": c.get("floor"), "target": c.get("target"), "flow": (c.get("flow") or {}).get("state"),
                     "trend": c.get("trend"), "errors": r.cd.errors})
    report = {"run_date": date.today().isoformat(), "tickers": tickers, "providers": hub.provider_status(), "companies": rows,
              "walk_forward": {k: v for k, v in wf.items() if k != "records"}, "candles_pooled": pooled,
              "candles_by_ticker": studies, "hub_errors": hub.errors}
    out.mkdir(parents=True, exist_ok=True)
    (out / "history_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / "history_report.md").write_text(markdown(report), encoding="utf-8")
    return report


def markdown(rep: dict) -> str:
    L = [f"# EVI — בדיקה על נתוני עבר ({rep['run_date']})", ""]
    L += ["## ספקי נתונים", "| קבוצה | ספק | פעיל |", "|---|---|---|"]
    L += [f"| {p['group']} | {p['provider']} | {'כן' if p['active'] else 'לא — ' + p['note']} |" for p in rep["providers"]]
    L += ["", "## חברות", "| מניה | ימי מחיר | דוחות (8-K) | בריאות | תמחור | סיווג | רצפה | יעד | נפח | מגמה |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["companies"]:
        L.append(f"| {r['ticker']} | {r['bars']} | {r['events']} | {num(r['health'], 0)} | {num(r['valuation'], 0)} | {r['cls'] or 'חסר'} | "
                 f"{num(r['floor'])} | {num(r['target'])} | {r['flow'] or 'חסר'} | {r['trend'] or 'חסר'} |")
    wf = rep["walk_forward"]
    L += ["", "## 1. כללי תזמון סביב דוחות (Walk-forward, מחוץ למדגם = 30% האחרונים)"]
    if not wf.get("available"):
        L.append(f"לא ניתן להריץ: {wf.get('why')}")
    else:
        L += [f"אירועים: {wf['n']} · תאריך פיצול: {wf['split_date']}", "", "| כלל | אירועים מחוץ למדגם | עם אות | יתרון | t | מסקנה |", "|---|---|---|---|---|---|"]
        for rule in wf["rules"].values():
            o = rule["oos"]
            L.append(f"| {rule['name']} | {o.get('n_all', 0)} | {o.get('n_sig', 0)} | {pct(o.get('edge'), 2)} | {num(o.get('t'))} | {rule['verdict']} |")
        L += ["", "מגבלות: " + " · ".join(wf.get("limitations", []))]
    p = rep["candles_pooled"]
    L += ["", "## 2. אותות נרות ונפח (Point-in-Time, כל המניות יחד)"]
    if not p.get("available"):
        L.append("לא ניתן להריץ — אין היסטוריית מחירים.")
    else:
        L += [f"מניות: {p['tickers']} · הרצפה החזיקה 20 ימי מסחר ב-**{pct(p['floor_held'])}** מ-{p['floor_n']} בדיקות", "",
              "| אות | מופעים | יתרון 10 ימים | יתרון 20 ימים | % עליות אחרי 10 ימים |", "|---|---|---|---|---|"]
        for k, a in sorted(p["signals"].items(), key=lambda kv: -kv[1]["n"]):
            if a["n"]:
                L.append(f"| {k} | {a['n']} | {pct(a['edge10'], 2)} | {pct(a['edge20'], 2)} | {pct(a['hit10'], 0)} |")
        L += ["", "יתרון = תשואה ממוצעת אחרי האות פחות תשואה ממוצעת של כל הימים באותה מניה. ללא עלויות מסחר."]
    L += ["", "## מה עוד לא נבדק", "- ציוני הבריאות והתמחור לא שוחזרו Point-in-Time (מה שהיה ידוע בכל תאריך) — זה השלב הבא בבדיקה.",
          "- Survivorship bias: רק חברות שנסחרות היום.", "- Short Interest: אין מקור מחובר."]
    errs = [e for r in rep["companies"] for e in r["errors"]] + rep["hub_errors"]
    if errs:
        L += ["", "## שגיאות", *[f"- {e}" for e in errs[:40]]]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=DEFAULT)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    rep = run([t.upper() for t in a.tickers], Path(a.out))
    print((Path(a.out) / "history_report.md").read_text(encoding="utf-8"))
