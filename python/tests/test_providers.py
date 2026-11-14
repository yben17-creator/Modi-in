import json
from datetime import date
from urllib.parse import urlencode

from evi.config import load_settings
from evi.providers.finnhub import BASE, FinnhubProvider
from evi.providers.prices import MassivePrices
from evi.providers.router import DataHub
from evi.store import Store

from . import fixtures_builder as fx


def _put(store, name, url, params, body):
    store.cache_put(f"{name}|{url}?{urlencode(sorted(params.items()))}", 200, json.dumps(body).encode())


def test_finnhub_parsing_and_calendar_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Test t@x.com")
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    s = load_settings(reload=True)
    store = Store(tmp_path / "f.db")
    fx.seed_cache(store)
    today = date(2026, 11, 14)
    cal = {"earningsCalendar": [{"date": "2026-11-25", "symbol": "TSTC", "hour": "amc", "epsEstimate": 0.9, "revenueEstimate": 3.2e9, "year": 2026, "quarter": 3},
                                {"date": "2026-11-26", "symbol": "OTHR", "hour": "bmo", "year": 2026, "quarter": 3}]}
    _put(store, "finnhub", f"{BASE}/calendar/earnings", {"from": "2026-11-21", "to": "2026-12-14"}, cal)
    _put(store, "finnhub", f"{BASE}/quote", {"symbol": "TSTC"}, {"c": 51.2, "t": 1763150000})
    _put(store, "finnhub", f"{BASE}/stock/metric", {"symbol": "TSTC", "metric": "all"}, {"metric": {"52WeekHigh": 70, "52WeekLow": 40, "13WeekPriceReturnDaily": -5.0}})
    _put(store, "finnhub", f"{BASE}/stock/earnings", {"symbol": "TSTC"}, [{"actual": 1.0, "estimate": 0.9, "period": "2026-06-30", "surprisePercent": 11.1},
                                                                         {"actual": 0.8, "estimate": 0.85, "period": "2026-03-31", "surprisePercent": -5.9}])
    _put(store, "finnhub", f"{BASE}/stock/recommendation", {"symbol": "TSTC"}, [])
    _put(store, "finnhub", f"{BASE}/company-news", {"symbol": "TSTC", "from": "2026-08-16", "to": "2026-11-14"},
         [{"datetime": 1762900000, "headline": "TESTCO faces class action lawsuit", "summary": "", "source": "Wire", "url": "http://x"}])
    hub = DataHub(s, store, today=today)
    hub.price_sources = []
    assert hub.mode() == "calendar"
    cands, notes = hub.candidates(7, 30, None, False)
    assert [c["ticker"] for c in cands] == ["TSTC"]  # OTHR is OTC → excluded
    assert cands[0]["next"]["status"] == "provider"
    cd = hub.load("TSTC", cands[0]["cik"], cands[0]["sector"], cands[0]["sector_how"], cands[0]["next"])
    assert cd.price.value == 51.2 and "Finnhub" in cd.price.source
    assert len(cd.surprises) == 2
    assert any(f.category == "Litigation" and f.status == "דיווח תקשורתי" for f in cd.flags)
    assert cd.quote_meta["ret3m"].value == -0.05
    assert store.estimate_history("TSTC")[0]["eps_est"] == 0.9
    load_settings(reload=True)


def test_massive_parsing(tmp_path):
    store = Store(tmp_path / "m.db")
    mp = MassivePrices(store, "KEY")
    end = date.today()
    from datetime import timedelta
    start = end - timedelta(days=int(365.25 * 1))
    url = f"https://api.massive.com/v2/aggs/ticker/ABC/range/1/day/{start.isoformat()}/{end.isoformat()}"
    _put(store, "massive", url, {"adjusted": "true", "sort": "asc", "limit": 50000},
         {"results": [{"t": 1735828800000, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100}, {"t": 1735915200000, "o": 1.5, "h": 2, "l": 1, "c": 1.8, "v": 120}]})
    df = mp.history("ABC", 1)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"] and df["close"].iloc[-1] == 1.8
