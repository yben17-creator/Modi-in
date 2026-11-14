// Port of python/evi/analytics/metrics.py — deterministic CALC-layer values. Missing input → missing output.
import { calc, missing, ok, v, type Val } from "./types.ts";
import type { Period } from "./xbrl.ts";

export interface CompanyInput {
  fin: Record<string, Val>;
  annual: Record<string, Period[]>;
  quarterly: Record<string, Period[]>;
  price: Val;
  quoteMeta: Record<string, Val>; // high52, low52, ret1y, ret3m
  nextEarnings?: { date?: string | null; source?: string; basis?: string; eps_est?: number | null } | null;
  today?: string; // ISO date; defaults to now
}

const div = (a: number | null, b: number | null) => (a === null || b === null || b === 0 ? null : a / b);
const toDay = (s: string) => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 86400000;

export function computeMetrics(cd: CompanyInput): Record<string, Val> {
  const f = (k: string): Val => cd.fin[k] ?? missing("לא נמצא בדיווחי XBRL");
  const m: Record<string, Val> = {};
  const price = cd.price, shOut = f("shares_outstanding");
  const cash = f("cash"), sti = f("st_investments"), std = f("st_debt"), ltd = f("lt_debt");
  const rev = f("revenue"), revPrev = f("revenue_prev");

  m["mcap"] = calc(ok(price) && ok(shOut) ? price.value * shOut.value : null, "מחיר × מניות במחזור", [price, shOut]);
  // Untagged component with cash reported → 0 (it does not exist). A STALE component (reported before, absent now)
  // is not assumed to be 0: the total is computed without it and flagged as possibly understated.
  const zero: string[] = [];
  const stale = (x: Val) => !ok(x) && x.note.startsWith("ישן:");
  const part = (x: Val, he: string): number | null => {
    if (ok(x)) return x.value;
    if (!ok(cash)) return null;
    zero.push(stale(x) ? `${he} לא דווח בדוח האחרון (דווח בעבר) — ייתכן שהסכום חסר` : `${he} לא דווח → 0`);
    return 0;
  };
  const stiV = part(sti, "השקעות קצרות");
  const stdV = part(std, "חוב קצר");
  const ltdV = part(ltd, "חוב ארוך");
  const note = zero.join("; ");
  m["cash_all"] = calc(ok(cash) && stiV !== null ? cash.value + stiV : null, "מזומן + השקעות לזמן קצר", [cash], note);
  m["total_debt"] = calc(stdV !== null && ltdV !== null ? stdV + ltdV : null, "חוב קצר + חוב ארוך", [cash], note);
  m["net_debt"] = calc(ok(m["total_debt"]) && ok(m["cash_all"]) ? m["total_debt"].value - m["cash_all"].value : null,
    "חוב כולל − מזומן והשקעות", [m["total_debt"], m["cash_all"]], note);
  m["ev"] = calc(ok(m["mcap"]) && ok(m["net_debt"]) ? m["mcap"].value + m["net_debt"].value : null, "שווי שוק + חוב נטו", [m["mcap"], m["net_debt"]]);
  const eq = f("equity");
  m["equity"] = eq;

  const ocf = f("ocf"), capex = f("capex"), sbc = f("sbc"), ni = f("net_income"), opi = f("operating_income");
  m["revenue"] = rev;
  m["fcf"] = calc(ok(ocf) && ok(capex) ? ocf.value - capex.value : null, "תזרים מפעילות − CapEx", [ocf, capex]);
  m["fcf_prev"] = calc(ok(f("ocf_prev")) && ok(f("capex_prev")) ? f("ocf_prev").value! - f("capex_prev").value! : null, "FCF שנה קודמת",
    [f("ocf_prev"), f("capex_prev")]);
  m["adj_fcf"] = calc(ok(m["fcf"]) && ok(sbc) ? m["fcf"].value - sbc.value : null, "FCF − תגמול מבוסס מניות", [m["fcf"], sbc]);
  const da = f("d_and_a");
  m["ebitda"] = calc(ok(opi) && ok(da) ? opi.value + da.value : null, "רווח תפעולי + פחת והפחתות", [opi, da]);

  const ratio = (key: string, a: number | null, b: number | null, label: string, inputs: Val[]) => { m[key] = calc(div(a, b), label, inputs); };
  ratio("current_ratio", v(f("current_assets")), v(f("current_liabilities")), "נכסים שוטפים / התחייבויות שוטפות", [f("current_assets"), f("current_liabilities")]);
  const quickNum = ok(cash) ? cash.value + (stiV ?? 0) + (v(f("receivables")) ?? 0) : null;
  ratio("quick_ratio", quickNum, v(f("current_liabilities")), "(מזומן + השקעות + לקוחות) / התחייבויות שוטפות", [cash, f("current_liabilities")]);
  ratio("debt_to_equity", v(m["total_debt"]), ok(eq) && eq.value > 0 ? eq.value : null, "חוב כולל / הון עצמי", [m["total_debt"], eq]);
  if (ok(m["net_debt"]) && ok(m["ebitda"])) {
    const nd = m["net_debt"].value, e = m["ebitda"].value;
    m["nd_ebitda"] = calc(e > 0 ? nd / e : nd <= 0 ? -Infinity : Infinity, "חוב נטו / EBITDA", [m["net_debt"], m["ebitda"]], e > 0 ? "" : "EBITDA שלילי");
  } else m["nd_ebitda"] = calc(null, "חוב נטו / EBITDA", [m["net_debt"], m["ebitda"]]);
  const ie = f("interest_expense");
  if (ok(opi) && ok(ie) && ie.value > 0) m["coverage"] = calc(opi.value / ie.value, "רווח תפעולי / הוצאות ריבית", [opi, ie]);
  else if (ok(opi) && ok(m["total_debt"]) && m["total_debt"].value === 0) m["coverage"] = { value: Infinity, source: "אין חוב", asOf: null, layer: "CALC", note: "" };
  else m["coverage"] = calc(null, "רווח תפעולי / הוצאות ריבית", [opi, ie], "הוצאות ריבית לא דווחו");
  const margins: [string, Val, string][] = [["gross_margin", f("gross_profit"), "רווח גולמי / הכנסות"], ["op_margin", opi, "רווח תפעולי / הכנסות"],
    ["ebitda_margin", m["ebitda"], "EBITDA / הכנסות"], ["net_margin", ni, "רווח נקי / הכנסות"], ["fcf_margin", m["fcf"], "FCF / הכנסות"],
    ["adj_fcf_margin", m["adj_fcf"], "FCF בניכוי SBC / הכנסות"], ["sbc_pct", sbc, "SBC / הכנסות"]];
  for (const [key, numr, label] of margins) m[key] = calc(div(v(numr), v(rev)), label, [numr, rev]);
  const opiPrev = f("operating_income_prev");
  m["op_margin_prev"] = calc(div(v(opiPrev), v(revPrev)), "מרווח תפעולי שנה קודמת", [opiPrev, revPrev]);
  let taxRate: number | null = null;
  if (ok(f("income_tax")) && ok(f("pretax_income")) && f("pretax_income").value! > 0) {
    taxRate = Math.min(Math.max(f("income_tax").value! / f("pretax_income").value!, 0), 0.35);
  }
  const ic = ok(eq) && ok(m["net_debt"]) ? eq.value + m["net_debt"].value : null;
  const tr = taxRate ?? 0.21;
  m["roic"] = calc(ok(opi) && ic !== null && ic > 0 ? div(opi.value * (1 - tr), ic) : null, "NOPAT / הון מושקע (הון + חוב נטו)",
    [opi, eq, m["net_debt"]], taxRate !== null ? "" : "שיעור מס 21% (סטטוטורי) — מס אפקטיבי לא זמין");

  m["rev_growth_1y"] = calc(ok(rev) && ok(revPrev) && revPrev.value > 0 ? rev.value / revPrev.value - 1 : null, "צמיחת הכנסות שנתית", [rev, revPrev]);
  const ann = cd.annual["revenue"] ?? [];
  const n = ann.length;
  m["rev_cagr_3y"] = calc(n >= 4 && ann[n - 4]!.val > 0 ? (ann[n - 1]!.val / ann[n - 4]!.val) ** (1 / 3) - 1 : null, "CAGR הכנסות 3 שנים (שנים פיסקליות)", [],
    n >= 4 ? "" : "פחות מ-4 שנים פיסקליות");
  m["rev_cagr_5y"] = calc(n >= 6 && ann[n - 6]!.val > 0 ? (ann[n - 1]!.val / ann[n - 6]!.val) ** (1 / 5) - 1 : null, "CAGR הכנסות 5 שנים", [],
    n >= 6 ? "" : "פחות מ-6 שנים פיסקליות");
  const yoy: number[] = [];
  for (let i = Math.max(1, n - 5); i < n; i++) if (ann[i - 1]!.val > 0) yoy.push(ann[i]!.val / ann[i - 1]!.val - 1);
  m["min_yoy"] = calc(yoy.length ? Math.min(...yoy) : null, "צמיחה שנתית מינימלית (עד 5 שנים)", []);
  const fp = v(m["fcf_prev"]);
  m["fcf_growth"] = calc(ok(m["fcf"]) && fp !== null && fp > 0 ? m["fcf"].value / fp - 1 : null, "צמיחת FCF", [m["fcf"], m["fcf_prev"]],
    fp === null || fp > 0 ? "" : "FCF קודם שלילי — צמיחה באחוזים אינה מוגדרת");
  m["cash_conversion"] = calc(ok(ni) && ni.value > 0 ? div(v(m["fcf"]), ni.value) : null, "FCF / רווח נקי", [m["fcf"], ni]);
  const s0 = f("shares_outstanding"), s3 = f("shares_outstanding_3y");
  m["dilution_rate"] = calc(ok(s0) && ok(s3) && s3.value > 0 ? (s0.value / s3.value) ** (1 / 3) - 1 : null, "שינוי שנתי במספר המניות (3 שנים)", [s0, s3]);
  m["fcf_yield"] = calc(div(v(m["fcf"]), v(m["mcap"])), "FCF / שווי שוק", [m["fcf"], m["mcap"]]);
  m["adj_fcf_yield"] = calc(div(v(m["adj_fcf"]), v(m["mcap"])), "FCF בניכוי SBC / שווי שוק", [m["adj_fcf"], m["mcap"]]);
  const burn = ok(m["fcf"]) && m["fcf"].value < 0 ? -m["fcf"].value : null;
  m["runway_years"] = calc(burn !== null && ok(m["cash_all"]) ? m["cash_all"].value / burn : ok(m["fcf"]) && m["fcf"].value >= 0 ? Infinity : null,
    "מזומן / שריפת מזומנים שנתית", [m["cash_all"], m["fcf"]]);

  const epsQ = cd.quarterly["eps_diluted"] ?? [];
  const epsTtm = epsQ.length >= 4 ? epsQ.slice(-4).reduce((s, x) => s + x.val, 0) : null;
  m["eps_ttm"] = epsTtm !== null
    ? { value: epsTtm, source: "SEC EDGAR · EPS מדולל, 4 רבעונים אחרונים", asOf: epsQ.at(-1)!.end, layer: "CALC", note: "" }
    : missing("אין 4 רבעוני EPS מדווחים");
  const ne = cd.nextEarnings ?? {};
  m["fwd_eps"] = ne.eps_est !== null && ne.eps_est !== undefined
    ? { value: Number(ne.eps_est) * 4, source: `${ne.source ?? ""} · EPS רבעון הבא × 4 (קירוב)`, asOf: ne.date ?? null, layer: "CALC", note: "קירוב: קונצנזוס הרבעון הבא כפול 4" }
    : missing("אין קונצנזוס EPS (דורש Finnhub)");
  const mult = (key: string, num: Val, den: Val, label: string) => {
    const a = v(num), b = v(den);
    m[key] = calc(a !== null && b !== null && b > 0 ? a / b : null, label, [num, den], b === null || b > 0 ? "" : "מכנה שלילי — מכפיל לא משמעותי");
  };
  mult("pe", price, m["eps_ttm"], "מחיר / EPS 12 חודשים");
  mult("fpe", price, m["fwd_eps"], "מחיר / EPS צפוי (שנתי)");
  mult("ev_rev", m["ev"], rev, "EV / הכנסות");
  mult("ev_ebitda", m["ev"], m["ebitda"], "EV / EBITDA");
  mult("ev_fcf", m["ev"], m["fcf"], "EV / FCF");
  mult("p_fcf", m["mcap"], m["fcf"], "שווי שוק / FCF");
  mult("ps", m["mcap"], rev, "שווי שוק / הכנסות");

  const hi = cd.quoteMeta["high52"] ?? missing("חסר");
  m["drawdown"] = calc(ok(price) && ok(hi) && hi.value > 0 ? 1 - price.value / hi.value : null, "ירידה מהשיא השנתי", [price, hi]);
  m["ret1y"] = cd.quoteMeta["ret1y"] ?? missing("חסר");
  m["ret3m"] = cd.quoteMeta["ret3m"] ?? missing("חסר");
  const today = cd.today ?? new Date().toISOString().slice(0, 10);
  m["days_to_earnings"] = ne.date
    ? { value: toDay(ne.date) - toDay(today), source: ne.source ?? "", asOf: ne.date, layer: "CALC", note: "" }
    : missing(ne.basis ?? "אין תאריך דוח");
  return m;
}
