# BUGS

Independent audit of Broker Growth OS. Severity: Sev-1 wrong number / crash on a documented command / false claim; Sev-2 brittle or misleading; Sev-3 polish. Regression tests live in [tests/test_audit_regressions.py](tests/test_audit_regressions.py). Pre-fix failure was demonstrated by running each new test against the unfixed code (before the fix commit, or in a worktree at the parent commit) and seeing it fail.

| ID | Sev | Status | Found by | Root cause | Fix (commit) |
|---|---|---|---|---|---|
| B-01 | 3 | fixed | `pytest -W error` | `open(APP).read()` in two dashboard tests leaked file handles (ResourceWarning). | Use `Path.read_text()` (da26e65) |
| B-02 | 2 | fixed | boundary review of the SHIP rule | A relative lift of exactly 20% evaluates to 0.19999999999999996 in IEEE arithmetic, so `rel_lift >= 0.20` silently failed at the boundary. Sample-size comparison also had no boundary test. | `LIFT_TOL`, `is_sample_size_reached()` (165589f) |
| B-03 | 1 | fixed | running the pipeline from output roots containing `#`, `%`, `?` | `metrics.connect` built a `file:` URI by string formatting. `#` and `?` truncated the path (silently opening an empty DB: "no such table: stage_events"); `%` crashed with "unable to open database file". `make all` therefore crashed on any such folder name. | `Path.as_uri()` (44cee2e) |
| B-04 | 2 | fixed | fresh-clone dashboard run | `use_container_width` is deprecated with a removal date that has passed (2025-12-31); a Streamlit upgrade would break every chart. | `width="stretch"` (da26e65) |
| B-05 | 1 | fixed | 40-seed sweep: mean Experiment A lift was +23.5% against a planted +30% | The generator capped only the TREATED probability at 0.97, so agencies with baseline probability above 0.75 received less than the planted multiplier. The manifest, README and memo all claimed a +30% planted effect that the data did not contain. | `submit_probability()` caps the control probability so the lift is exactly +30% for every agency; all outputs and docs regenerated (4109a5e) |
| B-06 | 2 | fixed | claims audit (A4/A6) | Nowhere acknowledged that three experiments carry multiple-comparisons risk; the memo/README/dashboard presented one seed as the result (the builder's "5 of 8 seeds" was not in any deliverable); the generous funnel was flagged only in the README; the README embedded a `.md` file as an image (renders broken). | Caveats added to README, memo (generated), Loom script (generated) and dashboard; `docs/seed_sweep.json` + `make sweep` (d2d4d10, 4109a5e) |
| B-07 | 2 | fixed | mutation testing (A3) | Six mutants survived the original 155 tests: dormancy boundary in the weekly north-star SQL (>= vs >, and < vs <=), 14-day activation boundary, `p < alpha` vs `p <= alpha`, "sample reached" using the larger arm, and AI scorer weights swapped (tautological test). Four more were caught only by the "docs equal regenerated" test, not by any unit test: naive relative CI, Tier-1 engagement threshold, LinkedIn source mapping, removal of blocked randomization. | Boundary tests on hand-built SQLite fixtures, statsmodels cross-check of both CIs, threshold-boundary tests, exact source-map test, literal AI weights, blocking-balance test (ec4870b) |
| B-08 | 3 | fixed (tests) | fresh-clone and extreme-filter review (A7) | Not a defect: the first-run bootstrap and empty/extreme filter states worked but were untested. | Added `test_dashboard_bootstraps_from_empty_root` and `test_dashboard_extreme_filters_do_not_crash` (ec4870b) |
| B-09 | 2 | fixed | seed change exposed it in `test_dedupe_recall_and_no_false_merges` | `dedupe_agencies` only skipped the literal state `UNK`; handed raw rows with blank / `N/A` states it merged same-name agencies. The pipeline normalized first, so the pipeline itself was unaffected, but the function was unsafe on its own. | Skip every missing-state token (4002c89) |
| B-10 | 2 | fixed, test changed | same seed change | Two tests asserted "referral has the highest bind rate" on one small noisy draw (referral n = 113). After B-05 the seed-42 draw shows partner (21.5%) above referral (18.6%). Verified at n = 6000 that the planted ordering holds (referral about 26%, linkedin about 9%). Test change justified: the property is a population-level design intent; the seed-level assertions were pinned to a lucky draw. Replaced by a stronger large-n test; seed-level tests keep "linkedin lowest" and "referral at or above the median". | (4109a5e) |
| B-11 | 3 | fixed | writing test B-10 | `generate(write=False)` still created output directories. | Only create directories when writing (4109a5e) |
| B-12 | 2 | fixed | claims audit | Memo said "speed is what brokers remember", an unsupported claim about broker behaviour. | Removed (e29986f) |
| B-13 | 3 | open | A1 | Report said 11 commits; there were 12. DECISIONS D8 still says "(planned)". | Logged only |
| B-14 | 3 | open | A7 | Two simultaneous first visitors to a fresh deployment could both run the bootstrap pipeline and write the same files. Output is deterministic so the files converge, but it is a race. | Logged only (Streamlit Cloud runs one process; low risk) |
| B-15 | 3 | open | A8 | Git author email is a personal address and will be public on GitHub. | Left as instructed; see AUDIT_REPORT.md |

## Weak or tautological tests found

- `test_zero_noncanonical_sources`: asserted mapped labels are "in CANONICAL", so a wrong mapping (`LI` to outbound) still passed. Strengthened with exact expectations (B-07).
- `test_scorer_100_for_complete...`: expected scores computed from the same `WEIGHTS` dict under test; swapping two weights was invisible. Literal weights now asserted.
- `test_confidence_intervals_formulas`: only checked `low < estimate < high` for the relative CI. Now compared with statsmodels (log-ratio and Wald).
- `test_source_quality_shape` / `test_source_quality`: pinned to one noisy draw (B-10).
- Dashboard "no hard-coded numbers" test only greps for currency/thousands literals; it cannot catch a typed `42`. Left as is (Sev-3).

## Mutation results (38 mutants, `/tmp` scratch copies)

Original suite: 6 survived (M03b, M07, M14, M15, M19, M31). After the new tests all 38 are killed. M13 (`>=` to `>` on the 20% rule) became an equivalent mutant once the float tolerance was added (the tolerance makes exact-boundary equality untestable); the pre-tolerance mutant was killed by the 20% boundary test.
