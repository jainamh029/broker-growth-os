# DECISIONS

Decision log. Every judgment call made without human input is recorded here. All data is synthetic.

| # | Phase | Decision | Why |
|---|-------|----------|-----|
| D1 | 0 | Venv scripts are invoked as `python -m ...` (never via `.venv/bin/pytest` shebangs). | The workspace path contains spaces, which breaks shebang lines. `python -m` works everywhere. |
| D2 | 0 | `config.get_paths()` honours a `BGOS_ROOT` env var. | Lets tests and the README-quickstart test run the whole pipeline in a temp dir without touching the repo's `data/`. |
| D3 | 0 | Makefile `clean` means "run the data-cleaning stage" (per the brief's target list); `reset` deletes generated files. | Brief lists `data, clean, score...` as pipeline steps. |
| D4 | 1 | Funnel is strictly nested: an agency counts at stage k only if it passed stages 1..k-1. Activity from agencies that skip stages (e.g. a submission from a non-ICP agency) is reported as "out-of-funnel". | Makes monotonic non-increase true by construction and keeps the numbers auditable. |
| D5 | 1 | "Underwriting-ready" = 4 required checklist fields (loss runs, prior carrier, risk description, property/exposure details). COIs and financials are recommended, not required for the funnel, but are weighted in the AI submission-quality score. | Underwriters can quote without COIs/financials on many specialty risks; a funnel that demanded all six would understate activation. |
| D6 | 1 | Funnel "Repeat Submission" = another complete submission within 90 days AFTER the first bind (bind-anchored). Activation retention cohorts (Phase 5) are anchored on FIRST SUBMISSION at 30/60/90 days. | The funnel is strictly ordered (Repeat follows Bound), so the stage must be bind-anchored to stay monotone. A repeat after a bind is the strongest signal the relationship works. First-submission anchoring in cohorts gives much larger n and measures the habit earlier. Both are documented and used for different questions. |
| D7 | 1 | ICP = commercial lines AND (E&S appetite high/medium OR target specialty weight >= 0.70) AND >= 3 producers. Qualification is dated at first touch. | Matches the brief's "E&S/specialty/hard-to-place exposure + minimum producer/deal-flow". Thresholds are in config. |
| D8 | 4 | Tier precedence (planned): Reactivation first, then Tier 1, then Tier 2, else Tier 3. | A dormant agency with past submissions is a different motion (win-back) regardless of fit. |
| D9 | 1 | The database enforces timestamp ordering via CHECK constraints; raw CSVs (which may be dirty) live outside the DB and are cleaned before loading. | Dirty data cannot enter the SQLite layer. |
