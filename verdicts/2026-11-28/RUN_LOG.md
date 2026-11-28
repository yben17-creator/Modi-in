# Maestro run log — 2026-11-28 (stage 2, manual, interactive session on the user's subscription)

- Dossiers: 20 (earnings-insight `dossiers/2026-11-28/`, workflow run 46145873850: 449 companies ranked from the
  back-test cache, 21 Tiingo requests in total, no database access).
- Read by the agents: the compact view from `agents/extract.py` — about 0.5 KB per company (~10 KB for 20). The raw
  dossiers are ~990 KB; reading them directly would cost ~100× more of the quota. → Stage 3 rule: agents read only the
  extracted view of their section.
- Verdicts: 19 scored, 1 not scored (ANF — report already published, builder bug, fixed in earnings-insight PR #95).
- Quota: a run of 20 companies with Auditor + Maestro fits easily in one session; Delta/Oracle/Radar/Nemesis in stage 3
  will roughly triple the reading (still small with the compact view). Exact token counts are not visible to the agent.
- Findings for the engine (not the agents' job to fix, recorded in earnings-insight docs/LESSONS.md and REGISTRY E1b):
  1. reverse-DCF predicted growth extrapolates the 3-year CAGR (MU +105%/yr, CRDO +94%/yr) → inflated expectation gap;
  2. valuation score is 100 for 14 of the 20 → it does not separate the top candidates;
  3. the universe is all sectors (retail dominates: SIG, AEO, FIVE, ANF, PVH, BBW, ASO, OLLI), not only US tech.
