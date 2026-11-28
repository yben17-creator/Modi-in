# EVI super agent — agent instructions (docs/SUPER_AGENT_SPEC.md)

Stage 2 (2026-11-28): Auditor + basic Maestro. Delta, Oracle, Radar and Nemesis come in stage 3, Referee in stage 5.
Every agent reads ONLY its section of a dossier (`earnings-insight/dossiers/<date>/<TICKER>.json`, built by code) and
never fetches data, never computes new numbers, never guesses: a missing input is "לא ידוע".
Outputs are JSON files in `Modi-in/verdicts/<date>/` (schema: `verdict.schema.json`). Nothing is written to the database
until stage 4 is approved. Runs use the user's Claude subscription only — no Claude API, no Lovable credits.

| file | agent | reads |
|---|---|---|
| `auditor.md` | Auditor (fundamental) | `auditor` + `meta` |
| `maestro.md` | Maestro (coordinator) | the Auditor finding + `delta.gap`, `delta.valuation`, `evidence`, `nextReport`, `missing` |
| `RUN.md` | the procedure a Maestro run follows (manual now; nightly only after the user approves) | — |
