// Core provenance type — port of python/evi/models.py (Val).
// A missing value is { value: null, note: "why" }. Values are never back-filled.

export type Layer = "RAW" | "CALC" | "MODEL" | "AI";

export interface Val {
  value: number | null;
  source: string;
  asOf: string | null; // period end / quote time (ISO)
  layer: Layer;
  note: string;
  fetched?: string | null;
}

export const ok = (x: Val | undefined | null): x is Val & { value: number } =>
  !!x && x.value !== null && x.value !== undefined && !Number.isNaN(x.value);

export const v = (x: Val | undefined | null): number | null => (ok(x) ? x.value : null);

export const missing = (why: string, source = ""): Val => ({ value: null, source, asOf: null, layer: "RAW", note: why });

export function calc(value: number | null, source: string, inputs: (Val | undefined)[] = [], note = ""): Val {
  const dates = inputs.filter((i): i is Val => !!i && !!i.asOf).map((i) => i.asOf as string).sort();
  const asOf = dates.length ? dates[0] : null;
  if (value === null || value === undefined || Number.isNaN(value)) {
    const miss = inputs.filter((i): i is Val => !!i && !ok(i)).map((i) => i.note || i.source).filter(Boolean);
    return { value: null, source, asOf, layer: "CALC", note: note || "חסר קלט: " + miss.join("; ") };
  }
  return { value, source, asOf, layer: "CALC", note };
}

export const MODEL_VERSION = "evi-engine-ts 0.1.0 (port of python reference @ Modi-in 1ebf157)";
