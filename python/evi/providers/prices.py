"""Daily price history providers. Output: DataFrame indexed by date with open/high/low/close/volume (split/dividend adjusted).

* Tiingo — requires TIINGO_API_KEY. Free plan: adjusted EOD history (decades), ~1000 requests/day.
* Massive (formerly Polygon.io) — requires MASSIVE_API_KEY. Free plan: end-of-day data, limited history and calls/minute.
* Yahoo via yfinance — unofficial, disabled by default (ENABLE_YFINANCE=true to opt in). Not an official data feed.
If no provider is configured, price history is missing and every module that needs it shows "חסר".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Protocol

import pandas as pd

from ..http import CachedHttp, HttpError
from ..store import Store


class PriceSource(Protocol):
    name: str
    def history(self, symbol: str, years: int) -> pd.DataFrame | None: ...


class MassivePrices:
    name = "Massive (Polygon) · aggs adjusted"

    def __init__(self, store: Store, api_key: str, base: str = "https://api.massive.com", per_second: float = 0.08):
        self.key = api_key
        self.base = base.rstrip("/")
        self.http = CachedHttp(store, "massive", per_second)

    def history(self, symbol: str, years: int) -> pd.DataFrame | None:
        end = date.today()
        start = end - timedelta(days=int(365.25 * years))
        url = f"{self.base}/v2/aggs/ticker/{symbol}/range/1/day/{start.isoformat()}/{end.isoformat()}"
        try:
            js = self.http.get_json(url, {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.key}, ttl_h=12, secret=("apiKey",))
        except HttpError:
            return None
        res = (js or {}).get("results") or []
        if not res:
            return None
        df = pd.DataFrame(res)
        df["date"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert("America/New_York").dt.date
        df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        return _finish(df)


class TiingoPrices:
    name = "Tiingo · EOD adjusted"

    def __init__(self, store: Store, api_key: str, per_second: float = 0.5):
        self.key = api_key
        self.http = CachedHttp(store, "tiingo", per_second)

    def history(self, symbol: str, years: int) -> pd.DataFrame | None:
        start = date.today() - timedelta(days=int(365.25 * years))
        url = f"https://api.tiingo.com/tiingo/daily/{symbol.replace('.', '-').lower()}/prices"
        try:
            js = self.http.get_json(url, {"startDate": start.isoformat(), "resampleFreq": "daily", "token": self.key},
                                    ttl_h=12, secret=("token",))
        except HttpError:
            return None
        if not isinstance(js, list) or not js:
            return None
        df = pd.DataFrame(js)
        need = ["date", "adjOpen", "adjHigh", "adjLow", "adjClose", "adjVolume"]
        if any(k not in df.columns for k in need):
            return None
        # Tiingo sends raw open/close/... AND adjusted adj*; keep only the adjusted set to avoid duplicate column names
        df = df[need].rename(columns={"adjOpen": "open", "adjHigh": "high", "adjLow": "low", "adjClose": "close", "adjVolume": "volume"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return _finish(df)


class YFinancePrices:
    name = "Yahoo Finance via yfinance (לא רשמי)"

    def __init__(self) -> None:
        import yfinance  # noqa: F401  (raises ImportError if not installed)

    def history(self, symbol: str, years: int) -> pd.DataFrame | None:
        import yfinance as yf
        try:
            h = yf.Ticker(symbol.replace(".", "-")).history(period=f"{max(1, years)}y", auto_adjust=True)
        except Exception:
            return None
        if h is None or h.empty:
            return None
        h = h.reset_index()
        h["date"] = pd.to_datetime(h["Date"]).dt.date
        h = h.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        return _finish(h)


def _finish(df: pd.DataFrame) -> pd.DataFrame | None:
    df = df[["date", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    if df.empty:
        return None
    df = df.drop_duplicates("date").set_index("date").sort_index()
    df.index = pd.to_datetime(df.index)
    return df


def build_price_sources(store: Store, order: list[str], massive_key: str | None, enable_yf: bool, massive_base: str,
                        tiingo_key: str | None = None) -> list[PriceSource]:
    out: list[PriceSource] = []
    for name in order:
        if name == "tiingo" and tiingo_key:
            out.append(TiingoPrices(store, tiingo_key))
        elif name == "massive" and massive_key:
            out.append(MassivePrices(store, massive_key, massive_base))
        elif name == "yfinance" and enable_yf:
            try:
                out.append(YFinancePrices())
            except ImportError:
                pass
    return out


def last_close_val(df: pd.DataFrame | None, source: str):
    from ..models import Val, missing
    if df is None or df.empty:
        return missing("אין היסטוריית מחירים")
    return Val(float(df["close"].iloc[-1]), source=f"{source} · סגירה אחרונה", as_of=df.index[-1].date().isoformat(),
               fetched=datetime.now(timezone.utc).date().isoformat())
