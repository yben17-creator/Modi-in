// Parity test: TypeScript engine must reproduce the Python reference outputs on identical inputs.
import { readFileSync } from "node:fs";
import { extract } from "../engine/xbrl.ts";
import { computeMetrics } from "../engine/metrics.ts";
import { health } from "../engine/health.ts";
import type { Val } from "../engine/types.ts";

const cases = JSON.parse(readFileSync(new URL("./parity_cases.json", import.meta.url), "utf8"));
const dec = (x: unknown) => (x === "inf" ? Infinity : x === "-inf" ? -Infinity : x);
const close = (a: unknown, b: unknown) => {
  a = dec(a); b = dec(b);
  if (a === null || b === null || a === undefined || b === undefined) return a === b || (a == null && b == null);
  if (typeof a === "number" && typeof b === "number") return a === b || Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));
  return a === b;
};
let fails = 0, checks = 0;
for (const c of cases) {
  const x = extract(c.cf);
  for (const [k, pv] of Object.entries(c.fin)) { checks++; if (!close(x.fin[k]?.value ?? null, pv)) { fails++; console.log(`[${c.name}] fin.${k}: ts=${x.fin[k]?.value} py=${pv}`); } }
  const price: Val = c.price ? { value: c.price, source: "test", asOf: "2026-11-13", layer: "RAW", note: "" } : { value: null, source: "", asOf: null, layer: "RAW", note: "none" };
  const meta: Record<string, Val> = {};
  for (const [k, val] of Object.entries(c.meta)) meta[k] = { value: val as number, source: "test", asOf: "2026-11-13", layer: "RAW", note: "" };
  const m = computeMetrics({ fin: x.fin, annual: x.annual, quarterly: x.quarterly, price, quoteMeta: meta,
    nextEarnings: { date: "2026-11-25", source: "test", eps_est: 0.9 }, today: "2026-11-14" });
  for (const [k, pv] of Object.entries(c.metrics)) { checks++; if (!close(m[k]?.value ?? null, pv)) { fails++; console.log(`[${c.name}] metric.${k}: ts=${m[k]?.value} py=${pv}`); } }
  for (const [k, pn] of Object.entries(c.notes ?? {})) { checks++; if ((m[k]?.note ?? "") !== pn) { fails++; console.log(`[${c.name}] note.${k}: ts=${m[k]?.note} py=${pn}`); } }
  const h = health(m, x.fin.operating_income, x.maturities, 0.6, 2026);
  checks += 4;
  if (!close(h.score.score, c.health)) { fails++; console.log(`[${c.name}] health ts=${h.score.score} py=${c.health}`); }
  if (!close(h.score.coverage, c.coverage)) { fails++; console.log(`[${c.name}] coverage`); }
  if (JSON.stringify(h.severe) !== JSON.stringify(c.severe)) { fails++; console.log(`[${c.name}] severe ts=${h.severe} py=${c.severe}`); }
  if (!close(h.nearMaturities, c.near)) { fails++; console.log(`[${c.name}] near ts=${h.nearMaturities} py=${c.near}`); }
}
console.log(`${checks - fails}/${checks} parity checks passed`);
if (fails) process.exit(1);
