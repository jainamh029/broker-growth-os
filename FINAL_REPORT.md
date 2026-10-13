# Final Report

> All data is synthetic. Every result below is a **simulated result that demonstrates the method**. None of it describes Hedge. Numbers are a snapshot of the seed-42 run; regenerate with `make all` and verify before quoting.

## What was built

Broker Growth OS: a tested, deterministic growth-operations prototype.

- **Funnel as code** ([src/bgos/funnel.py](src/bgos/funnel.py)): 7 strictly nested stages with definitions, ICP rule, completeness checklist, record validation.
- **Dirty synthetic data** ([src/bgos/generate.py](src/bgos/generate.py)): 1,500 true agencies plus 75 duplicates, about 11.8k touches, about 2.7k submissions over 2025-10-01 to 2026-09-30; 9 defect types injected and logged; effects planted for experiments A/B/C; referral = low-volume/high-quality, LinkedIn = high-volume/low-quality.
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

- The funnel is deliberately generous (about 35% of raw leads reach a first submission) so Experiment A can be powered with 1,500 agencies; real baselines will be lower and need much larger samples.
- Planted effects are plumbing tests. On seed 42 the A estimate (+27.3%) lies close to the planted +30%; across 8 seeds A reaches SHIP in 5, which is the honest power of this design.
- The tier ordering check (Tier 1 > Tier 2 > Tier 3 first-submission rate) is circular by construction and only validates plumbing.
- "Dormant" agencies include some that are merely between submissions, so Experiment C's control-arm return rate (about 20% in 45 days) is higher than a truly lapsed population would show.
- Cohort repeat rates (about 52% / 67% / 75% at 30 / 60 / 90 days) and bind rates are generator choices, not benchmarks.
- No seasonality, loss ratio, carrier capacity, or cost metrics; flat commission assumption; dedupe blocks on state.
- Hedge-specific assumptions are unverified (see the "Assumptions to validate in the first 30 days" section of [STRATEGY_MEMO.md](STRATEGY_MEMO.md)).

## Headline simulated results (seed 42)

- Funnel: 1,500 leads, 1,112 ICP-qualified, 797 engaged, 521 first submissions, 492 quoted, 203 bound (13.5% of leads), 150 repeat.
- Source quality: referral binds 23.0% of leads versus 8.4% for LinkedIn (2.7x), while LinkedIn supplies 32% of lead volume. Three tiny sources (n = 3, 4, 5) show 100% in the raw data and are suppressed.
- Activation: 42% of engaged agencies submit a complete package within 14 days (the biggest controllable gap). Median time to quote: 35 hours overall, 21 hours for low-complexity versus 89 for high-complexity risks.
- Tiers: 82 Tier 1, 610 Tier 2, 602 Tier 3, 206 Reactivation.
- Experiment A (ICP-targeted outbound): 31.4% to 40.0%, relative lift +27.3% (95% CI +9.4% to +48.2%), p = 0.002, 612 per arm versus 407 required: **SHIP** (simulated).
- Experiment B (submission-ready onboarding): +20.5% (95% CI +2.7% to +41.4%), p = 0.022, but 383 per arm versus 1,058 required: **ITERATE** (underpowered; the framework refuses to ship it).
- Experiment C (reactivation): -26.7% (95% CI -63.9% to +49.0%), p = 0.39, 75 per arm versus 294 required: **INCONCLUSIVE** (planted null).

## What Jainam must do

1. **Read the code**, at least [funnel.py](src/bgos/funnel.py), [scoring.py](src/bgos/scoring.py), [experiments.py](src/bgos/experiments.py), the SQL in [sql/](sql/) and [DECISIONS.md](DECISIONS.md). You should be able to defend every definition and every threshold.
2. **Run it yourself**: `make setup && make all && make test && make dashboard`; confirm it matches this report.
3. **Rehearse the Loom** using [LOOM_SCRIPT.md](LOOM_SCRIPT.md); time it (5-8 minutes); keep the synthetic-data banner on screen.
4. **Capture screenshots** into `docs/screenshots/`.
5. **Push to GitHub and deploy the dashboard** following [DEPLOY.md](DEPLOY.md) (nothing was pushed or deployed).
6. **Verify every number before quoting it** to Hedge or anyone else, and never present synthetic numbers as Hedge's. Validate each assumption in the memo against real data before building on it.
7. Decide whether the generous synthetic funnel (D10) is acceptable for the story you want to tell, or lower it and accept that Experiment A will then show as underpowered.
