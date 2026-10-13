# AUDIT LOG

| Stage | What was run | Result |
|---|---|---|
| A0 | `pwd`, `git log`, `git status` in the original folder | The project lived in a session scratch workspace that is deleted with the session. Copied (history intact, clean tree) to `~/broker-growth-os`; all audit work happened there. |
| A1 | Fresh `git clone`, new venv, `pip install -r requirements.txt`, `make all`, `pytest -q`, `make test` x2 | Pass: 155 passed (35 s), `make all` 30 s, clean `git status` afterwards (docs regenerate byte-identically). Claim mismatches: 12 commits (not 11); `DECISIONS.md` has 37 decisions (matches); `BLOCKERS.md` contained "no blockers" prose (acceptable). |
| A2 | Seeds 1-8 full pipeline (no crash, no NaN/inf outside suppressed columns, funnel monotone, no impossible values after cleaning) | Clean before and after fixes. |
| A2 | `PYTHONHASHSEED` 0 / 1 / random; `pytest-randomly` order; `-W error` | Hash seeds pass. **Random order exposed B-16** (order-dependent failure). `-W error` exposed B-01. Fixed; all pass after. |
| A2 | Run from another cwd (`make -C` from /tmp, BGOS_ROOT elsewhere); grep for absolute paths, `datetime.now`, `date.today`, `time.time` | Works; no absolute paths and no wall-clock calls in logic (as-of date comes only from `config.py`). |
| A2 | Determinism: two `make all` runs into different roots, hash all 35 files | Identical (including the SQLite file). |
| A2 | Output roots with `#`, `%`, `?`, space | **B-03** crash on `#`, `%`, `?`. Fixed. |
| A3 | 39 mutants on scratch copies (+5 added later) | 6 survived the original suite (B-07); 0 survive after the new tests (M13 is an equivalent mutant after the float tolerance). Details in BUGS.md. |
| A4 | z-test, absolute CI, relative (log-ratio) CI, sample size, power re-derived with statsmodels on fixed inputs AND on the experiment counts re-queried from raw SQLite | All match to 1e-9 (power and sample size within 1 unit of the arcsine reference). Boundary logic reviewed: **B-02**. Stratified randomization uses baseline covariates only (source, ICP flag, fit tercile), is documented in D25 including the reason it was introduced, and SRM still works (unit-tested; blocked assignment is simply more balanced). |
| A4 | 40-seed sweep before and after the B-05 fix | Before: A SHIP 29/40, mean A lift +23.5% (planted +30%). After: A SHIP 32/40, mean +28.3%; B never SHIP; C spurious significance 3/40. |
| A5 | Independent raw-SQL recomputation of funnel, source bind rates, experiment counts | Originally reported figures (797 / 521 / 203, 23.0% vs 8.4%, +27.3%) were reproduced exactly on the original data. They changed after the B-05 fix; the new figures were again reproduced with independent SQL (1,116 / 795 / 486 / 209 / 160, linkedin 8.0%, referral 18.6%, partner 21.5%, A +37.5%, B +11.8%, C 0.0%). A drift test now guards FINAL_REPORT. |
| A6 | Claims, disclaimers, send-code, multiple-comparisons greps | No real-Hedge claims; no send/network code; disclaimers present everywhere. Gaps fixed in B-06 and B-12. |
| A7 | Fresh clone with no data: dashboard AppTest | Bootstraps and renders (now covered by a test). Extreme/empty filters covered by a test. Deprecated API fixed (B-04). |
| A8 | Secret scan of whole git history (grep, gitleaks/trufflehog not installed), personal strings, file sizes | No secrets; no paths/hostnames in history; largest file 35 KB. Personal email in commit authorship (B-15, left as instructed). |
