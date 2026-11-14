"""Builds SEC-format fixtures for tests (fictional company TESTCO, CIK 9999999). Test data only — never used by the app."""
from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

CIK = 9999999


def _q_ends(fy: int) -> list[tuple[str, str]]:
    # fiscal year = calendar year; quarter (start, end)
    return [(f"{fy}-01-01", f"{fy}-03-31"), (f"{fy}-04-01", f"{fy}-06-30"), (f"{fy}-07-01", f"{fy}-09-30"), (f"{fy}-10-01", f"{fy}-12-31")]


def companyfacts(years=range(2019, 2026), last_q_2026: int = 3) -> dict:
    facts: dict = {"us-gaap": {}, "dei": {}}
    def add(tag, unit, row, tax="us-gaap"):
        facts[tax].setdefault(tag, {"label": tag, "units": {}})["units"].setdefault(unit, []).append(row)
    rev0 = 1000e6
    qs = []
    for fy in list(years) + [2026]:
        nq = 4 if fy < 2026 else last_q_2026
        for qi, (s, e) in enumerate(_q_ends(fy)[:nq]):
            qs.append((fy, qi, s, e))
    for n, (fy, qi, s, e) in enumerate(qs):
        rev = rev0 * (1.04 ** n)
        form, fp = ("10-Q", f"Q{qi + 1}") if qi < 3 else ("10-K", "FY")
        filed = (date.fromisoformat(e) + timedelta(days=35)).isoformat()
        q = {"start": s, "end": e, "fy": fy, "fp": fp, "form": form, "filed": filed}
        if qi < 3:  # 10-Q quarters reported directly for income statement
            add("RevenueFromContractWithCustomerExcludingAssessedTax", "USD", {**q, "val": rev})
            add("OperatingIncomeLoss", "USD", {**q, "val": rev * 0.18})
            add("NetIncomeLoss", "USD", {**q, "val": rev * 0.14})
            add("CostOfRevenue", "USD", {**q, "val": rev * 0.3})
            add("EarningsPerShareDiluted", "USD/shares", {**q, "val": round(rev * 0.14 / 200e6, 2)})
            add("WeightedAverageNumberOfDilutedSharesOutstanding", "shares", {**q, "val": 200e6})
            add("InterestExpense", "USD", {**q, "val": 5e6})
            add("DepreciationDepletionAndAmortization", "USD", {**q, "val": rev * 0.04})
            # cash flow: YTD from fiscal year start
            ytd_rev = sum(rev0 * 1.04 ** (n - qi + k) for k in range(qi + 1))
            add("NetCashProvidedByUsedInOperatingActivities", "USD", {**q, "start": f"{fy}-01-01", "val": ytd_rev * 0.25})
            add("PaymentsToAcquirePropertyPlantAndEquipment", "USD", {**q, "start": f"{fy}-01-01", "val": ytd_rev * 0.03})
            add("ShareBasedCompensation", "USD", {**q, "start": f"{fy}-01-01", "val": ytd_rev * 0.06})
        else:  # Q4 only via annual 10-K
            annual_rev = sum(rev0 * 1.04 ** (n - 3 + k) for k in range(4))
            a = {"start": f"{fy}-01-01", "end": e, "fy": fy, "fp": "FY", "form": "10-K", "filed": filed}
            add("RevenueFromContractWithCustomerExcludingAssessedTax", "USD", {**a, "val": annual_rev})
            add("OperatingIncomeLoss", "USD", {**a, "val": annual_rev * 0.18})
            add("NetIncomeLoss", "USD", {**a, "val": annual_rev * 0.14})
            add("CostOfRevenue", "USD", {**a, "val": annual_rev * 0.3})
            add("NetCashProvidedByUsedInOperatingActivities", "USD", {**a, "val": annual_rev * 0.25})
            add("PaymentsToAcquirePropertyPlantAndEquipment", "USD", {**a, "val": annual_rev * 0.03})
            add("ShareBasedCompensation", "USD", {**a, "val": annual_rev * 0.06})
            add("InterestExpense", "USD", {**a, "val": 20e6})
            add("DepreciationDepletionAndAmortization", "USD", {**a, "val": annual_rev * 0.04})
            add("WeightedAverageNumberOfDilutedSharesOutstanding", "shares", {**a, "val": 200e6})
            add("EarningsPerShareDiluted", "USD/shares", {**a, "val": round(annual_rev * 0.14 / 200e6, 2)})
        inst = {"end": e, "fy": fy, "fp": fp, "form": form, "filed": filed}
        add("CashAndCashEquivalentsAtCarryingValue", "USD", {**inst, "val": 800e6 + n * 20e6})
        add("ShortTermInvestments", "USD", {**inst, "val": 300e6})
        add("AccountsReceivableNetCurrent", "USD", {**inst, "val": 400e6})
        add("AssetsCurrent", "USD", {**inst, "val": 1800e6})
        add("LiabilitiesCurrent", "USD", {**inst, "val": 900e6})
        add("Assets", "USD", {**inst, "val": 5000e6})
        add("Liabilities", "USD", {**inst, "val": 2500e6})
        add("StockholdersEquity", "USD", {**inst, "val": 2500e6})
        add("LongTermDebtNoncurrent", "USD", {**inst, "val": 700e6})
        add("LongTermDebtCurrent", "USD", {**inst, "val": 50e6})
        add("EntityCommonStockSharesOutstanding", "shares", {**inst, "val": 190e6 + n * 1e6}, "dei")
    last_10k_end = "2025-12-31"
    for i, tag in enumerate(["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths", "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
                             "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree"]):
        add(tag, "USD", {"end": last_10k_end, "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2026-02-05", "val": [50e6, 200e6, 500e6][i]})
    return {"cik": CIK, "entityName": "TESTCO INC", "facts": facts}


def earnings_dates(start_year=2019, end: date = date(2026, 11, 5)) -> list[date]:
    out = []
    d = date(start_year, 2, 5)
    while d <= end:
        out.append(d)
        d = d + timedelta(days=91)
    return out


def submissions(today: date = date(2026, 11, 14)) -> dict:
    rows = []
    for d in earnings_dates():
        rows.append(("8-K", d.isoformat(), f"{d.isoformat()}T16:05:12.000Z", "2.02,9.01", "ex991.htm"))
    rows.append(("8-K", (today - timedelta(days=5)).isoformat(), f"{(today - timedelta(days=5)).isoformat()}T08:00:00.000Z", "4.01,9.01", "auditor.htm"))
    rows.append(("8-K", (today - timedelta(days=60)).isoformat(), "", "5.02", "exec.htm"))
    rows.append(("S-3", (today - timedelta(days=200)).isoformat(), "", "", "s3.htm"))
    rows.append(("4", (today - timedelta(days=20)).isoformat(), "", "", "xslF345X05/form4.xml"))
    rows.sort(key=lambda r: r[1], reverse=True)
    recent = {k: [] for k in ("accessionNumber", "filingDate", "acceptanceDateTime", "form", "items", "primaryDocument", "reportDate")}
    for i, (form, fd, acc_t, items, doc) in enumerate(rows):
        recent["accessionNumber"].append(f"0009999999-26-{i:06d}")
        recent["filingDate"].append(fd)
        recent["acceptanceDateTime"].append(acc_t)
        recent["form"].append(form)
        recent["items"].append(items)
        recent["primaryDocument"].append(doc)
        recent["reportDate"].append("")
    return {"cik": str(CIK), "name": "TESTCO INC", "sic": "7372", "sicDescription": "Services-Prepackaged Software",
            "tickers": ["TSTC"], "exchanges": ["Nasdaq"], "fiscalYearEnd": "1231", "filings": {"recent": recent, "files": []}}


FORM4_XML = b"""<?xml version="1.0"?>
<ownershipDocument>
  <aff10b5One>1</aff10b5One>
  <reportingOwner><reportingOwnerId><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>Chief Executive Officer</officerTitle></reportingOwnerRelationship></reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction><transactionDate><value>2026-10-20</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>10000</value></transactionShares><transactionPricePerShare><value>50.5</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction><transactionDate><value>2026-10-21</value></transactionDate>
      <transactionCoding><transactionCode>F</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>2000</value></transactionShares><transactionPricePerShare><value>51</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def tickers_json() -> dict:
    return {"fields": ["cik", "name", "ticker", "exchange"], "data": [[CIK, "TESTCO INC", "TSTC", "Nasdaq"], [1, "OTHER", "OTHR", "OTC"]]}


def prices(seed: int = 1, start="2019-01-02", end="2026-11-13", drift=0.0004) -> pd.DataFrame:
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, 0.02, len(idx))
    close = 40 * np.exp(np.cumsum(r))
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close, "volume": rng.integers(1e6, 2e6, len(idx))}, index=idx)
    return df


class FakePrices:
    name = "TEST prices"

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames

    def history(self, symbol, years):
        return self.frames.get(symbol)


def seed_cache(store) -> None:
    """Pre-populate the HTTP cache so EdgarProvider never touches the network in tests."""
    store.cache_put("edgar|https://www.sec.gov/files/company_tickers_exchange.json?", 200, json.dumps(tickers_json()).encode())
    store.cache_put(f"edgar|https://data.sec.gov/submissions/CIK{CIK:010d}.json?", 200, json.dumps(submissions()).encode())
    store.cache_put(f"edgar|https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK:010d}.json?", 200, json.dumps(companyfacts()).encode())
    sub = submissions()
    rec = sub["filings"]["recent"]
    i = rec["form"].index("4")
    acc = rec["accessionNumber"][i].replace("-", "")
    store.cache_put(f"edgar|https://www.sec.gov/Archives/edgar/data/{CIK}/{acc}/form4.xml?", 200, FORM4_XML)
