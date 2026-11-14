// Port of python/evi/providers/xbrl.py — extract standardized fundamentals from SEC XBRL `companyfacts` JSON.
// Rules (identical to the Python reference):
//  * concepts map to ordered us-gaap tag lists; series are merged by period end, earlier tag wins
//  * flows → discrete quarters: direct 3-month facts, YTD differences (same start), Q4 = FY − 3 quarters
//  * TTM = last 4 contiguous quarters; else latest fiscal year (labeled)
//  * nothing estimated: tag not found → missing
import { missing, type Val } from "./types.ts";

const SRC = "SEC EDGAR XBRL";

export const FLOW_TAGS: Record<string, string[]> = {
  revenue: ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet", "SalesRevenueServicesNet"],
  cost_of_revenue: ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices"],
  gross_profit: ["GrossProfit"],
  operating_income: ["OperatingIncomeLoss"],
  net_income: ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
  d_and_a: ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization", "Depreciation"],
  interest_expense: ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense"],
  ocf: ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
  capex: ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "PaymentsForCapitalImprovements"],
  sbc: ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
  buyback_paid: ["PaymentsForRepurchaseOfCommonStock"],
  pretax_income: ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
  income_tax: ["IncomeTaxExpenseBenefit"],
};

export const INSTANT_TAGS: Record<string, string[]> = {
  total_assets: ["Assets"],
  total_liabilities: ["Liabilities"],
  liabilities_and_equity: ["LiabilitiesAndStockholdersEquity"],
  equity: ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
  cash: ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash"],
  st_investments: ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    "ShortTermInvestmentsAndMarketableSecurities"],
  receivables: ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
  inventory: ["InventoryNet"],
  current_assets: ["AssetsCurrent"],
  current_liabilities: ["LiabilitiesCurrent"],
  st_debt: ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings", "ConvertibleNotesPayableCurrent",
    "LongTermDebtAndCapitalLeaseObligationsCurrent", "ConvertibleDebtCurrent"],
  lt_debt_noncurrent: ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "ConvertibleNotesPayableNoncurrent",
    "ConvertibleDebtNoncurrent", "SeniorNotesNoncurrent", "ConvertibleSeniorNotesNoncurrent"],
  lt_debt_total: ["LongTermDebt", "DebtInstrumentCarryingAmount"],
  convertible_debt: ["ConvertibleDebtNoncurrent", "ConvertibleNotesPayableNoncurrent", "ConvertibleSeniorNotesNoncurrent",
    "ConvertibleNotesPayable", "ConvertibleDebt"],
  buyback_remaining: ["StockRepurchaseProgramRemainingAuthorizedRepurchaseAmount1"],
  options_outstanding: ["ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingNumber"],
  rsu_outstanding: ["ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsNonvestedNumber"],
};

const MATURITY_TAGS: [string, number][] = [
  ["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths", 1],
  ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo", 2],
  ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree", 3],
  ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour", 4],
  ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive", 5],
  ["LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive", 6],
];

export interface Fact { start?: string | undefined; end: string; val: number; filed?: string | undefined; form?: string | undefined; fy?: number | undefined; fp?: string | undefined; tag: string }
export interface Period { start?: string | undefined; end: string; val: number; tag: string; how?: string | undefined; filed?: string | undefined; form?: string | undefined }

// deno-lint-ignore no-explicit-any
type CompanyFacts = any;

const toDay = (s: string) => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 86400000;
const days = (r: { start?: string | undefined; end: string }): number | null => (r.start ? toDay(r.end) - toDay(r.start) : null);

function units(cf: CompanyFacts, tag: string, taxonomy = "us-gaap"): Record<string, Fact[]> {
  return cf?.facts?.[taxonomy]?.[tag]?.units ?? {};
}
function rows(cf: CompanyFacts, tag: string, unit = "USD", taxonomy = "us-gaap"): Fact[] {
  return (units(cf, tag, taxonomy)[unit] ?? []).filter((r: Fact) => "val" in r && "end" in r).map((r: Fact) => ({ ...r, tag }));
}
// Python: max(rows, key=(filed, form != "10-K/A")) — later filing wins; ties prefer non-amendment.
function latestFiled<T extends { filed?: string | undefined; form?: string | undefined }>(rs: T[]): T {
  let best = rs[0]!;
  for (const r of rs.slice(1)) {
    const a = r.filed ?? "", b = best.filed ?? "";
    if (a > b || (a === b && (r.form !== "10-K/A") && best.form === "10-K/A")) best = r;
  }
  return best;
}
const sortedKeys = (o: Record<string, unknown>) => Object.keys(o).sort();

export function annualSeries(cf: CompanyFacts, tags: string[], unit = "USD"): Period[] {
  const merged: Record<string, Period> = {};
  for (const tag of tags) {
    const byEnd: Record<string, Fact[]> = {};
    for (const r of rows(cf, tag, unit)) {
      const dd = days(r);
      if (dd !== null && dd >= 350 && dd <= 380) (byEnd[r.end] ??= []).push(r);
    }
    for (const [end, rs] of Object.entries(byEnd)) {
      if (!(end in merged)) {
        const b = latestFiled(rs);
        merged[end] = { end, start: b.start, val: Number(b.val), tag, filed: b.filed, form: b.form };
      }
    }
  }
  return sortedKeys(merged).map((k) => merged[k]!);
}

export function quarterlySeries(cf: CompanyFacts, tags: string[], unit = "USD"): Period[] {
  const merged: Record<string, Period> = {};
  for (const tag of tags) {
    const all = rows(cf, tag, unit).filter((r) => r.start);
    if (!all.length) continue;
    const uniq: Record<string, Fact> = {};
    for (const r of all) {
      const k = `${r.start}|${r.end}`;
      if (!(k in uniq) || (r.filed ?? "") > (uniq[k]!.filed ?? "")) uniq[k] = r;
    }
    const rs = Object.values(uniq);
    const q: Record<string, Period> = {};
    // 1) direct 3-month values
    for (const r of rs) {
      const dd = days(r)!;
      if (dd >= 80 && dd <= 100) q[r.end] = { start: r.start, end: r.end, val: Number(r.val), tag, how: "direct" };
    }
    // 2) YTD differences with the same start
    const byStart: Record<string, Fact[]> = {};
    for (const r of rs) {
      const dd = days(r)!;
      if (dd >= 80 && dd <= 380) (byStart[r.start!] ??= []).push(r);
    }
    for (const group of Object.values(byStart)) {
      group.sort((a, b) => (a.end < b.end ? -1 : a.end > b.end ? 1 : 0));
      for (let i = 1; i < group.length; i++) {
        const prev = group[i - 1]!, cur = group[i]!;
        const diff = days(cur)! - days(prev)!;
        if (diff >= 80 && diff <= 100 && !(cur.end in q)) {
          q[cur.end] = { start: prev.end, end: cur.end, val: Number(cur.val) - Number(prev.val), tag, how: "ytd-diff" };
        }
      }
    }
    // 3) missing quarter = fiscal year − three quarters inside it
    for (const r of rs) {
      const dd = days(r)!;
      if (!(dd >= 350 && dd <= 380) || r.end in q) continue;
      const inside = Object.values(q).filter((x) => (x.start ?? "") >= r.start! && x.end < r.end)
        .sort((a, b) => (a.end < b.end ? -1 : 1));
      if (inside.length === 3) {
        q[r.end] = { start: inside[2]!.end, end: r.end, val: Number(r.val) - inside.reduce((s, x) => s + x.val, 0), tag, how: "fy-minus-3q" };
      }
    }
    for (const [end, item] of Object.entries(q)) if (!(end in merged)) merged[end] = item;
  }
  return sortedKeys(merged).map((k) => merged[k]!);
}

export function ttm(quarters: Period[], offset = 0): { value: number | null; end: string | null; note: string } {
  if (quarters.length < 4 + offset) return { value: null, end: null, note: "פחות מ-4 רבעונים רציפים" };
  const w = quarters.slice(quarters.length - 4 - offset, quarters.length - offset);
  for (let i = 1; i < w.length; i++) {
    const gap = w[i]!.start ? toDay(w[i]!.start!) - toDay(w[i - 1]!.end) : 999;
    if (gap > 12 || gap < -12) return { value: null, end: null, note: "רבעונים לא רציפים" };
  }
  return { value: w.reduce((s, x) => s + x.val, 0), end: w[3]!.end, note: "TTM" };
}

export function instantLatest(cf: CompanyFacts, tags: string[], unit = "USD", taxonomy = "us-gaap"): Fact | null {
  let best: Fact | null = null;
  for (const tag of tags) {
    const rs = rows(cf, tag, unit, taxonomy).filter((r) => !r.start);
    if (!rs.length) continue;
    const end = rs.map((r) => r.end).sort().at(-1)!;
    const cand = latestFiled(rs.filter((r) => r.end === end));
    if (best === null || cand.end > best.end) best = cand;
  }
  return best;
}

export function instantSeries(cf: CompanyFacts, tags: string[], unit = "USD", taxonomy = "us-gaap"): Period[] {
  const merged: Record<string, Period> = {};
  for (const tag of tags) {
    const byEnd: Record<string, Fact[]> = {};
    for (const r of rows(cf, tag, unit, taxonomy)) if (!r.start) (byEnd[r.end] ??= []).push(r);
    for (const [end, rs] of Object.entries(byEnd)) {
      if (!(end in merged)) { const b = latestFiled(rs); merged[end] = { end, val: Number(b.val), tag, filed: b.filed }; }
    }
  }
  return sortedKeys(merged).map((k) => merged[k]!);
}

// ---- stock splits: a jump between consecutive share counts that matches a split ratio within 4%
const SPLIT_FACTORS = [1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 30, 40, 50];
export interface SplitEvent { date: string; factor: number }

export function adjustForSplits(series: Period[]): { series: Period[]; splits: SplitEvent[] } {
  const out = series.map((p) => ({ ...p }));
  const splits: SplitEvent[] = [];
  for (let i = 1; i < out.length; i++) {
    const prev = out[i - 1]!, cur = out[i]!;
    if (!(prev.val > 0) || !(cur.val > 0)) continue;
    const r = cur.val / prev.val;
    const probe = r >= 1.4 ? r : r <= 0.7 ? 1 / r : 0;
    if (!probe) continue;
    const k = SPLIT_FACTORS.reduce((b, f) => (Math.abs(probe / f - 1) < Math.abs(probe / b - 1) ? f : b), SPLIT_FACTORS[0]!);
    if (Math.abs(probe / k - 1) > 0.04) continue;
    const factor = r >= 1 ? k : 1 / k;
    for (let j = 0; j < i; j++) out[j]!.val *= factor;
    splits.push({ date: cur.end, factor });
  }
  return { series: out, splits };
}

const BALANCE_SHEET_KEYS = ["cash", "st_investments", "receivables", "inventory", "current_assets", "current_liabilities",
  "st_debt", "lt_debt_noncurrent", "lt_debt_total", "convertible_debt", "total_liabilities", "equity"];
export const STALE_PREFIX = "ישן:";

export interface Extracted {
  fin: Record<string, Val>;
  annual: Record<string, Period[]>;
  quarterly: Record<string, Period[]>;
  maturities: { year: number | string; amount: number; tag: string }[];
  maturitiesAsOf: string | null;
  gaps: string[];
  splits: SplitEvent[];
}

export function extract(cf: CompanyFacts, fetched: string | null = null): Extracted {
  const fin: Record<string, Val> = {};
  const annual: Record<string, Period[]> = {};
  const quarterly: Record<string, Period[]> = {};
  const gaps: string[] = [];
  const g = (k: string): Val => fin[k] ?? missing("לא נמצא", SRC);
  const put = (key: string, value: number | null, end: string | null, tag: string | null, note = "") => {
    fin[key] = value === null ? missing(note || "לא נמצא תג XBRL מתאים", SRC)
      : { value, source: `${SRC} · ${tag}`, asOf: end, layer: "RAW", note, fetched };
  };

  for (const [key, tags] of Object.entries(FLOW_TAGS)) {
    const qs = quarterlySeries(cf, tags), ann = annualSeries(cf, tags);
    quarterly[key] = qs; annual[key] = ann;
    const cur = ttm(qs), prev = ttm(qs, 4);
    if (cur.value !== null) {
      put(key, cur.value, cur.end, qs.at(-1)!.tag, cur.note);
      put(key + "_prev", prev.value, prev.end, prev.value !== null ? qs.at(-5)!.tag : null,
        prev.value !== null ? "TTM שנה קודמת" : "אין 8 רבעונים רציפים");
    } else if (ann.length) {
      const a = ann.at(-1)!;
      put(key, a.val, a.end, a.tag, "שנה פיסקלית אחרונה (TTM לא זמין)");
      if (ann.length > 1) { const p = ann.at(-2)!; put(key + "_prev", p.val, p.end, p.tag, "שנה פיסקלית קודמת"); }
      else put(key + "_prev", null, null, null, "אין שנה קודמת");
    } else { put(key, null, null, null); put(key + "_prev", null, null, null); }
  }

  const rv = g("revenue"), cr = g("cost_of_revenue");
  if (g("gross_profit").value === null && rv.value !== null && cr.value !== null && rv.asOf === cr.asOf) {
    fin["gross_profit"] = { value: rv.value - cr.value, source: `${SRC} · Revenue − CostOfRevenue`, asOf: rv.asOf, layer: "CALC", note: "", fetched };
  }

  for (const [key, tags] of Object.entries(INSTANT_TAGS)) {
    const unit = key === "options_outstanding" || key === "rsu_outstanding" ? "shares" : "USD";
    const r = instantLatest(cf, tags, unit);
    put(key, r ? Number(r.val) : null, r ? r.end : null, r ? r.tag : null);
  }
  // a balance-sheet component last reported well before the latest balance sheet is stale: do not mix periods
  const ref = g("total_assets").asOf ?? g("current_assets").asOf;
  if (ref) {
    for (const k of BALANCE_SHEET_KEYS) {
      const cur = g(k);
      if (cur.value !== null && cur.asOf && toDay(ref) - toDay(cur.asOf) > 100) {
        fin[k] = missing(`${STALE_PREFIX} הערך האחרון מדווח ל-${cur.asOf}, ישן מתאריך המאזן ${ref} — לא נכלל`, SRC);
      }
    }
  }
  const le = g("liabilities_and_equity"), eq = g("equity");
  if (g("total_liabilities").value === null && le.value !== null && eq.value !== null && le.asOf === eq.asOf) {
    fin["total_liabilities"] = { value: le.value - eq.value, source: `${SRC} · LiabilitiesAndStockholdersEquity − StockholdersEquity`,
      asOf: eq.asOf, layer: "CALC", note: "", fetched };
  }
  if (g("lt_debt_noncurrent").value !== null) fin["lt_debt"] = g("lt_debt_noncurrent");
  else if (g("lt_debt_total").value !== null) {
    const t = g("lt_debt_total"), s = g("st_debt");
    const cur = s.value !== null && s.asOf === t.asOf ? s.value : 0;
    fin["lt_debt"] = { value: t.value! - cur, source: t.source + " − חלות שוטפת", asOf: t.asOf, layer: "CALC", note: "", fetched };
  } else fin["lt_debt"] = missing("לא דווח חוב לזמן ארוך בתגי XBRL (ייתכן שאין חוב)", SRC);

  // shares
  const soRaw = instantSeries(cf, ["EntityCommonStockSharesOutstanding"], "shares", "dei");
  const { series: so, splits } = adjustForSplits(soRaw);
  const splitNote = splits.length ? `מותאם לפיצול מניות: ${splits.map((x) => `${x.factor >= 1 ? x.factor : "1/" + Math.round(1 / x.factor)}:1 ב-${x.date}`).join(", ")}` : "";
  if (so.length) {
    const last = so.at(-1)!;
    fin["shares_outstanding"] = { value: last.val, source: `${SRC} · dei:EntityCommonStockSharesOutstanding`, asOf: last.end, layer: "RAW", note: "", fetched };
    const target = toDay(last.end) - 3 * 365;
    const old = so.reduce((b, r) => (Math.abs(toDay(r.end) - target) < Math.abs(toDay(b.end) - target) ? r : b), so[0]!);
    fin["shares_outstanding_3y"] = Math.abs(toDay(old.end) - target) <= 120
      ? { value: old.val, source: `${SRC} · dei:EntityCommonStockSharesOutstanding`, asOf: old.end, layer: splits.length ? "CALC" : "RAW", note: splitNote, fetched }
      : missing("אין נתון מניות מלפני ~3 שנים", SRC);
  } else {
    fin["shares_outstanding"] = missing("dei:EntityCommonStockSharesOutstanding חסר", SRC);
    fin["shares_outstanding_3y"] = missing("אין היסטוריית מניות", SRC);
  }
  const dil = quarterlySeries(cf, ["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares").filter((q) => q.how === "direct");
  if (dil.length) {
    const d = dil.at(-1)!;
    fin["diluted_shares"] = { value: d.val, source: `${SRC} · WeightedAverageNumberOfDilutedSharesOutstanding (רבעוני)`, asOf: d.end, layer: "RAW", note: "", fetched };
  } else {
    const da = annualSeries(cf, ["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares");
    fin["diluted_shares"] = da.length
      ? { value: da.at(-1)!.val, source: `${SRC} · WeightedAverageNumberOfDilutedSharesOutstanding (שנתי)`, asOf: da.at(-1)!.end, layer: "RAW", note: "", fetched }
      : missing("מניות בדילול מלא חסרות", SRC);
  }
  annual["diluted_shares"] = annualSeries(cf, ["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares");
  annual["shares_outstanding"] = so;

  // EPS quarterly (diluted)
  let eps: Period[] = [];
  for (const tag of ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"]) {
    for (const r of rows(cf, tag, "USD/shares")) {
      const dd = days(r);
      if (dd !== null && dd >= 80 && dd <= 100) eps.push({ end: r.end, val: Number(r.val), filed: r.filed, tag });
    }
    if (eps.length) break;
  }
  const ded: Record<string, Period> = {};
  for (const r of eps) if (!(r.end in ded) || (r.filed ?? "") > (ded[r.end]!.filed ?? "")) ded[r.end] = r;
  eps = sortedKeys(ded).map((k) => ded[k]!);
  quarterly["eps_diluted"] = eps;

  for (const key of ["cash", "st_investments", "st_debt", "lt_debt_noncurrent", "lt_debt_total", "equity"]) {
    annual[key + "_instant"] = instantSeries(cf, INSTANT_TAGS[key]!);
  }

  // debt maturities (latest 10-K)
  const maturities: Extracted["maturities"] = [];
  let latestEnd: string | null = null;
  for (const [tag] of MATURITY_TAGS) {
    const r = instantLatest(cf, [tag]);
    if (r && (latestEnd === null || r.end >= latestEnd)) latestEnd = r.end;
  }
  if (latestEnd) {
    const baseYear = +latestEnd.slice(0, 4);
    for (const [tag, n] of MATURITY_TAGS) {
      const rs = rows(cf, tag).filter((x) => !x.start && x.end === latestEnd);
      if (rs.length) maturities.push({ year: n <= 5 ? baseYear + n : `${baseYear + 6}+`, amount: Number(latestFiled(rs).val), tag });
    }
  }
  if (!maturities.length) gaps.push("לוח פירעונות חוב לא דווח ב-XBRL");
  for (const k of ["revenue", "operating_income", "net_income", "ocf", "capex", "cash", "current_assets", "current_liabilities", "equity"]) {
    if (g(k).value === null) gaps.push(`${k}: ${g(k).note}`);
  }
  return { fin, annual, quarterly, maturities, maturitiesAsOf: latestEnd, gaps, splits };
}
