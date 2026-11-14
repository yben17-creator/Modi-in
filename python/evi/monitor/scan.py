"""Phase 6 — scheduled scans and alerts.

Usage:
    python -m evi.monitor.scan                      # scan with config.yaml defaults, compare to last snapshot, alert
    python -m evi.monitor.scan --min 7 --max 30 --sectors "Cybersecurity,Semiconductors"
Schedule it daily (cron / Windows Task Scheduler) — see README.
"""
from __future__ import annotations

import argparse
import sys

from ..analytics.pipeline import run_scan
from ..analytics.scores import CLASSES
from ..config import load_settings
from ..models import now_iso
from ..providers.router import DataHub
from ..store import get_store
from .notify import send


def compare(store, results, threshold: float) -> list[tuple[str, str, str]]:
    """Alerts for watchlist companies whose scores/class changed materially vs the watch baseline or previous scan."""
    watch = store.watch_list()
    alerts: list[tuple[str, str, str]] = []
    for r in results:
        if r.ticker not in watch:
            continue
        base = watch[r.ticker]["base"]
        cur = r.snapshot_row()
        for k, he in (("health", "בריאות"), ("valuation", "תמחור"), ("earnings", "הזדמנות דוח"), ("risk", "סיכון")):
            a, b = base.get(k), cur.get(k)
            if a is not None and b is not None and abs(b - a) >= threshold:
                alerts.append((r.ticker, "score_change", f"{r.ticker}: ציון {he} השתנה מ-{a:.0f} ל-{b:.0f}"))
        if base.get("cls_idx") is not None and base["cls_idx"] != cur["cls_idx"]:
            alerts.append((r.ticker, "class_change", f"{r.ticker}: הסיווג השתנה מ\"{CLASSES[base['cls_idx']]}\" ל\"{CLASSES[cur['cls_idx']]}\""))
        if r.r["override"]:
            alerts.append((r.ticker, "risk_override", f"{r.ticker}: {r.r['override']['reason']}"))
        for fl in r.cd.flags:
            if not fl.known and fl.severity >= 3:
                alerts.append((r.ticker, "new_flag", f"{r.ticker}: דגל חדש ({fl.status}) — {fl.title}"))
        for a in r.mon.get("alerts", []):
            alerts.append((r.ticker, "momentum", f"{r.ticker}: {a['k']} — {a['d']}"))
    return alerts


def main(argv: list[str] | None = None) -> int:
    s = load_settings()
    ap = argparse.ArgumentParser(description="EVI scheduled scan")
    ap.add_argument("--min", type=int, default=int(s.get("scan.days_min", 7)))
    ap.add_argument("--max", type=int, default=int(s.get("scan.days_max", 30)))
    ap.add_argument("--sectors", type=str, default="")
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args(argv)
    store = get_store()
    hub = DataHub(s, store)
    if not hub.edgar:
        print("שגיאה:", "; ".join(hub.errors), file=sys.stderr)
        return 2
    sectors = {x.strip() for x in args.sectors.split(",") if x.strip()} or None
    out = run_scan(hub, store, s, args.min, args.max, sectors, include_recent=True,
                   progress=lambda f, msg: print(f"[{f:4.0%}] {msg}"), extra_tickers=list(store.watch_list()))
    alerts = compare(store, out["results"], float(s.get("alerts.score_change", 10)))
    ts = now_iso()
    for t, kind, msg in alerts:
        store.alert_add(ts, t, kind, msg)
    print(f"נותחו {len(out['results'])} חברות; {len(alerts)} התראות.")
    for n in out["notes"]:
        print("•", n)
    if alerts and not args.no_notify:
        ch = send(s, f"EVI — {len(alerts)} התראות", [m for _, _, m in alerts])
        print("נשלח דרך:", ", ".join(ch) or "לא הוגדר ערוץ שליחה (.env)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
