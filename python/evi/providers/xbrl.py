"""Extract standardized fundamentals from SEC XBRL `companyfacts` JSON.

Rules:
* Each concept has an ordered list of us-gaap tags; companies switch tags over time, so series are merged by
  period end date, preferring the earlier tag in the list.
* Flow items (revenue, cash flow) are turned into discrete quarters: directly reported 3-month values, or
  differences between year-to-date values with the same start date, or Q4 = FY − (Q1+Q2+Q3).
* TTM = sum of the last 4 contiguous quarters; if not available, the latest fiscal year is used and labeled.
* Nothing is estimated or filled: if no tag is found, the value is missing.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from ..models import Val, missing

SRC = "SEC EDGAR XBRL"

FLOW_TAGS: dict[str, list[str]] = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet", "SalesRevenueServicesNet"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "d_and_a": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization",
                "Depreciation"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "buyback_paid": ["PaymentsForRepurchaseOfCommonStock"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "income_tax": ["IncomeTaxExpenseBenefit"],
}
INSTANT_TAGS: dict[str, list[str]] = {
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "liabilities_and_equity": ["LiabilitiesAndStockholdersEquity"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash"],
    "st_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
                       "ShortTermInvestmentsAndMarketableSecurities"],
    "receivables": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
    "inventory": ["InventoryNet"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "st_debt": ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings", "ConvertibleNotesPayableCurrent",
                "LongTermDebtAndCapitalLeaseObligationsCurrent", "ConvertibleDebtCurrent"],
    "lt_debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "ConvertibleNotesPayableNoncurrent",
                           "ConvertibleDebtNoncurrent", "SeniorNotesNoncurrent", "ConvertibleSeniorNotesNoncurrent"],
    "lt_debt_total": ["LongTermDebt", "DebtInstrumentCarryingAmount"],
    "convertible_debt": ["ConvertibleDebtNoncurrent", "ConvertibleNotesPayableNoncurrent", "ConvertibleSeniorNotesNoncurrent",
                         "ConvertibleNotesPayable", "ConvertibleDebt"],
    "buyback_remaining": ["StockRepurchaseProgramRemainingAuthorizedRepurchaseAmount1"],
    "options_outstanding": ["ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingNumber"],
    "rsu_outstanding": ["ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsNonvestedNumber"],
}
MATURITY_TAGS = [
    ("LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths", 1),
    ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo", 2),
    ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree", 3),
    ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour", 4),
    ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive", 5),
    ("LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive", 6),
]
SHARE_UNITS = ("shares",)


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def _days(r: dict) -> int | None:
    if not r.get("start"):
        return None
    return (_d(r["end"]) - _d(r["start"])).days


def _units(cf: dict, tag: str, taxonomy: str = "us-gaap") -> dict[str, list[dict]]:
    try:
        return cf["facts"][taxonomy][tag]["units"]
    except (KeyError, TypeError):
        return {}


def _rows(cf: dict, tag: str, unit: str = "USD", taxonomy: str = "us-gaap") -> list[dict]:
    return [dict(r, tag=tag) for r in _units(cf, tag, taxonomy).get(unit, []) if "val" in r and "end" in r]


def _latest_filed(rows: list[dict]) -> dict:
    return max(rows, key=lambda r: (r.get("filed", ""), r.get("form", "") != "10-K/A"))


# ------------------------------------------------------------------ series builders
def annual_series(cf: dict, tags: list[str], unit: str = "USD") -> list[dict]:
    """Fiscal-year flows (duration 350–380 days) merged by end date. Returns oldest→newest."""
    merged: dict[str, dict] = {}
    for tag in tags:
        by_end: dict[str, list[dict]] = {}
        for r in _rows(cf, tag, unit):
            dd = _days(r)
            if dd is not None and 350 <= dd <= 380:
                by_end.setdefault(r["end"], []).append(r)
        for end, rs in by_end.items():
            if end not in merged:
                best = _latest_filed(rs)
                merged[end] = {"end": end, "start": best["start"], "val": float(best["val"]), "tag": tag,
                               "filed": best.get("filed"), "form": best.get("form")}
    return [merged[k] for k in sorted(merged)]


def quarterly_series(cf: dict, tags: list[str], unit: str = "USD") -> list[dict]:
    """Discrete quarters (≈3 months) merged across tags. Returns oldest→newest."""
    merged: dict[str, dict] = {}
    for tag in tags:
        rows = [r for r in _rows(cf, tag, unit) if r.get("start")]
        if not rows:
            continue
        # dedupe identical (start,end) keeping latest filing
        uniq: dict[tuple[str, str], dict] = {}
        for r in rows:
            k = (r["start"], r["end"])
            if k not in uniq or r.get("filed", "") > uniq[k].get("filed", ""):
                uniq[k] = r
        rows = list(uniq.values())
        q: dict[str, dict] = {}
        # 1) direct 3-month values
        for r in rows:
            dd = _days(r)
            if dd is not None and 80 <= dd <= 100:
                q[r["end"]] = {"start": r["start"], "end": r["end"], "val": float(r["val"]), "tag": tag, "how": "direct"}
        # 2) differences of cumulative values with the same start (YTD)
        by_start: dict[str, list[dict]] = {}
        for r in rows:
            dd = _days(r)
            if dd is not None and 80 <= dd <= 380:
                by_start.setdefault(r["start"], []).append(r)
        for start, rs in by_start.items():
            rs.sort(key=lambda r: r["end"])
            for prev, cur in zip(rs, rs[1:]):
                diff_days = _days(cur) - _days(prev)
                if 80 <= diff_days <= 100 and cur["end"] not in q:
                    q[cur["end"]] = {"start": prev["end"], "end": cur["end"], "val": float(cur["val"]) - float(prev["val"]),
                                     "tag": tag, "how": "ytd-diff"}
        # 3) Q4 (or any single missing quarter) = fiscal year − the three reported quarters inside it
        for r in rows:
            dd = _days(r)
            if dd is None or not (350 <= dd <= 380) or r["end"] in q:
                continue
            inside = sorted([x for x in q.values() if x["start"] >= r["start"] and x["end"] < r["end"]], key=lambda x: x["end"])
            if len(inside) == 3:
                q[r["end"]] = {"start": inside[-1]["end"], "end": r["end"], "val": float(r["val"]) - sum(x["val"] for x in inside),
                               "tag": tag, "how": "fy-minus-3q"}
        for end, item in q.items():
            merged.setdefault(end, item)
    return [merged[k] for k in sorted(merged)]


def ttm(quarters: list[dict], offset: int = 0) -> tuple[float | None, str | None, str]:
    """Sum of 4 contiguous quarters ending `offset` quarters before the latest. Returns (value, end, note)."""
    if len(quarters) < 4 + offset:
        return None, None, "פחות מ-4 רבעונים רציפים"
    window = quarters[len(quarters) - 4 - offset: len(quarters) - offset]
    for a, b in zip(window, window[1:]):
        gap = (_d(b["start"]) - _d(a["end"])).days if b.get("start") else 999
        if gap > 12 or gap < -12:
            return None, None, "רבעונים לא רציפים"
    return sum(x["val"] for x in window), window[-1]["end"], "TTM"


def instant_latest(cf: dict, tags: list[str], unit: str = "USD", taxonomy: str = "us-gaap") -> dict | None:
    best: dict | None = None
    for tag in tags:
        rows = [r for r in _rows(cf, tag, unit, taxonomy) if not r.get("start")]
        if not rows:
            continue
        end = max(r["end"] for r in rows)
        cand = _latest_filed([r for r in rows if r["end"] == end])
        if best is None or cand["end"] > best["end"]:
            best = cand
    return best


def instant_series(cf: dict, tags: list[str], unit: str = "USD", taxonomy: str = "us-gaap") -> list[dict]:
    merged: dict[str, dict] = {}
    for tag in tags:
        by_end: dict[str, list[dict]] = {}
        for r in _rows(cf, tag, unit, taxonomy):
            if not r.get("start"):
                by_end.setdefault(r["end"], []).append(r)
        for end, rs in by_end.items():
            if end not in merged:
                b = _latest_filed(rs)
                merged[end] = {"end": end, "val": float(b["val"]), "tag": tag, "filed": b.get("filed")}
    return [merged[k] for k in sorted(merged)]


# ------------------------------------------------------------------ stock splits / staleness
SPLIT_FACTORS = [1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 30, 40, 50]
BALANCE_SHEET_KEYS = ["cash", "st_investments", "receivables", "inventory", "current_assets", "current_liabilities",
                      "st_debt", "lt_debt_noncurrent", "lt_debt_total", "convertible_debt", "total_liabilities", "equity"]
STALE_PREFIX = "ישן:"


def adjust_for_splits(series: list[dict]) -> tuple[list[dict], list[dict]]:
    """Detect splits as jumps between consecutive share counts matching a split ratio within 4%; restate earlier values."""
    out = [dict(p) for p in series]
    splits = []
    for i in range(1, len(out)):
        prev, cur = out[i - 1], out[i]
        if not (prev["val"] > 0 and cur["val"] > 0):
            continue
        r = cur["val"] / prev["val"]
        probe = r if r >= 1.4 else (1 / r if r <= 0.7 else 0)
        if not probe:
            continue
        k = SPLIT_FACTORS[0]
        for f in SPLIT_FACTORS:
            if abs(probe / f - 1) < abs(probe / k - 1):
                k = f
        if abs(probe / k - 1) > 0.04:
            continue
        factor = k if r >= 1 else 1 / k
        for j in range(i):
            out[j]["val"] *= factor
        splits.append({"date": cur["end"], "factor": factor})
    return out, splits


# ------------------------------------------------------------------ public API
def extract(cf: dict, fetched: str | None = None) -> dict[str, Any]:
    """Return {'fin': {key: Val}, 'annual': {...}, 'quarterly': {...}, 'maturities': [...], 'gaps': [...]}."""
    fin: dict[str, Val] = {}
    annual: dict[str, list[dict]] = {}
    quarterly: dict[str, list[dict]] = {}
    gaps: list[str] = []

    def put_val(key: str, value: float | None, end: str | None, tag: str | None, note: str = "") -> None:
        if value is None:
            fin[key] = missing(note or "לא נמצא תג XBRL מתאים", SRC)
        else:
            fin[key] = Val(value, source=f"{SRC} · {tag}", as_of=end, layer="RAW", note=note, fetched=fetched)

    for key, tags in FLOW_TAGS.items():
        qs = quarterly_series(cf, tags)
        ann = annual_series(cf, tags)
        quarterly[key], annual[key] = qs, ann
        val, end, note = ttm(qs)
        prev, prev_end, _ = ttm(qs, offset=4)
        if val is not None:
            put_val(key, val, end, qs[-1]["tag"], note)
            put_val(key + "_prev", prev, prev_end, qs[-5]["tag"] if prev is not None else None,
                    "TTM שנה קודמת" if prev is not None else "אין 8 רבעונים רציפים")
        elif ann:
            put_val(key, ann[-1]["val"], ann[-1]["end"], ann[-1]["tag"], "שנה פיסקלית אחרונה (TTM לא זמין)")
            if len(ann) > 1:
                put_val(key + "_prev", ann[-2]["val"], ann[-2]["end"], ann[-2]["tag"], "שנה פיסקלית קודמת")
            else:
                put_val(key + "_prev", None, None, None, "אין שנה קודמת")
        else:
            put_val(key, None, None, None)
            put_val(key + "_prev", None, None, None)

    # gross profit fallback: revenue − cost of revenue (same period basis)
    if not fin["gross_profit"].ok and fin["revenue"].ok and fin["cost_of_revenue"].ok \
            and fin["revenue"].as_of == fin["cost_of_revenue"].as_of:
        fin["gross_profit"] = Val(fin["revenue"].value - fin["cost_of_revenue"].value, source=f"{SRC} · Revenue − CostOfRevenue",
                                  as_of=fin["revenue"].as_of, layer="CALC", fetched=fetched)

    for key, tags in INSTANT_TAGS.items():
        unit = "shares" if key in ("options_outstanding", "rsu_outstanding") else "USD"
        r = instant_latest(cf, tags, unit)
        put_val(key, float(r["val"]) if r else None, r["end"] if r else None, r["tag"] if r else None)

    # balance-sheet components last reported well before the latest balance sheet are stale — never mix periods
    ref = fin["total_assets"].as_of or fin["current_assets"].as_of
    if ref:
        for k in BALANCE_SHEET_KEYS:
            cur = fin[k]
            if cur.ok and cur.as_of and (_d(ref) - _d(cur.as_of)).days > 100:
                fin[k] = missing(f"{STALE_PREFIX} הערך האחרון מדווח ל-{cur.as_of}, ישן מתאריך המאזן {ref} — לא נכלל", SRC)

    # liabilities fallback (some filers do not tag total Liabilities)
    if not fin["total_liabilities"].ok and fin["liabilities_and_equity"].ok and fin["equity"].ok \
            and fin["liabilities_and_equity"].as_of == fin["equity"].as_of:
        fin["total_liabilities"] = Val(fin["liabilities_and_equity"].value - fin["equity"].value,
                                       source=f"{SRC} · LiabilitiesAndStockholdersEquity − StockholdersEquity",
                                       as_of=fin["equity"].as_of, layer="CALC", fetched=fetched)

    # long-term debt (non-current): prefer explicit noncurrent tag; else total LTD − current portion (same date)
    if fin["lt_debt_noncurrent"].ok:
        fin["lt_debt"] = fin["lt_debt_noncurrent"]
    elif fin["lt_debt_total"].ok:
        cur = fin["st_debt"].value if fin["st_debt"].ok and fin["st_debt"].as_of == fin["lt_debt_total"].as_of else 0.0
        fin["lt_debt"] = Val(fin["lt_debt_total"].value - cur, source=fin["lt_debt_total"].source + " − חלות שוטפת",
                             as_of=fin["lt_debt_total"].as_of, layer="CALC", fetched=fetched)
    else:
        fin["lt_debt"] = missing("לא דווח חוב לזמן ארוך בתגי XBRL (ייתכן שאין חוב)", SRC)

    # shares
    so, splits = adjust_for_splits(instant_series(cf, ["EntityCommonStockSharesOutstanding"], "shares", "dei"))
    split_note = ("מותאם לפיצול מניות: " + ", ".join(
        f"{x['factor'] if x['factor'] >= 1 else '1/' + str(round(1 / x['factor']))}:1 ב-{x['date']}" for x in splits)) if splits else ""
    if so:
        fin["shares_outstanding"] = Val(so[-1]["val"], source=f"{SRC} · dei:EntityCommonStockSharesOutstanding",
                                        as_of=so[-1]["end"], fetched=fetched)
        target = date.fromordinal(_d(so[-1]["end"]).toordinal() - 3 * 365)
        old = min(so, key=lambda r: abs((_d(r["end"]) - target).days))
        if abs((_d(old["end"]) - target).days) <= 120:
            fin["shares_outstanding_3y"] = Val(old["val"], source=f"{SRC} · dei:EntityCommonStockSharesOutstanding",
                                               as_of=old["end"], layer="CALC" if splits else "RAW", note=split_note, fetched=fetched)
        else:
            fin["shares_outstanding_3y"] = missing("אין נתון מניות מלפני ~3 שנים", SRC)
    else:
        fin["shares_outstanding"] = missing("dei:EntityCommonStockSharesOutstanding חסר", SRC)
        fin["shares_outstanding_3y"] = missing("אין היסטוריית מניות", SRC)
    dil = quarterly_series(cf, ["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares")
    dil_direct = [q for q in dil if q["how"] == "direct"]
    if dil_direct:
        fin["diluted_shares"] = Val(dil_direct[-1]["val"], source=f"{SRC} · WeightedAverageNumberOfDilutedSharesOutstanding (רבעוני)",
                                    as_of=dil_direct[-1]["end"], fetched=fetched)
    else:
        da = annual_series(cf, ["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares")
        fin["diluted_shares"] = Val(da[-1]["val"], source=f"{SRC} · WeightedAverageNumberOfDilutedSharesOutstanding (שנתי)",
                                    as_of=da[-1]["end"], fetched=fetched) if da else missing("מניות בדילול מלא חסרות", SRC)
    annual["diluted_shares"] = annual_series(cf, ["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares")
    for sp in splits:
        post = next((q for q in annual["diluted_shares"] if q["end"] >= sp["date"]), None)
        for p in annual["diluted_shares"]:
            if post and p["end"] < sp["date"] and abs(p["val"] * sp["factor"] / post["val"] - 1) < abs(p["val"] / post["val"] - 1):
                p["val"] *= sp["factor"]
    annual["shares_outstanding"] = so

    # EPS (quarterly, diluted) — reported actuals
    eps_q = []
    for tag in ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"):
        for r in _rows(cf, tag, "USD/shares"):
            dd = _days(r)
            if dd is not None and 80 <= dd <= 100:
                eps_q.append({"end": r["end"], "val": float(r["val"]), "filed": r.get("filed"), "tag": tag})
        if eps_q:
            break
    dedup: dict[str, dict] = {}
    for r in eps_q:
        if r["end"] not in dedup or (r.get("filed") or "") > (dedup[r["end"]].get("filed") or ""):
            dedup[r["end"]] = r
    quarterly["eps_diluted"] = [dedup[k] for k in sorted(dedup)]

    # instant series used for historical multiples
    for key in ("cash", "st_investments", "st_debt", "lt_debt_noncurrent", "lt_debt_total", "equity"):
        annual[key + "_instant"] = instant_series(cf, INSTANT_TAGS[key])

    # debt maturity schedule (from the latest 10-K)
    mats: list[dict] = []
    mat_as_of = None
    latest_end = None
    for tag, _ in MATURITY_TAGS:
        r = instant_latest(cf, [tag])
        if r and (latest_end is None or r["end"] >= latest_end):
            latest_end = r["end"]
    if latest_end:
        base_year = _d(latest_end).year
        for tag, n in MATURITY_TAGS:
            rows = [x for x in _rows(cf, tag) if not x.get("start") and x["end"] == latest_end]
            if rows:
                r = _latest_filed(rows)
                mats.append({"year": base_year + n if n <= 5 else f"{base_year + 6}+", "amount": float(r["val"]), "tag": tag})
        mat_as_of = latest_end
    if not mats:
        gaps.append("לוח פירעונות חוב לא דווח ב-XBRL")

    for k in ("revenue", "operating_income", "net_income", "ocf", "capex", "cash", "current_assets", "current_liabilities", "equity"):
        if not fin[k].ok:
            gaps.append(f"{k}: {fin[k].note}")
    return {"fin": fin, "annual": annual, "quarterly": quarterly, "maturities": mats, "maturities_as_of": mat_as_of, "gaps": gaps,
            "splits": splits}
