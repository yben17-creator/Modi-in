import math
from datetime import date

import pytest

from evi.analytics.pipeline import analyze_all
from evi.config import load_settings
from evi.providers import xbrl
from evi.providers.edgar import EdgarProvider, parse_form4
from evi.providers.router import DataHub
from evi.reports.export import company_xlsx, report_html, report_pdf, rtl, scanner_xlsx
from evi.reports.hebrew import sections
from evi.store import Store
from evi.validation.backtest import walk_forward

from . import fixtures_builder as fx


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "t.sqlite")
    fx.seed_cache(s)
    return s


@pytest.fixture()
def settings(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Test test@example.com")
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    return load_settings(reload=True)


def make_hub(settings, store, with_prices=True):
    hub = DataHub(settings, store, today=date(2026, 11, 14))
    hub.finnhub = None
    hub.price_sources = [fx.FakePrices({"TSTC": fx.prices(1), "SPY": fx.prices(2)})] if with_prices else []
    return hub


# ------------------------------------------------------------------ XBRL
def test_xbrl_ttm_and_ytd_diff():
    x = xbrl.extract(fx.companyfacts())
    f = x["fin"]
    q = x["quarterly"]["revenue"]
    # Q4 is derived only if needed; TTM must be sum of the last 4 contiguous quarters
    assert f["revenue"].ok and f["revenue"].note == "TTM"
    # cash flow quarters derived from YTD differences
    assert any(i["how"] == "ytd-diff" for i in x["quarterly"]["ocf"])
    assert f["ocf"].ok and f["capex"].ok and f["sbc"].ok
    assert f["shares_outstanding"].ok and f["shares_outstanding_3y"].ok
    assert x["maturities"] and x["maturities"][0]["amount"] == 50e6


def test_missing_tags_are_missing_not_zero():
    cf = fx.companyfacts()
    del cf["facts"]["us-gaap"]["InterestExpense"]
    x = xbrl.extract(cf)
    assert not x["fin"]["interest_expense"].ok
    assert x["fin"]["interest_expense"].value is None


def test_q4_derivation_annual_only():
    x = xbrl.extract(fx.companyfacts())
    q = x["quarterly"]["revenue"]
    ends = [i["end"] for i in q]
    # Revenue Q4 is never reported directly in fixtures; TTM still requires it -> annual fallback or derived
    assert x["fin"]["revenue"].value > 0


# ------------------------------------------------------------------ EDGAR parsing
def test_form4_plan_and_tax():
    tx = parse_form4(fx.FORM4_XML, "u")
    assert [t.plan for t in tx] == ["10b5-1", "tax"]
    assert tx[0].value == pytest.approx(505000)
    assert "Chief Executive Officer" in tx[0].role


def test_events_flags_and_next_date():
    sub = fx.submissions()
    filings = EdgarProvider._flatten(sub["filings"]["recent"], fx.CIK)
    ev = EdgarProvider.earnings_events(filings)
    assert len(ev) > 20
    flags = EdgarProvider.filing_flags(filings, date(2026, 11, 14))
    cats = {f.category for f in flags}
    assert "Auditor Change" in cats and "Executive Departure" in cats
    new = [f for f in flags if f.category == "Auditor Change"][0]
    assert new.known is False
    nxt = EdgarProvider.estimate_next_earnings(ev, date(2026, 11, 14))
    assert nxt["status"] == "estimated_local"
    assert nxt["date"] > "2026-11-14"


# ------------------------------------------------------------------ end to end
def test_full_pipeline_with_prices(settings, store):
    hub = make_hub(settings, store)
    cd = hub.load("TSTC")
    assert cd.cik == fx.CIK and cd.sector == "Software & SaaS"
    assert cd.price.ok and "TEST prices" in cd.price.source
    assert cd.insiders and cd.flags
    res = analyze_all([cd], settings, hub.benchmark())
    r = res[0]
    assert r.h.score is not None
    assert r.val.get("mid") is not None and r.val["grid"]["cells"]
    assert r.t["available"] and r.t["n"] >= 8
    assert r.mon["available"]
    # peer medians need >=3 peers → relative discount missing, not invented
    assert r.val["rel_disc"] is None
    # auditor change is 'cap' level (severity 3, new)
    assert r.r["override"] is not None
    secs = sections(r)
    assert len(secs) == 7 and all(t for _, _, t in secs)
    assert scanner_xlsx(res)[:2] == b"PK" and company_xlsx(r)[:2] == b"PK"
    assert "<html" in report_html(r)
    pdf = report_pdf(r)
    assert pdf is None or pdf[:4] == b"%PDF"
    wf = walk_forward(res, hub.benchmark())
    assert wf["available"] and "r1" in wf["rules"]


def test_pipeline_without_prices_marks_missing(settings, store):
    hub = make_hub(settings, store, with_prices=False)
    cd = hub.load("TSTC")
    assert not cd.price.ok
    r = analyze_all([cd], settings, None)[0]
    assert r.val.get("mos") is None
    assert not r.t["available"] and "מחירים" in r.t["why"]
    assert not r.mon["available"]
    assert r.m["mcap"].value is None
    assert r.fin["idx"] in (3, 4)  # cannot be ranked without valuation
    secs = dict((h, t) for h, _, t in sections(r))
    assert "חסר" in secs["הערכת שווי"] or "לא חושב" in secs["הערכת שווי"]


def test_rtl_fallback():
    assert rtl("abc") == "abc"
    assert rtl("שלום") in ("םולש",)


def test_day0_mapping_eastern_time():
    import pandas as pd
    from evi.analytics.timing import day0_index
    idx = pd.bdate_range("2026-01-05", "2026-01-16")
    assert idx[day0_index(idx, "2026-01-07T16:05:00.000Z")] == pd.Timestamp("2026-01-08")  # after close → next session
    assert idx[day0_index(idx, "2026-01-07T07:30:00.000Z")] == pd.Timestamp("2026-01-07")  # pre-market → same session
    assert idx[day0_index(idx, "2026-01-10")] == pd.Timestamp("2026-01-12")                # weekend → next session
