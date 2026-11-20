import numpy as np
import pandas as pd

from evi.analytics import candles


def _df(close, vol=None, spread=0.01):
    close = np.asarray(close, float)
    idx = pd.bdate_range("2022-01-03", periods=len(close))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) * (1 + spread)
    lo = np.minimum(op, close) * (1 - spread)
    return pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close,
                         "volume": np.full(len(close), 1e6) if vol is None else vol}, index=idx)


def _walk(n=400, seed=3):
    r = np.random.default_rng(seed)
    return _df(100 * np.exp(np.cumsum(r.normal(0.0003, 0.015, n))), r.uniform(5e5, 2e6, n))


def test_short_history_is_missing():
    out = candles.analyze(_walk(40))
    assert out["available"] is False and "60" in out["why"]


def test_floor_below_price_and_short_interest_missing():
    out = candles.analyze(_walk())
    assert out["available"]
    assert out["floor"] < out["close"]
    assert out["target"] is None or out["target"] > out["close"]
    assert out["short"]["value"] is None


def test_fair_value_caps_target():
    df = _walk()
    base = candles.analyze(df)
    fv = base["close"] * 1.01
    out = candles.analyze(df, fair_value=fv)
    assert out["target"] <= (base["target"] or fv) and out["target"] > out["close"]


def test_bullish_engulfing_detected():
    df = _df([100] * 30 + [99, 98, 97])
    df.iloc[-2, df.columns.get_loc("open")] = 99.0   # red candle 99 -> 97.5
    df.iloc[-2, df.columns.get_loc("close")] = 97.5
    df.iloc[-1, df.columns.get_loc("open")] = 97.0   # green candle engulfing it
    df.iloc[-1, df.columns.get_loc("close")] = 100.0
    df["high"] = df[["open", "close"]].max(axis=1) * 1.005
    df["low"] = df[["open", "close"]].min(axis=1) * 0.995
    assert candles.pattern_frame(df)["bull_engulf"].iloc[-1]


def test_quiet_distribution_flat_price_selling_volume():
    n = 120
    close = 100 + np.tile([0.4, -0.4], n // 2)       # flat price
    df = _df(close)
    # closes near the low of each bar, heavy volume on down days → selling pressure
    df["high"] = df["close"] + 2.0
    df["low"] = df["close"] - 0.2
    df["volume"] = np.where(np.diff(np.r_[close[0], close]) < 0, 3e6, 1e6)
    st = candles.flow_state(df)
    assert st["state"] == "distribution", st


def test_levels_are_point_in_time():
    df = _walk()
    i = 300
    full = candles.levels_at(df, i)
    cut = candles.levels_at(df.iloc[:i + 1], i)
    assert full == cut          # future bars never change what was known at bar i


def test_signal_study_and_pool():
    s = candles.signal_study(_walk(600))
    assert s["available"] and 0 <= s["floor"]["held"] <= 1
    assert set(s["baseline"]) == {5, 10, 20}
    p = candles.pool_studies({"A": s, "B": candles.signal_study(_walk(600, 7))})
    assert p["tickers"] == 2 and p["floor_n"] > 0


def test_run_history_offline(tmp_path, monkeypatch):
    import importlib.util
    from datetime import date
    from pathlib import Path

    from evi.config import load_settings
    from evi.providers.router import DataHub
    from evi.store import Store

    from . import fixtures_builder as fx

    monkeypatch.setenv("SEC_USER_AGENT", "Test test@example.com")
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    s = load_settings(reload=True)
    st = Store(tmp_path / "t.sqlite")
    fx.seed_cache(st)
    hub = DataHub(s, st, today=date(2026, 11, 14))
    hub.finnhub = None
    hub.price_sources = [fx.FakePrices({"TSTC": fx.prices(1), "SPY": fx.prices(2)})]
    spec = importlib.util.spec_from_file_location("run_history", Path(__file__).resolve().parent.parent / "scripts" / "run_history.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rep = mod.run(["TSTC"], tmp_path / "out", hub=hub, settings=s)
    md = (tmp_path / "out" / "history_report.md").read_text(encoding="utf-8")
    assert rep["companies"][0]["bars"] > 0 and "אותות נרות" in md
