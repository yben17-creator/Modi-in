"""Parity cases for the TS port of monitor/scan.py `compare` (watchlist change detection → alerts).
Usage: python tests/gen_alerts_parity.py <out.json>   (all inputs are arbitrary test values, not company data)"""
import json, sys
from types import SimpleNamespace
sys.path.insert(0, '.')
from evi.models import Flag
from evi.monitor.scan import compare

def fl(sev, known, status="מאומת", title="t"):
    return Flag("2026-11-10", "Impairment", f"{title}{sev}", status, sev, "", "SEC", None, known, False)

class Store:
    def __init__(self, w): self.w = w
    def watch_list(self): return self.w

def res(tk, snap, override=None, flags=(), mon=None):
    r = SimpleNamespace(ticker=tk, r={"override": override}, cd=SimpleNamespace(flags=list(flags)), mon=mon or {})
    r.snapshot_row = lambda: snap
    return r

base = {"health": 70.0, "valuation": 55.4, "earnings": 40.0, "risk": 20.0, "cls_idx": 1, "price": 100.0, "fv_base": 120.0}
cases_in = [
    ("no_change", {"AAA": {"base": base}}, [res("AAA", {**base, "health": 75.0})], 10),
    ("score_changes", {"AAA": {"base": base}}, [res("AAA", {**base, "health": 59.6, "valuation": 65.5, "risk": 35.0, "earnings": None})], 10),
    ("class_change_override_flags", {"AAA": {"base": base}}, [res("AAA", {**base, "cls_idx": 3}, {"level": "disqualify", "reason": "Risk Override: x"},
        [fl(3, False), fl(4, True), fl(2, False), fl(4, False, "דיווח תקשורתי")], {"alerts": [{"k": "Momentum Weakening", "he": "h", "d": "d1"}]})], 10),
    ("not_watched_and_missing_base", {"BBB": {"base": {"health": None, "cls_idx": None}}}, [res("AAA", {**base, "health": 0.0}), res("BBB", {**base, "health": 10.0})], 10),
    ("threshold_5", {"AAA": {"base": base}}, [res("AAA", {**base, "health": 64.5, "valuation": 60.5})], 5),
]
out = []
for name, watch, results, thr in cases_in:
    out.append({"name": name, "watch": watch, "threshold": thr,
                "results": [{"ticker": r.ticker, "snap": r.snapshot_row(), "override": r.r["override"],
                             "flags": [{"title": f.title, "status": f.status, "severity": f.severity, "known": f.known} for f in r.cd.flags],
                             "mon": [{"k": a["k"], "d": a["d"]} for a in r.mon.get("alerts", [])]} for r in results],
                "alerts": [list(a) for a in compare(Store(watch), results, thr)]})
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
for c in out: print(c["name"], c["alerts"])
