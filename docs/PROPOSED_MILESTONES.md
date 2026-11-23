# Proposed milestones for earnings-insight `docs/ROADMAP.md` (2026-11-23)

Written in Modi-in because this session has no write access to earnings-insight. Copy into the app roadmap once approved.
Rules as always: free sources only, missing stays missing, every new signal enters a score only after it passes the
point-in-time back-test (out-of-sample t ≥ 2). Testing on live data waits until the user resumes data loading.

## M15 — New research-backed signals (from data already collected)
- [ ] M15.1 Earnings-date shift (Johnson & So 2018, JFQA): scheduled date of the coming report (Finnhub calendar) vs the
  same fiscal quarter last year (8-K Item 2.02 acceptance dates). Later than usual → −1, earlier → +1 (band ±3 days), as a
  guidance-predictor signal with evidence.
- [ ] M15.2 Filing text change ("Lazy Prices", Cohen-Malloy-Nguyen 2020, JF): cosine similarity of the latest 10-K/10-Q
  (whole document and Item 1A risk factors) vs the same report a year earlier, from SEC full-text documents; low
  similarity (bottom of the stored universe) → −1. Deterministic and point-in-time, unlike the AI `risk_factor_changes`.
- [ ] M15.3 Earnings seasonality (Chang-Hartzmark-Solomon-Soltes 2017, RFS): rank of the coming fiscal quarter among the
  company's quarters over the last 5 years (from stored SEC quarterly net income / revenue); high-seasonality quarter → +1.
- [ ] M15.4 Time-series revenue and gross-profit surprise (Jegadeesh-Livnat 2006; gross-profit surprise subsumes revenue
  surprise): standardized unexpected revenue / gross profit vs a seasonal random walk (quarter t−4), from SEC; "double
  surprise" when the EPS surprise has the same sign.
- [ ] M15.5 Mohanram G-score (2005, RAS) for growth (low book-to-market) companies: 8 binary signals (ROA, CFO/assets,
  CFO > NI, earnings and sales growth variability, R&D / capex / advertising intensity vs sector median; advertising
  usually not tagged → 7-point version, labeled).
- [ ] M15.6 Routine vs opportunistic insiders (Cohen-Malloy-Pomorski 2012, JF): an insider who traded in the same calendar
  month in each of the prior 3 years is routine; only opportunistic trades feed `insider_buys` and the unusual-sale risk item.

## M16 — Fixes from the full model review (2026-11-23)
- [ ] M16.0 Run the one-year PIT back-test (needs DECISIONS_NEEDED #13) and freeze its output as the baseline; extend it to
  5 years (SEC data and Tiingo history allow it) so the evaluation has hundreds of report events, not dozens.
- [ ] M16.1 State the target explicitly in MASTER_SPEC: the app ranks companies by the expected gap between the coming
  report/guidance and market expectations; evaluate everything against (a) guidance raised vs consensus and (b) excess
  return from 20 trading days before the report to 1 and 60 days after.
- [ ] M16.2 Ranking structure: health, risk override and data coverage become gates (pass / fail with reason), not 70% of
  the composite; the rank inside the gate = expectation-gap score (guidance predictor + M15 signals + M16.4). Show the old
  composite next to it until the back-test decides.
- [ ] M16.3 Guidance predictor: one vote per signal family (leading indicators, management track, analysts, read-through,
  industry, insiders, text) = mean of its members, so the ~10 accounting signals stop outvoting single analyst signals; keep
  magnitudes (z-scores) instead of only +1/0/−1; refit weights only walk-forward after ≥ 30 resolved outcomes (already the rule).
- [ ] M16.4 Reverse DCF: growth rate implied by today's price (same DCF, solve for g1) vs predicted growth (consensus
  revenue growth, guidance track, M9.1 leading indicators) → "expectations high / low"; replaces the saturating MoS score
  (50 + 150 × MoS hits 0 for most large tech) as the valuation input of the ranking.
- [ ] M16.5 Remove double counting: health is in the composite and again in risk ((100 − health) × 0.25); MoS is in
  valuation and in the earnings score ("rerate"); the EPS surprise streak is in the earnings score and in the predictor.
- [ ] M16.6 Sector-relative scoring: health and earnings parts as percentiles within sector (semis vs software differ in
  margins, inventory, capex) instead of fixed absolute bins.
- [ ] M16.7 Earnings score review: "priced" gives full points after a negative 3-month return (contrarian) — test vs the
  opposite (estimate-revision and price momentum before reports) in the back-test; drop the never-filled manual guidance part.
- [ ] M16.8 Chart layer only for entry/exit (floor, target, exit level), not for ranking, until a signal passes; widen the
  floor (Modi-in run 2026-11-20: floor held 20 sessions only 52% of the time).
