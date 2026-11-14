# EARNINGS VALUE INTELLIGENCE — PROJECT HANDOFF

**Handoff date:** 2026-11-14  
**Purpose:** Transfer project context, implementation status, authoritative specification, and next steps to Claude or another development environment.  
**Priority:** This handoff and the embedded Master Specification supersede earlier conflicting architecture requests.

## A. VERIFIED VS REPORTED IMPLEMENTATION STATUS

**Important: This is a conversation-based handoff, not a source-code audit.** The receiving developer must inspect the actual Claude workspace, repository, deployed services, and test output before claiming functionality.

| Area | Status from conversation | Verification needed |
|---|---|---|
| Product concept and requirements | Specified in detail | Confirm against user expectations |
| Phase 1 interactive Claude Artifact | Claude reportedly completed an 8-screen demo with ~11 demo companies | Inspect artifact and confirm all screens |
| Financial metrics / DCF / risk override / holding-window comparison in demo | Reportedly displayed or simulated in prototype | Check whether computations are real or mocked |
| Phase 2 architecture | Discussed / prompted | Inspect actual deliverables; completion unverified |
| Phase 3 Python + Streamlit | Claude was actively writing it when last discussed | Obtain files, run code, tests, check EDGAR/Finnhub integrations |
| Phase 4 or later | **NOT VERIFIED AS IMPLEMENTED** | Do not assume completed merely because in spec |
| Real live market/financial data | Not demonstrated in provided evidence | Verify API calls, timestamps, accuracy and credentials |
| Scan Market button | User explicitly reported it was absent from current UI | Add and test in target Lovable app |
| Automatic scheduled scanning | Not demonstrated | Design, deploy, and verify separately |
| Lovable integration | New architecture decision; no completed integration demonstrated | Establish project and integration |
| Lovable Cloud database | Required final primary DB; not demonstrated as created | Configure and test schema/security |
| Backtesting and live alerts | Specified, not verified | Implement with data provenance and tests |

### What the user explicitly decided
- Final UI: **Lovable**, not Streamlit as the production frontend.
- Primary application database: **Lovable Cloud only**. No separately purchased/configured Supabase project.
- Preserve existing Claude Artifact and any reusable Python code; audit before rebuilding.
- English company names and tickers; coherent, paragraph-based Hebrew research reports with clear conclusions.
- Show current company market capitalization, annual revenue, profit/loss, debt, FCF, and meaningful valuation context.
- Strong focus on risk of **repeated share dilution**, including already announced issuance plans.
- No ETF or index-fund recommendation modules in the company research output.
- Include manual **Scan Market** and **Refresh Data**, plus eventual scheduled scanning.
- Optimize Claude model selection and token use; do not waste expensive inference on deterministic calculations.

## B. NON-NEGOTIABLE HANDOFF RULES
1. Treat all completion claims as provisional until verified against actual files, tests, or running services.
2. Do not invent existing API keys, provider entitlements, deployment URLs, or completed phases.
3. Do not imply Claude can directly migrate a Python/Streamlit UI into Lovable without adaptation.
4. Keep financial calculation logic deterministic, auditable, and independently tested.
5. Keep API credentials server-side and source timestamps visible.
6. Do not create a second independent application database.
7. If a separate Python runtime is needed, explain and obtain approval before adding hosting costs.
8. Preserve existing implementation where correct; provide migration/reuse matrix before major rewrites.

## C. FIRST TASK FOR THE RECEIVING CLAUDE SESSION
1. List the actual files/artifacts/repositories currently accessible.
2. Produce a verified implementation inventory with four labels: WORKING + TESTED / IMPLEMENTED BUT UNTESTED / DEMO ONLY / NOT IMPLEMENTED.
3. Compare the current project against the complete specification below, including every module.
4. Identify exact gaps through the user's stated Phase 4 and all later planned phases.
5. Provide a migration plan to Lovable + Lovable Cloud + optional Python analytics runtime.
6. Identify the smallest next milestone with a real-data end-to-end test.
7. Do not start a wholesale rewrite until the user approves the audit and migration plan.

## D. HOW TO USE THIS FILE
This is a **standalone handoff**: the entire authoritative Master Specification is embedded below. Upload this one file to Claude. Ask Claude to first audit the actual work and explicitly identify anything missing from the handoff or unavailable in its workspace.

---

# EMBEDDED AUTHORITATIVE MASTER SPECIFICATION (v1.1)

# EARNINGS VALUE INTELLIGENCE
## Master Product Requirements & Technical Specification
**Version:** 1.1 — Consolidated Lovable Cloud Architecture  
**Date:** 2026-11-14  
**Primary language:** Hebrew (RTL); company names and tickers in English  
**Market:** US-listed equities  
**Target stack:** Lovable frontend + Lovable Cloud managed database/backend + Python analytics when required  
**Status:** Product specification, not a claim of implemented functionality

> **Authoritative architecture decision:** Lovable Cloud is the sole primary application database. Do not require the user to create or purchase an independent Supabase project. Existing Claude Artifacts and Python/Streamlit work must be audited before migration. External Python compute may be needed for complex analysis, but must not require a second application database.

---

## 1. Mission and scope
Build an evidence-based research application that screens US-listed companies ahead of quarterly earnings, evaluates financial strength, estimates defensible intrinsic-value ranges, identifies potential fallen angels and value traps, detects risks (especially repeat share dilution), and researches historical price behavior around earnings. The system supports research decisions, **not automated brokerage trading**. It must never imply it can predict exact peaks or guaranteed returns.

The user should be able to scan the market, view earnings candidates, read coherent Hebrew company research, inspect evidence and uncertainty, monitor changes, and export reports. Separate fundamental long-term undervaluation from short-term event-driven opportunities.

## 2. Existing implementation and audit
A Claude Artifacts interactive prototype exists, reportedly with demo data for approximately 11 companies. A Python/Streamlit Phase 3 may be in progress. Before writing new code, Claude must inspect **only files actually available** and inventory: implemented features, demo-only functionality, verified live data integrations, reusable Python calculations, missing tests, technical debt, and migration risks. Do not claim access to unseen artifacts. Preserve functional code. Streamlit may remain an internal testing tool but is **not** the target production UI.

## 3. Target architecture — Lovable-first
- **Frontend:** Lovable-generated React + TypeScript, responsive Hebrew RTL, charting, search, filters, company profiles, watchlists, alerts and reports.
- **Primary database and app backend:** **Lovable Cloud**, including managed data tables, authentication, storage, secrets and supported server/edge functions. No independent Supabase account, project or subscription.
- **Financial analytics:** deterministic Python modules (FastAPI, pandas, NumPy, SciPy, Pydantic, pytest where appropriate) for DCF, historical event studies and backtesting. Run externally **only if** Lovable Cloud's supported runtime is insufficient; use authenticated API integration and keep Lovable Cloud as the only application database.
- **Financial providers:** SEC EDGAR; a verified market-data and earnings-calendar provider such as Finnhub, FMP or Massive; licensed analyst-estimate and news providers where necessary. Validate current entitlements, pricing, coverage, latency, and terms before implementation.
- **Code/versioning:** GitHub as source-control repository; clearly separate frontend, functions, analytics, migrations and tests.

**Proposed data flow:** Providers → ingestion/validation → Lovable Cloud → deterministic financial engines → valuation/earnings/risk rankings → Lovable UI/reports/alerts.

**Important limitations:** Lovable Cloud may use Supabase technology internally but must be treated as a managed Lovable product; do not assume unrestricted direct PostgreSQL connections, service-role keys, or external Python access. Verify supported integration methods. Cloud usage may incur charges beyond included quotas; avoid claiming it is permanently free. An external Python hosting service, if needed, can carry separate compute cost without becoming a separate DB.

## 4. Market universe and scanner
Cover NASDAQ, NYSE and NYSE American common equities, subject to verified data coverage. Prioritize enterprise software, SaaS, AI, cybersecurity, cloud, data infrastructure, semiconductors, automation and robotics; permit other sectors. Exclude ETFs, funds, warrants and preferred shares by default. Treat ADRs separately.

Filters: market capitalization, sector, earnings window (7/14/21/30 days), revenue growth, profitability, FCF, cash/debt, financial quality, valuation discount, dilution, insider transactions, news risks, and earnings catalyst score. All thresholds configurable; avoid arbitrary universal rules across industries.

**Scan Market** must be a real working button, not merely a mockup. It starts an asynchronous job, retrieves or refreshes licensed source data, applies filters, computes analysis, ranks companies and saves results. Display job ID/status/progress, number considered/analyzed/passed/rejected/insufficient-data, last completed time, source freshness, and provider failures. **Refresh Data** refreshes a selected company. Never silently fall back to demo data. Maintain an explicit isolated demo mode.

## 5. Financial health engine
Prefer at least five annual periods and eight quarters when available, without fabricating unavailable history. Compute and contextualize:
- Balance sheet: assets, liabilities, equity, cash, investments, total/short/long-term debt, net debt, current/quick ratios, debt maturities, leases, net debt/EBITDA, interest coverage.
- Profitability: annual revenue and trend, growth, gross profit/margin, operating income/margin, net income/margin, EBITDA when appropriate, ROIC.
- Cash flow: operating cash flow, capital expenditure, free cash flow (FCF), FCF margin/yield/conversion and stability.
- Stock-based compensation (SBC) and shareholder impact, with explicit distinction between GAAP cash flow treatment and dilution-adjusted owner metrics.

Clearly show **current market capitalization**, whether the company is profitable, **annual revenue**, debt, cash, and FCF. Generate an explainable 0–100 financial-quality score with sector-aware weighting and data-confidence penalties.

## 6. Intrinsic valuation and undervaluation
Implement reproducible DCF with revenue, operating margin, taxes, working capital, reinvestment, cash flow, discount rate, terminal growth/exit multiple, net debt, and fully diluted share count. Output bear/base/bull cases and sensitivity tables. Add peer and historical multiples: P/E, forward P/E, EV/sales, EV/EBITDA, EV/FCF, price/FCF, FCF yield where meaningful.

Display share price, market capitalization, enterprise value, intrinsic equity-value range, margin of safety, scenario upside/downside, assumptions and confidence. Avoid confusing enterprise and equity value, and avoid false precision. Flag aggressive terminal assumptions, declining economics, hidden liabilities and dilution-driven apparent cheapness.

## 7. Fallen angels and value traps
Analyze drawdown from 52-week highs, valuation compression, revenue/FCF trend, competitive changes, customer concentration, management transitions, business-model risk, AI disruption and market narrative. Classify as potentially undervalued quality, temporary transition, uncertain recovery, potential value trap or distressed. A large price decline alone is not a positive signal.

## 8. Earnings catalyst engine
For upcoming earnings, obtain the next event date, confirmation status, before-open/after-close/unknown timing, revenue/EPS consensus, revisions, guidance, past surprises, and historical reactions **only where licensed data exist**. Assess expectation changes, whether optimism is priced in, relevant peer reports, guidance trajectory, and identifiable catalysts. Produce explainable 0–100 catalyst score. A beat does not imply a positive return.

## 9. Insider, dilution and negative-news risk
**Insiders:** Track public disclosures for CEO/CFO/directors/significant owners, discretionary open-market purchases/sales, value, percentage of disclosed holdings, clusters, tax-related trades, option exercises and disclosed 10b5-1 plans. Do not claim visibility into private ordinary-employee trades.

**Dilution:** Track historical basic/diluted share counts, SBC/revenue, SBC/FCF, shelf registrations, ATM programs, announced/closed offerings, convertibles, employee grants, buybacks and net share count. Distinguish authorization, intent, announced transactions, actual issuance and future dilution potential. **Recurring dilution risk is a first-class metric**, especially where a company has publicly signaled plans to issue shares. Compute explainable risk score and date-stamped evidence.

**Negative news:** Track guidance cuts, restatements, auditor changes, investigations, litigation, cybersecurity incidents, management departures, key-customer loss, product failures, competitive threats and allegations. Store source, publication/event date, verification, severity and financial relevance; distinguish allegations from established facts. Critical risk overrides may downgrade research priority despite attractive valuation.

## 10. Historical earnings event study
Analyze prior events where data exist, ideally broader cross-company samples in addition to company history. Windows: -30/-21/-14/-7 trading days; event day; +1/+3/+5/+10/+20 trading days. Distinguish trading from calendar days and after-hours from before-open releases. Compare pre-earnings run-up, holding through earnings, and post-earnings drift. Calculate mean, median, win rate, dispersion, drawdown, tail risk, confidence intervals, sample size, benchmark-relative return and estimated costs. Eight company earnings events alone are insufficient for precise prediction.

## 11. Holding-period and exit research
Compare pre-event, through-event, short post-event and longer post-event windows. Show historical return distributions, volatility, tail risk, confidence, thesis-invalidation conditions and momentum/valuation changes. If evidence is inadequate, show **“Insufficient evidence to identify a reliable preferred holding period.”** Never invent exact future peak, optimal exit date or predictive probabilities. No trade execution.

## 12. Post-earnings monitoring
For watchlisted companies monitor price/volume, relative strength, volatility, guidance/analyst revisions, news, valuation, insider activity and dilution. Alerts: valuation gap closing, thesis deterioration, significant new risk, weakening momentum, estimate revisions, earnings date change and stale data. Each alert requires evidence, timestamp and user-relevant explanation.

## 13. Transparent scoring and prioritization
Separate Financial Quality, Valuation Attractiveness, Earnings Catalyst, Dilution Risk, Corporate Risk and Data Confidence scores. Optional overall Research Priority Score uses configurable weights, versioned methodology and overrides. Scores are research triage, **not** buy/sell guarantees. Avoid generic index and ETF recommendations; the product focuses on individual companies.

## 14. Backtesting and validation
Require point-in-time datasets, walk-forward/out-of-sample testing, transaction costs, slippage, spreads, corporate actions, delistings, survivorship and look-ahead bias controls. Use the date information was actually published; never treat later restatements as contemporaneous. Report sample periods, observations, sector/regime results, benchmark comparisons, uncertainty, drawdowns, calibration and failures. If historical advantage is not demonstrated, say so.

## 15. AI research use
LLMs may summarize calls/filings, extract guidance, classify news and write coherent Hebrew reports **with source citations**. Deterministic code must compute ratios, DCF, statistics and returns. Use structured extraction and caching, avoid reprocessing unchanged filings, and distinguish facts from model interpretations.

## 16. Data provenance, freshness and scheduling
For each observation store provider, source identifier/URL, fiscal period, published_at, retrieved_at, currency, units, data state and quality. States: current, delayed, historical, estimate, missing, stale, demo. Never fill unknowns with plausible numbers. Suggested checks: earnings calendar daily; new SEC filings daily; insider disclosures daily; analyst revisions daily where licensed; news multiple times daily if feasible; price updates per provider entitlement; valuations on material changes; full screening daily. Scheduled jobs must run without an open browser, subject to actual supported Lovable Cloud scheduling/compute limits. Long-running jobs may require separate workers.

## 17. Lovable Cloud database model
Design normalized tables or equivalent supported managed collections:
`companies`, `securities`, `market_prices`, `financial_statements`, `financial_metrics`, `earnings_events`, `analyst_estimates`, `insider_transactions`, `dilution_events`, `news_events`, `valuation_runs`, `risk_assessments`, `opportunity_scores`, `scan_jobs`, `scan_results`, `watchlists`, `alerts`, `model_versions`, `backtest_runs`, `backtest_results`, `source_documents`, `data_quality_logs`.

Include keys, relationships, indexes, unique constraints, historical snapshots and access rules. Use Lovable Cloud authentication and user-level access controls. Do not create a separate Supabase database or assume direct PostgreSQL access for Python.

## 18. Required Lovable UI screens
1. Market Scanner — filters, Scan Market, progress, results.
2. Upcoming Earnings — calendar and candidate ranking.
3. Financial Health — balance sheet, revenue, profitability and FCF.
4. Fair Value — DCF scenarios, peer multiples, margin of safety.
5. Fallen Angels — drawdowns, business health and value-trap warnings.
6. Risk Intelligence — insiders, repeat dilution, negative news.
7. Earnings Intelligence — expectations, revisions, surprises, catalysts.
8. Holding Period Research — historical distributions and limitations.
9. Company Research Report — coherent Hebrew paragraphs and conclusions.
10. Watchlist & Alerts — changes and evidence.
11. Backtesting — out-of-sample results and caveats.
12. System Status — provider connectivity, freshness, job errors, costs.

Main dashboard shows last scan, analyzed/qualified companies, earnings candidates, research priorities, critical risk alerts and freshness. Correct RTL layout, English tickers and company names, accessible charts, responsive design, dark-mode option. Avoid clutter and decorative metrics without decision value.

## 19. Required company report format
Use **readable connected Hebrew paragraphs**, not random snippets or metric dumps. English company names. Sections:
1. Business Overview — products, customers, business model, competition.
2. Financial Strength — **current market cap, annual revenue, profit/loss, cash, debt, FCF**, trend and interpretation.
3. Valuation — current value, bear/base/bull intrinsic range and assumptions.
4. Why It May Be Undervalued — plausible mispricing thesis versus value trap.
5. Earnings Catalyst — report date, expectations and potential drivers.
6. Risks — insider activity, **repeat dilution and announced issuance**, balance-sheet and business risks, verified negative news.
7. Historical Earnings Behavior — event study with sample size and limitations.
8. Holding Period Research — empirical comparison, not future timing certainty.
9. Final Research Assessment — High Research Priority / Worth Monitoring / Uncertain Opportunity / High Risk / Insufficient Data, with explicit rationale.

Provide evidence links, as-of timestamps and model version. Do not substitute ETF/index commentary for individual-company analysis.

## 20. Exports
Provide Excel, CSV and PDF exports for scan results, company research, watchlists and historical comparisons. Preserve Hebrew RTL, English company names, data timestamps, source links, assumptions and model versions.

## 21. Lovable Cloud integration and Python API
Build frontend and app database in Lovable. Use supported Lovable Cloud server functions to orchestrate provider requests, enforce authentication, handle secrets and manage jobs. If Python is required for complex calculations, expose authenticated FastAPI endpoints and integrate through supported HTTP APIs; verify network access, auth, CORS, limits and execution timeouts.

**Proposed endpoints, not claims of existing functionality:** `GET /health`, `GET /companies`, `GET /companies/{ticker}`, `GET /companies/{ticker}/financials`, `GET /companies/{ticker}/valuation`, `GET /companies/{ticker}/risks`, `GET /companies/{ticker}/earnings`, `GET /companies/{ticker}/holding-periods`, `POST /scans`, `GET /scans/{job_id}`, `GET /scan-results`, `GET /system/data-status`. Adapt architecture so Lovable Cloud remains the sole primary data store. Avoid publicly exposed write endpoints or browser-embedded secrets.

## 22. Claude model choice and token efficiency
**Do not assume specific model versions exist or are available. Verify the current Claude model menu and API catalog.** Use the highest-capability available Claude model (e.g., Opus tier) sparingly for architecture, critical quantitative review and difficult debugging; a balanced coding model (e.g., Sonnet tier) for normal implementation, UI, tests and migrations; a cheaper fast model (e.g., Haiku tier) for high-volume classification and structured extraction. An unusual specialized model should be used only if genuinely available and justified. Chat subscription model selection and paid API usage are separate.

Efficiency rules: keep `MASTER_SPEC.md`, `PROJECT_STATE.md`, `ARCHITECTURE.md`, `DATA_SOURCES.md`, `API_CONTRACTS.md`, `TEST_RESULTS.md` and `DEVELOPMENT_ROADMAP.md`; work in bounded tasks; read relevant files only; patch rather than rewrite; cache source documents; batch economical extraction; avoid unnecessary agents; run deterministic code for numeric analysis; record blockers; avoid repeated full-context prompts. Never trade correctness for token savings.

## 23. Security, reliability and costs
Use server-side secrets, secure auth, access rules, input validation, retries/backoff, rate limiting, audit logs, error reporting, backups and separate demo/production modes. Respect provider licensing and redistribution restrictions. Track costs for Lovable Cloud, API providers, AI inference and any optional Python hosting. Prefer Lovable-native capabilities; introduce external paid services only with documented necessity, free alternatives, tradeoffs and projected recurring cost.

## 24. Phased development roadmap
**Phase 0 Audit:** inventory Claude Artifact, Python/Streamlit work and real-vs-demo data. Deliver migration and reuse plan.

**Phase 1 Foundation:** GitHub structure, Lovable project, Lovable Cloud schema/auth, provider abstraction, security and tests.

**Phase 2 Verified Data:** company universe, market prices, SEC filings, earnings calendar, provenance, freshness, functioning Scan Market and Refresh Data.

**Phase 3 Fundamental Analysis:** financial health, DCF, peer multiples, margin of safety, share dilution.

**Phase 4 Earnings/Risk Intelligence:** analyst estimates, revisions, event history, insider filings, negative news, risk overrides.

**Phase 5 Validation:** event studies, walk-forward backtesting, holding-window research, failure analysis.

**Phase 6 Monitoring:** scheduled scans, watchlists, change detection, alerts, exports.

**Phase 7 Production:** security, performance, observability, cost controls, deployment, documentation.

Each phase has measurable acceptance tests; do not declare success on UI appearance alone.

## 25. Acceptance criteria
1. A scan fetches real US-listed companies, not fabricated demo entries.
2. Earnings dates show confirmation and provider timestamps.
3. Financial figures reconcile to source filings.
4. Ratios and DCF are reproducible by tests.
5. Current market cap, annual revenue, profitability, debt and FCF are clearly shown.
6. Dilution analysis differentiates potential from actual issuance and flags announced repeat dilution.
7. Insider and news events link to verifiable evidence.
8. Missing/stale data are explicitly labeled; never silently substituted.
9. Event studies handle announcement timestamps and trading days correctly.
10. Backtests prevent look-ahead/survivorship bias.
11. Scan progress, freshness and failures are visible.
12. API keys are server-side.
13. Hebrew reports are coherent and conclude with clear research priority and risks.
14. Lovable Cloud is the sole primary application database; no independent Supabase purchase required.
15. The deployed app works outside development preview and documents any optional external Python hosting.

## 26. Instructions to Claude — immediate next step
This document is the **single authoritative specification** and supersedes earlier conflicting architecture instructions. Do **not** attempt to generate the whole production system in one response. First audit existing accessible work; list implemented/tested/live/demo/unavailable components; preserve valid code; propose a minimal Lovable Cloud migration plan and first verified-data milestone. Before introducing external infrastructure, verify Lovable Cloud capabilities and explain necessity, costs and integration. At each phase report: implemented, tested, operational, demo-only, credentials needed, limitations and next step. Ask for user action only for genuinely required access, credentials or decisions.

**First response requested from Claude:** (a) factual inventory of accessible project, (b) architecture diagram using Lovable Cloud, (c) migration/reuse matrix, (d) real-data provider plan with verified entitlements, (e) immediate next step and acceptance tests. Do not silently implement a second disconnected app.
