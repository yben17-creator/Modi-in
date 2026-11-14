"""Orchestration: load companies → metrics → scores → valuation → timing → final assessment."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from ..config import Settings
from ..models import CompanyData, now_iso, v
from ..providers.router import DataHub
from ..store import Store
from . import momentum, scores, timing
from .fallen import fallen_angel
from .metrics import compute_metrics
from .valuation import Assumptions, default_assumptions, peer_medians, valuation


@dataclass
class Result:
    cd: CompanyData
    m: dict
    h: scores.Score
    severe: list[str]
    near_maturities: float | None
    a: Assumptions | None
    val: dict
    t: dict
    e: scores.Score
    r: dict
    fa: dict
    fin: dict
    mon: dict
    vol: float | None
    rev_change: float | None
    extras: dict = field(default_factory=dict)

    @property
    def ticker(self) -> str:
        return self.cd.ticker

    def snapshot_row(self) -> dict[str, Any]:
        return {"health": self.h.score, "valuation": self.val.get("score"), "earnings": self.e.score, "risk": self.r["score"],
                "cls_idx": self.fin["idx"], "price": v(self.cd.price), "fv_base": self.val.get("mid")}


def analyze_all(cds: list[CompanyData], settings: Settings, bench: pd.DataFrame | None,
                overrides: dict[str, Assumptions] | None = None, cost_bps: float | None = None) -> list[Result]:
    cfg_val = settings.get("valuation", {}) or {}
    cfg_risk = settings.get("risk", {}) or {}
    cfg_cls = settings.get("classification", {}) or {}
    cost = cost_bps if cost_bps is not None else float(settings.get("backtest.cost_bps_per_side", 15))
    min_ev = int(settings.get("backtest.min_events", 8))
    overrides = overrides or {}
    stage1 = []
    for cd in cds:
        m = compute_metrics(cd)
        stage1.append((cd, m))
    peers = peer_medians([(cd.sector, m) for cd, m in stage1], int(cfg_val.get("min_peers", 3)))
    out: list[Result] = []
    for cd, m in stage1:
        h, severe, near = scores.health(cd, m, float(settings.get("scores.health_min_coverage", 0.6)))
        vol = momentum.daily_vol(cd.prices)
        a = overrides.get(cd.ticker) or default_assumptions(cd, m, vol, cfg_val)
        val = valuation(cd, m, a, peers, cfg_val)
        t = timing.analyze(cd, bench, cost, min_ev, int(settings.get("backtest.max_years", 10)))
        e = scores.earnings(cd, m, val, t, float(settings.get("scores.earnings_min_coverage", 0.5)))
        r = scores.risk(cd, m, h, severe, vol, cfg_risk)
        fa = fallen_angel(cd, m, h.score, val)
        fin = scores.final(h, val, e, r, fa, cfg_cls)
        rev_change = scores.estimate_revision(cd)
        mon = momentum.monitor(cd, m, val, bench, rev_change)
        out.append(Result(cd, m, h, severe, near, a, val, t, e, r, fa, fin, mon, vol, rev_change, {"peers": peers.get(cd.sector or "", {})}))
    return out


def run_scan(hub: DataHub, store: Store, settings: Settings, dmin: int, dmax: int, sectors: set[str] | None,
             include_recent: bool, progress: Callable[[float, str], None] | None = None,
             overrides: dict[str, Assumptions] | None = None, extra_tickers: list[str] | None = None) -> dict[str, Any]:
    t0 = time.time()
    p = progress or (lambda f, s: None)
    cands, notes = hub.candidates(dmin, dmax, sectors, include_recent, lambda f, s: p(f * 0.3, s))
    have = {c["ticker"] for c in cands}
    for t in extra_tickers or []:  # watchlist companies are always refreshed
        if t not in have:
            cands.append({"ticker": t, "cik": None, "sector": None, "sector_how": None, "next": None, "watch_only": True})
    cds: list[CompanyData] = []
    for i, c in enumerate(cands):
        p(0.3 + 0.6 * i / max(len(cands), 1), f"טעינת נתונים: {c['ticker']}")
        cd = hub.load(c["ticker"], c.get("cik"), c.get("sector"), c.get("sector_how"), c.get("next"))
        cd.manual["_watch_only"] = c.get("watch_only", False)
        cds.append(cd)
    p(0.92, "חישוב מודלים")
    bench = hub.benchmark()
    results = analyze_all(cds, settings, bench, overrides)
    ts = now_iso()
    for r in results:
        store.snapshot_save(ts, r.ticker, r.snapshot_row())
    errors = [f"{r.ticker}: {e}" for r in results for e in r.cd.errors] + hub.errors
    store.scan_log(ts, {"dmin": dmin, "dmax": dmax, "sectors": sorted(sectors or []), "recent": include_recent}, len(results), time.time() - t0, errors)
    p(1.0, "הסריקה הושלמה")
    return {"results": results, "notes": notes, "ts": ts, "errors": errors, "bench": bench}
