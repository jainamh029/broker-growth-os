# Final Report

> All data is synthetic. Every result below is a **simulated result that demonstrates the method**. None of it describes Hedge. Numbers are a snapshot of the seed-42 run; regenerate with `make all` and verify before quoting.

## What was built

Broker Growth OS: a tested, deterministic growth-operations prototype.

- **Funnel as code** ([src/bgos/funnel.py](src/bgos/funnel.py)): 7 strictly nested stages with definitions, ICP rule, completeness checklist, record validation.
- **Dirty synthetic data** ([src/bgos/generate.py](src/bgos/generate.py)): 3,000 true agencies plus 150 duplicates, about 23.7k touches, about 5.7k submissions over 2025-10-01 to 2026-09-30; 9 defect types injected and logged; effects planted for experiments A/B/C; referral = low-volume/high-quality, LinkedIn = high-volume/low-quality.
- **Cleaning** ([src/bgos/clean.py](src/bgos/clean.py)): dedupe 75/75 with 0 false merges on the labeled set, source mapping, size normalization, quarantine, tiny-n suppression, idempotent, never reads the defect manifest.
- **Scoring** ([src/bgos/scoring.py](src/bgos/scoring.py)): 0.30/0.25/0.20/0.15/0.10 Broker Fit Score, four tiers with explicit precedence, human-readable reasons.
- **Metrics layer**: 13 SQL files in [sql/](sql/), each cross-checked against independent pandas.
- **Experiments** ([src/bgos/experiments.py](src/bgos/experiments.py)): sample size, z-test, CIs (absolute and relative), power, SRM, SHIP/ITERATE/INCONCLUSIVE.
- **AI layer** ([src/bgos/ai/](src/bgos/ai/)): mock provider by default; research, submission-quality scorer, next-best-action, email first-line drafter (always `requires_human_review=True`); optional Anthropic provider (model from `BGOS_LLM_MODEL`).
- **Dashboard** ([app/dashboard.py](app/dashboard.py)): 9 views, synthetic-data banner, computed takeaways, reads `data/marts` only.
- **Docs**: [README.md](README.md), [DATA_DICTIONARY.md](DATA_DICTIONARY.md), [STRATEGY_MEMO.md](STRATEGY_MEMO.md), [LOOM_SCRIPT.md](LOOM_SCRIPT.md), [DEPLOY.md](DEPLOY.md), [DECISIONS.md](DECISIONS.md), [PROGRESS.md](PROGRESS.md), [BLOCKERS.md](BLOCKERS.md).

## Tests per phase (full suite: 155 passed, 0 failed, run twice; each phase was green with the full regression before the next began)

| Phase | Test file | Tests |
|---|---|---|
| 0 Scaffold | test_phase0_smoke.py | 21 |
| 1 Funnel and schema | test_phase1_funnel_schema.py | 9 |
| 2 Dirty data | test_phase2_generate.py | 10 |
| 3 Cleaning | test_phase3_clean.py | 15 |
| 4 Scoring | test_phase4_scoring.py | 14 |
| 5 Metrics | test_phase5_metrics.py | 16 |
| 6 Experiments | test_phase6_experiments.py | 17 |
| 7 AI layer | test_phase7_ai.py | 24 |
| 8 Dashboard | test_phase8_dashboard.py | 16 |
| 9 Docs | test_phase9_docs.py | 13 |

Phase 10 verification: `.venv` deleted and recreated with `make setup`; `data/` and `outputs/` removed; `make all` completed with exit 0; suite run twice, both green; secret scan found no keys, tokens or `.env`; no TODO/FIXME left in code or docs.

## Cuts and partial items

- **Nothing was cut.**
- Partial: the real-LLM provider is only exercised with an injected fake client. It has never called the live API (by design: no key, no network).
- Partial: screenshots are a placeholder ([docs/screenshots/README.md](docs/screenshots/README.md)); capture them yourself.
- Not done by design: GitHub push and Streamlit deployment (see [DEPLOY.md](DEPLOY.md)).
- Fix-loop log: Phase 2 (label-variant overlap, window overflow, missing-size on duplicate rows), Phase 4 (empty-frame handling, reason rounding, one wrong test fixture), Phase 6 (B came out at -11% under simple randomization, fixed with stratified randomization), Phase 7 (trailing negation in the text parser). Details in [DECISIONS.md](DECISIONS.md).

## Known limitations

- The funnel is deliberately generous (about 36% of raw leads reach a first submission) so Experiment A can be powered at its 20% ship threshold with 3,000 agencies (D41); real baselines will be lower and need much larger samples.
- Planted effects are plumbing tests. The mean A lift over 40 seeds is +29% (planted +30%) and A reaches SHIP in 37 of 40; seed 42 is one draw.
- The tier check is now out-of-sample (prospects scored 90 days before the as-of date, outcomes counted afterwards, engagement never uses submissions), but the generator still makes conversion depend on fit and engagement, so on synthetic data it validates plumbing, not real predictive power.
- "Dormant" agencies include some that are merely between submissions, so Experiment C's control-arm return rate (about 22% in 45 days) is higher than a truly lapsed population would show.
- Cohort repeat rates (about 55% / 72% / 79% at 30 / 60 / 90 days) and bind rates are generator choices, not benchmarks.
- No seasonality, loss ratio, carrier capacity, or cost metrics; flat commission assumption; dedupe blocks on state.
- Hedge-specific assumptions are unverified (see the "Assumptions to validate in the first 30 days" section of [STRATEGY_MEMO.md](STRATEGY_MEMO.md)).

## Headline simulated results (seed 42; after the scoring, maturity and sizing fixes, see [BUGS.md](BUGS.md))

- Funnel: 3,000 leads, 2,282 ICP-qualified, 1,695 engaged, 1,077 first submissions, 1,033 quoted, 466 bound, 343 repeat. Counting only leads old enough to have converted (cohort-mature), 21.7% of leads reach a bind; the raw 15.5% understates it.
- Source quality (mature): referral binds 35.6% of leads versus 11.7% for LinkedIn (3.1x), while LinkedIn supplies 30% of lead volume. Three tiny sources (n = 3, 4, 5) show 100% in the raw data and are suppressed.
- Activation: 38% of engaged agencies submit a complete package within 14 days. Median time to quote: 34 hours overall, 20 hours for low-complexity versus 91 for high-complexity risks.
- Tiers: 24 Tier 1, 706 Tier 2, 1,193 Tier 3 (prospects only), 672 Active customers, 405 Reactivation.
- Out-of-sample tier check (prospects scored 90 days earlier, conversion counted in the next 90 days): Tier 1 28.1%, Tier 2 11.7%, Tier 3 0.6%. On synthetic data this checks plumbing, not real predictive power.
- Experiment A (ICP-targeted outbound): 32.3% to 40.5%, relative lift +25.5% (95% CI +12.9% to +39.4%), p < 0.001, 1,221 per arm versus 862 required for the 20% ship threshold, power at that effect 92%: **SHIP** (simulated). The lower CI bound is below 20%, so the point-estimate rule carries winner's-curse risk. The planted effect is +30%.
- Experiment B (submission-ready onboarding): +15.3% (95% CI +2.2% to +30.1%), p = 0.020, 801 per arm versus 2,744 required, power at +10% only 33%: **ITERATE** (underpowered; not shippable).
- Experiment C (reactivation): -15.2% (95% CI -45.8% to +32.9%), p = 0.47, 147 per arm versus 940 required: **INCONCLUSIVE** (planted null).
- These are one simulated draw. Across 40 seeds ([docs/seed_sweep.json](docs/seed_sweep.json), `make sweep`) the same design returns SHIP for A in 37, never SHIP for B, and a chance-significant result for C in 3 (running three experiments at once carries a multiple comparisons risk).

## What Jainam must do

1. **Read the code**, at least [funnel.py](src/bgos/funnel.py), [scoring.py](src/bgos/scoring.py), [experiments.py](src/bgos/experiments.py), the SQL in [sql/](sql/) and [DECISIONS.md](DECISIONS.md). You should be able to defend every definition and every threshold.
2. **Run it yourself**: `make setup && make all && make test && make dashboard`; confirm it matches this report.
3. **Rehearse the Loom** using [LOOM_SCRIPT.md](LOOM_SCRIPT.md); time it (5-8 minutes); keep the synthetic-data banner on screen.
4. **Capture screenshots** into `docs/screenshots/`.
5. **Push to GitHub and deploy the dashboard** following [DEPLOY.md](DEPLOY.md) (nothing was pushed or deployed).
6. **Verify every number before quoting it** to Hedge or anyone else, and never present synthetic numbers as Hedge's. Validate each assumption in the memo against real data before building on it.
7. Decide whether the generous synthetic funnel (D10) is acceptable for the story you want to tell, or lower it and accept that Experiment A will then show as underpowered.
