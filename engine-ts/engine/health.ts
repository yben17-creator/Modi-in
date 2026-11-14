// Port of python/evi/analytics/scores.py — Score.build + financial health score.
import { ok, v, type Val } from "./types.ts";

export interface Part { label: string; max: number; pts: number | null; basis: string; missing: string }
export interface Score { score: number | null; parts: Record<string, Part>; coverage: number; notes: string[] }

export const part = (label: string, max: number, pts: number | null, basis: string, missingWhy = ""): Part =>
  ({ label, max, pts, basis, missing: pts === null ? missingWhy : "" });

const round1 = (x: number) => Math.round(x * 10) / 10; // Python round(x, 1) — differs only on exact .x5 ties

export function buildScore(parts: Record<string, Part>, minCov: number): Score {
  const avail = Object.values(parts).filter((p) => p.pts !== null);
  const totMax = Object.values(parts).reduce((s, p) => s + p.max, 0);
  const gotMax = avail.reduce((s, p) => s + p.max, 0);
  const cov = totMax ? gotMax / totMax : 0;
  if (cov < minCov || gotMax === 0) {
    return { score: null, parts, coverage: cov, notes: [`כיסוי נתונים ${Math.round(cov * 100)}% — מתחת לסף ${Math.round(minCov * 100)}%; הציון לא חושב`] };
  }
  return { score: round1(100 * avail.reduce((s, p) => s + (p.pts as number), 0) / gotMax), parts, coverage: cov, notes: [] };
}

export interface HealthResult { score: Score; severe: string[]; nearMaturities: number | null }

export function health(m: Record<string, Val>, opIncome: Val, maturities: { year: number | string; amount: number }[],
  minCov = 0.6, currentYear = new Date().getUTCFullYear()): HealthResult {
  const nd = v(m.net_debt), ndE = v(m.nd_ebitda), cr = v(m.current_ratio);
  const om = v(m.op_margin), am = v(m.adj_fcf_margin), cov = v(m.coverage), runway = v(m.runway_years);
  const eq = v(m.equity), opi = v(opIncome), td = v(m.total_debt), ca = v(m.cash_all);
  const p: Record<string, Part> = {};
  if (nd === null) p.balance = part("איתנות מאזן", 20, null, "חוב נטו / EBITDA", "חוב נטו לא ניתן לחישוב");
  else {
    let pts: number;
    if (nd <= 0) pts = 20;
    else if (ndE === null || ndE === Infinity) pts = 0;
    else pts = ndE < 1 ? 16 : ndE < 2 ? 12 : ndE < 3 ? 8 : ndE < 4 ? 4 : 0;
    if (eq !== null && eq <= 0) pts = Math.min(pts, 4);
    p.balance = part("איתנות מאזן", 20, pts, nd <= 0 ? "מזומן נטו" : "חוב נטו / EBITDA");
  }
  p.liquidity = part("נזילות", 15, cr === null ? null : cr >= 2 ? 15 : cr >= 1.5 ? 12 : cr >= 1.2 ? 9 : cr >= 1 ? 6 : 2, "יחס שוטף", "יחס שוטף חסר");
  p.profit = part("רווחיות", 20, om === null ? null : om > 0.25 ? 20 : om > 0.15 ? 16 : om > 0.05 ? 12 : om > 0 ? 8 : om > -0.1 ? 4 : 0,
    "מרווח תפעולי", "מרווח תפעולי חסר");
  p.cash = part("איכות תזרים", 20, am === null ? null : am > 0.2 ? 20 : am > 0.1 ? 16 : am > 0.05 ? 12 : am > 0 ? 8 : am > -0.05 ? 4 : 0,
    "מרווח FCF בניכוי SBC", "FCF או SBC חסרים");
  const mn = v(m.min_yoy), cagr = v(m.rev_cagr_3y);
  if (mn === null) p.stability = part("יציבות הכנסות", 10, null, "צמיחה שנתית", "פחות משנתיים של הכנסות שנתיות");
  else {
    const g = cagr !== null ? cagr : (v(m.rev_growth_1y) || 0);
    p.stability = part("יציבות הכנסות", 10, mn > 0 ? 6 + (g > 0.15 ? 4 : g > 0.05 ? 2 : 0) : g > 0 ? 3 : 0, "צמיחה ומינימום YoY");
  }
  let ds: number | null;
  if (td === 0 || cov === Infinity) ds = 15;
  else if (opi !== null && opi <= 0) ds = runway !== null && runway > 3 && ca !== null && td !== null && ca > td ? 6 : 2;
  else if (cov === null) ds = null;
  else ds = cov > 20 ? 15 : cov > 10 ? 12 : cov > 5 ? 9 : cov > 2 ? 5 : 0;
  p.debt = part("יכולת פירעון", 15, ds, "כיסוי ריבית / runway", "הוצאות ריבית לא דווחו");
  const score = buildScore(p, minCov);
  const severe: string[] = [];
  if (cr !== null && cr < 1 && ndE !== null && ndE > 4) severe.push("נזילות נמוכה לצד מינוף גבוה");
  if (cov !== null && cov < 1.5 && (td || 0) > 0) severe.push("כיסוי ריבית נמוך מ-1.5");
  const fcf = v(m.fcf);
  if (fcf !== null && fcf < 0 && runway !== null && runway < 2) severe.push("תזרים שלילי ו-runway קצר משנתיים");
  let near: number | null = null;
  if (maturities.length) {
    near = maturities.filter((x) => typeof x.year === "number" && x.year <= currentYear + 1).reduce((s, x) => s + x.amount, 0);
    if (ca !== null && near > ca + Math.max(fcf || 0, 0)) severe.push(`פירעונות חוב עד סוף ${currentYear + 1} גבוהים מהמזומן והתזרים`);
  }
  return { score, severe, nearMaturities: near };
}

export { ok };
