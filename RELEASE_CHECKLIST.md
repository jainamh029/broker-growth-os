# RELEASE CHECKLIST

| Gate | Result | Evidence |
|---|---|---|
| Fresh-clone `make setup`, `make all`, `pytest -q` pass, twice | PASS | Fresh clone of HEAD: `make setup` exit 0, `make all` exit 0 and clean `git status`, `make test` x2 and `pytest -q`: 190 passed each time (about 90 s). |
| Also green under hash seeds, random test order, `-W error` | PASS | `PYTHONHASHSEED` 0/1/random; `pytest-randomly` seeds 11, 12 (and 817394477, which had exposed B-16); `-W error`: 190 passed. |
| Seed sweep 1-8 clean | PASS | No crash, no NaN/inf outside suppressed columns, funnel monotone, no impossible values surviving cleaning (run after the last generator change). |
| Every A3 mutation caught | PASS | 39 mutants: 6 survived the original suite, 0 survive now (M13 is an equivalent mutant after the float tolerance). See BUGS.md. |
| Independent recomputation matches every reported number; drift test exists | PASS | Raw-SQL recomputation of funnel, source bind rates and experiment counts matches (AUDIT_LOG A5); `test_final_report_headline_numbers_match_outputs`, the memo traceability test and the dashboard-vs-metrics tests fail on drift. |
| Stats cross-checks pass | PASS | z, p, absolute and log-ratio relative CI, sample size and power match statsmodels; boundary behaviour tested (B-02). |
| Zero open Sev-1 / Sev-2; BLOCKERS.md has no blockers | PASS | BUGS.md: B-01..B-12 and B-16 fixed; open items B-13, B-14, B-15 are Sev-3. |
| Secret and personal-data scan (tree and history) | PASS with note | No keys/tokens/.env in tree or history; no home paths or hostnames. gitleaks/trufflehog are not installed, so the scan was grep-based. Commit author email is a personal Gmail address (B-15), left as instructed. |
| Synthetic disclaimers present everywhere required | PASS | Tests: README, memo, Loom, deploy, data dictionary; banner on all nine dashboard views; SIMULATED label on experiment outputs. |
| Dashboard starts from a fresh clone with no manual data step | PASS | `test_dashboard_bootstraps_from_empty_root`; manual AppTest from a clone with no `data/` rendered with no exception. |
| Optional: screenshots | NOT DONE | No Playwright/Chromium available to this session; placeholder remains in `docs/screenshots/README.md`. |
