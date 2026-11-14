"""DataHub — the swappable Data Provider layer.

Each data group has an ordered list of providers. The hub records which provider supplied each group
(`CompanyData.sources_used`) and lists what is missing (`CompanyData.gaps`). It never substitutes demo values.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, timedelta
from typing import Any, Callable

import pandas as pd

from ..config import ROOT, Settings
from ..models import CompanyData, Val, missing, now_iso
from ..sectors import classify
from ..store import Store
from . import xbrl
from .edgar import EdgarProvider
from .finnhub import FinnhubProvider
from .prices import build_price_sources, last_close_val

log = logging.getLogger("evi")


class DataHub:
    def __init__(self, settings: Settings, store: Store, today: date | None = None):
        self.s = settings
        self.store = store
        self.today = today or date.today()
        self.errors: list[str] = []
        try:
            self.edgar: EdgarProvider | None = EdgarProvider(store, settings.sec_user_agent, settings.get("edgar.rate_limit_per_sec", 8),
                                                             settings.get("cache.ttl_hours", {}))
        except ValueError as e:
            self.edgar = None
            self.errors.append(str(e))
        self.finnhub = FinnhubProvider(store, settings.finnhub_key, settings.get("finnhub.rate_limit_per_sec", 0.9)) if settings.finnhub_key else None
        self.price_sources = build_price_sources(store, settings.get("prices.providers", ["massive", "yfinance"]), settings.massive_key,
                                                 settings.enable_yfinance, settings.get("prices.massive_base_url", "https://api.massive.com"))
        self._bench: pd.DataFrame | None = None
        self._bench_loaded = False

    # ---------------------------------------------------------------- status
    def provider_status(self) -> list[dict[str, Any]]:
        return [
            {"group": "דוחות כספיים, הגשות, Form 4, דילול", "provider": "SEC EDGAR", "active": self.edgar is not None,
             "note": "פעיל" if self.edgar else "חסר SEC_USER_AGENT בקובץ .env"},
            {"group": "מחיר עדכני, 52 שבועות, לוח דוחות, קונצנזוס, הפתעות EPS, חדשות", "provider": "Finnhub",
             "active": self.finnhub is not None, "note": "פעיל" if self.finnhub else "לא הוגדר FINNHUB_API_KEY — הנתונים יוצגו כחסרים"},
            {"group": "היסטוריית מחירים (Backtest, מומנטום)", "provider": " → ".join(p.name for p in self.price_sources) or "—",
             "active": bool(self.price_sources), "note": "פעיל" if self.price_sources else "לא הוגדר ספק מחירים (MASSIVE_API_KEY או ENABLE_YFINANCE)"},
        ]

    # ---------------------------------------------------------------- universe & candidates
    def universe(self) -> dict[str, dict]:
        if not self.edgar:
            return {}
        ex = set(self.s.get("universe.exchanges", ["Nasdaq", "NYSE"]))
        return {t: d for t, d in self.edgar.tickers().items() if d.get("exchange") in ex}

    def list_universe(self) -> list[str]:
        p = ROOT / self.s.get("universe.list_file", "data/universe.csv")
        if not p.exists():
            return []
        with p.open(encoding="utf-8") as fh:
            return [r["ticker"].strip().upper() for r in csv.DictReader(fh) if r.get("ticker")]

    def mode(self) -> str:
        m = self.s.get("universe.mode", "auto")
        if m == "auto":
            return "calendar" if self.finnhub else "list"
        return m

    def candidates(self, dmin: int, dmax: int, sectors: set[str] | None, include_recent: bool,
                   progress: Callable[[float, str], None] | None = None) -> tuple[list[dict], list[str]]:
        """Return companies whose next earnings date falls in the window, with sector classification."""
        notes: list[str] = []
        if not self.edgar:
            return [], self.errors
        uni = self.universe()
        out: list[dict] = []
        mode = self.mode()
        if mode == "calendar" and self.finnhub:
            start = self.today + timedelta(days=(-10 if include_recent else dmin))
            rows = self.finnhub.earnings_calendar(start, self.today + timedelta(days=dmax))
            notes.append(f"מצב סריקה: לוח הדוחות של Finnhub ({len(rows)} דוחות בטווח, לפני סינון בורסה וסקטור).")
            seen = set()
            pool = [r for r in rows if (r.get("symbol") or "").upper() in uni]
            for i, r in enumerate(pool):
                t = r["symbol"].upper()
                if t in seen:
                    continue
                seen.add(t)
                if progress:
                    progress(i / max(len(pool), 1), f"סיווג סקטור: {t}")
                sec, how = self._sector_for(t, uni[t]["cik"])
                if sec is None or (sectors and sec not in sectors):
                    continue
                d = (date.fromisoformat(r["date"]) - self.today).days
                if not (dmin <= d <= dmax or (include_recent and -10 <= d < 0)):
                    continue
                out.append({"ticker": t, "cik": uni[t]["cik"], "sector": sec, "sector_how": how,
                            "next": {"date": r["date"], "status": "provider", "hour": r.get("hour"), "eps_est": r.get("epsEstimate"),
                                     "rev_est": r.get("revenueEstimate"), "source": r["_source"], "fetched": r.get("_fetched"),
                                     "quarter": f"{r.get('year')}Q{r.get('quarter')}"}})
        else:
            tickers = self.list_universe()
            notes.append(f"מצב סריקה: רשימת מניות מקובץ universe.csv ({len(tickers)} מניות). תאריכי הדוח משוערים מקומית "
                         "לפי היסטוריית 8-K Item 2.02 — הוסף מפתח Finnhub לקבלת לוח דוחות.")
            for i, t in enumerate(tickers):
                if progress:
                    progress(i / max(len(tickers), 1), f"בדיקת מועד דוח: {t}")
                if t not in uni:
                    notes.append(f"{t}: לא נמצא ברשימת SEC לבורסות שנבחרו")
                    continue
                cik = uni[t]["cik"]
                sec, how = self._sector_for(t, cik)
                if sec is None or (sectors and sec not in sectors):
                    continue
                _, filings = self.edgar.submissions(cik, include_older=False)
                ev = self.edgar.earnings_events(filings)
                nxt = self.edgar.estimate_next_earnings(ev, self.today)
                if not nxt:
                    notes.append(f"{t}: אין מספיק דוחות 8-K Item 2.02 להערכת מועד")
                    continue
                d = (date.fromisoformat(nxt["date"]) - self.today).days
                recent = bool(ev) and 0 <= (self.today - date.fromisoformat(ev[-1]["filed"])).days <= 10
                if dmin <= d <= dmax or (include_recent and recent):
                    out.append({"ticker": t, "cik": cik, "sector": sec, "sector_how": how, "next": {**nxt, "source": "חישוב מקומי מ-SEC EDGAR"}})
        out.sort(key=lambda r: r["next"]["date"])
        cap = int(self.s.get("universe.max_companies_per_scan", 60))
        if len(out) > cap:
            notes.append(f"נמצאו {len(out)} חברות; נותחו {cap} הראשונות לפי מועד הדוח (ניתן לשנות ב-config.yaml).")
            out = out[:cap]
        return out, notes

    def _sector_for(self, ticker: str, cik: int) -> tuple[str | None, str]:
        sec, how = classify(ticker, None)
        if sec:
            return sec, how
        header, _ = self.edgar.submissions(cik, include_older=False)
        return classify(ticker, (header or {}).get("sic"))

    # ---------------------------------------------------------------- benchmark
    def benchmark(self) -> pd.DataFrame | None:
        if not self._bench_loaded:
            self._bench_loaded = True
            sym = self.s.get("prices.benchmark", "SPY")
            for src in self.price_sources:
                df = src.history(sym, int(self.s.get("prices.history_years", 6)))
                if df is not None:
                    self._bench = df
                    break
        return self._bench

    # ---------------------------------------------------------------- load one company
    def load(self, ticker: str, cik: int | None = None, sector: str | None = None, sector_how: str | None = None,
             next_hint: dict | None = None) -> CompanyData:
        t = ticker.upper()
        if not self.edgar:
            cd = CompanyData(t, None, t, None, sector)
            cd.errors.extend(self.errors)
            return cd
        info = self.edgar.tickers().get(t, {})
        cik = cik or info.get("cik")
        cd = CompanyData(t, cik, info.get("name", t), info.get("exchange"), sector)
        if not cik:
            cd.errors.append("הטיקר לא נמצא ברשימת SEC")
            return cd
        hist_years = int(self.s.get("prices.history_years", 6))
        # --- filings
        try:
            header, filings = self.edgar.submissions(cik, include_older=True, min_year=self.today.year - max(hist_years, 6))
        except Exception as e:  # network or parse error
            header, filings = None, []
            cd.errors.append(f"submissions: {e}")
        if header:
            cd.name = header.get("name") or cd.name
            cd.sic, cd.sic_desc = header.get("sic"), header.get("sicDescription")
            if not sector:
                cd.sector, sector_how = classify(t, cd.sic)
            cd.sources_used["הגשות (submissions)"] = f"SEC EDGAR · {self.edgar.fetched_at(header['_url']) or now_iso()}"
        cd.sources_used["סיווג סקטור"] = sector_how or classify(t, cd.sic)[1]
        # --- fundamentals
        try:
            cf, url = self.edgar.companyfacts(cik)
        except Exception as e:
            cf, url = None, ""
            cd.errors.append(f"companyfacts: {e}")
        if cf:
            fetched = self.edgar.fetched_at(url)
            x = xbrl.extract(cf, fetched)
            cd.fin, cd.annual, cd.quarterly = x["fin"], x["annual"], x["quarterly"]
            cd.maturities, cd.maturities_as_of = x["maturities"], x["maturities_as_of"]
            cd.gaps.extend(x["gaps"])
            cd.sources_used["דוחות כספיים (XBRL)"] = f"SEC EDGAR companyfacts · {fetched}"
        else:
            cd.gaps.append("אין נתוני XBRL ב-SEC (ייתכן חברה זרה / דיווח 20-F)")
        # --- events, flags, insiders, dilution
        cd.earnings_events = self.edgar.earnings_events(filings)
        cd.flags = self.edgar.filing_flags(filings, self.today, known_after_days=int(self.s.get("risk.known_after_days", 30)))
        try:
            cd.insiders = self.edgar.insider_transactions(cik, filings, self.today, int(self.s.get("risk.insider_lookback_days", 180)),
                                                          int(self.s.get("risk.max_form4_docs", 40)))
            cd.sources_used["בעלי עניין"] = "SEC EDGAR · Form 4"
        except Exception as e:
            cd.errors.append(f"Form 4: {e}")
        cd.dilution = self.edgar.dilution_filings(filings, self.today)
        # --- prices
        for src in self.price_sources:
            try:
                df = src.history(t, hist_years)
            except Exception as e:
                cd.errors.append(f"{src.name}: {e}")
                df = None
            if df is not None and len(df) > 30:
                cd.prices, cd.prices_source = df, src.name
                cd.sources_used["היסטוריית מחירים"] = f"{src.name} · עד {df.index[-1].date()}"
                break
        if cd.prices is None:
            cd.gaps.append("היסטוריית מחירים: אין ספק מוגדר או שהספק לא החזיר נתונים")
        # --- current price & quote metrics
        if self.finnhub:
            try:
                cd.price = self.finnhub.quote(t)
                cd.quote_meta = self.finnhub.metrics(t)
            except Exception as e:
                cd.errors.append(f"Finnhub quote: {e}")
        if not cd.price.ok and cd.prices is not None:
            cd.price = last_close_val(cd.prices, cd.prices_source or "")
        if not cd.price.ok:
            cd.price = missing("אין מחיר: הגדר FINNHUB_API_KEY או ספק היסטוריית מחירים")
            cd.gaps.append("מחיר מניה עדכני")
        _derive_quote_meta(cd)
        # --- next earnings
        cd.next_earnings = self._next_earnings(t, next_hint, cd)
        # --- Finnhub extras
        if self.finnhub:
            try:
                cd.surprises, cd.surprises_source = self.finnhub.surprises(t)
                cd.recommendations = self.finnhub.recommendations(t)
                cd.flags.extend(self.finnhub.news_flags(t, self.today))
                cd.sources_used["הפתעות EPS / המלצות / חדשות"] = f"Finnhub · {now_iso()[:10]}"
            except Exception as e:
                cd.errors.append(f"Finnhub: {e}")
        else:
            cd.gaps.append("הפתעות EPS, קונצנזוס אנליסטים וחדשות: דורש FINNHUB_API_KEY")
        ne = cd.next_earnings
        if ne.get("eps_est") is not None or ne.get("rev_est") is not None:
            self.store.estimate_save(self.today.isoformat(), t, ne.get("quarter") or ne.get("date", ""), ne.get("eps_est"), ne.get("rev_est"), ne.get("source", ""))
        cd.estimate_history = self.store.estimate_history(t)
        cd.manual = self.store.manual_get(t)
        if cd.manual.get("confirmed_date"):
            cd.next_earnings = {**cd.next_earnings, "date": cd.manual["confirmed_date"], "status": "confirmed_manual",
                                "source": "אושר ידנית ע\"י המשתמש (הודעת החברה)"}
        return cd

    def _next_earnings(self, t: str, hint: dict | None, cd: CompanyData) -> dict:
        if hint:
            return dict(hint)
        if self.finnhub:
            rows = self.finnhub.earnings_calendar(self.today - timedelta(days=10), self.today + timedelta(days=120), symbol=t)
            fut = sorted([r for r in rows if r.get("date")], key=lambda r: r["date"])
            up = [r for r in fut if r["date"] >= self.today.isoformat()]
            r = up[0] if up else (fut[-1] if fut else None)
            if r:
                return {"date": r["date"], "status": "provider", "hour": r.get("hour"), "eps_est": r.get("epsEstimate"),
                        "rev_est": r.get("revenueEstimate"), "source": r["_source"], "fetched": r.get("_fetched"),
                        "quarter": f"{r.get('year')}Q{r.get('quarter')}"}
        est = self.edgar.estimate_next_earnings(cd.earnings_events, self.today) if self.edgar else None
        if est:
            return {**est, "source": "חישוב מקומי מ-SEC EDGAR"}
        return {"date": None, "status": "missing", "source": "", "basis": "אין מספיק היסטוריית דוחות להערכה"}


def _derive_quote_meta(cd: CompanyData) -> None:
    """52w high/low and returns: prefer Finnhub metric; else compute from price history (CALC)."""
    df = cd.prices
    meta = cd.quote_meta or {}
    def from_df(key: str, fn) -> None:
        if (key not in meta or not meta[key].ok) and df is not None and len(df) > 5:
            try:
                val = fn(df)
            except Exception:
                val = None
            meta[key] = Val(val, source=f"חישוב מהיסטוריית מחירים ({cd.prices_source})", as_of=df.index[-1].date().isoformat(), layer="CALC") \
                if val is not None else missing("אין מספיק היסטוריה")
    last_year = lambda d: d[d.index >= d.index[-1] - pd.Timedelta(days=365)]
    from_df("high52", lambda d: float(last_year(d)["high"].max()))
    from_df("low52", lambda d: float(last_year(d)["low"].min()))
    from_df("ret1y", lambda d: float(d["close"].iloc[-1] / last_year(d)["close"].iloc[0] - 1) if len(last_year(d)) > 200 else None)
    from_df("ret3m", lambda d: float(d["close"].iloc[-1] / d["close"].iloc[-64] - 1) if len(d) > 64 else None)
    for k in ("high52", "low52", "ret1y", "ret3m"):
        meta.setdefault(k, missing("דורש Finnhub או היסטוריית מחירים"))
    cd.quote_meta = meta
