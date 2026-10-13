import hashlib
import shutil
import sqlite3

import pandas as pd
import pytest

import config
from bgos import clean, funnel, generate


def test_zero_residual_duplicates(clean_result):
    d = clean.dedupe_agencies(clean_result.agencies)
    assert (d.agency_id == d.survivor_id).all()
    assert clean_result.agencies.agency_id.is_unique


def test_dedupe_recall_and_no_false_merges(gen_result, clean_result):
    dups = gen_result["manifest"]["details"]["duplicates"]  # dup_id -> true id (labeled test set)
    raw_ids = gen_result["raw"]["agencies"].agency_id.tolist()
    entity = {i: dups.get(i, i) for i in raw_ids}
    surv = pd.concat([clean_result.dedupe_map[["agency_id", "survivor_id"]]]).set_index("agency_id")["survivor_id"].to_dict()
    # dedupe_map only lists merged rows; rebuild full mapping
    full = clean.dedupe_agencies(clean.load_raw(gen_result["root"] / "data" / "raw")["agencies"].assign(
        name=lambda d: d["name"].str.strip()).assign(state=lambda d: d["state"].str.upper()))
    m = dict(zip(full.agency_id, full.survivor_id))
    found = sum(1 for d_, t_ in dups.items() if m[d_] == m[t_])
    assert found / len(dups) >= 0.95, (found, len(dups))
    # false merges: two ids share a survivor but belong to different true entities
    groups = {}
    for i, s in m.items():
        groups.setdefault(s, set()).add(entity[i])
    assert all(len(v) == 1 for v in groups.values()), [v for v in groups.values() if len(v) > 1]


def test_dedupe_handlabeled_pairs():
    ag = pd.DataFrame({
        "agency_id": ["1", "2", "3", "4", "5", "6", "7"],
        "name": ["Hargrove & Cole Insurance Agency LLC", "HARGROVE & COLE INSURANCE AGENCY",
                 "Hargrove & Cole Ins. Agcy", "Summit Risk Advisors", "Summit Risk Advisors",
                 "Westbrook Insurance Group", "Eastgate Insurance Group"],
        "state": ["CA", "CA", "CA", "TX", "FL", "NY", "NY"],
        "first_touch_date": ["2025-11-01", "2025-12-01", "2026-01-01", "2025-10-05", "2025-10-06", "2025-10-07", "2025-10-08"]})
    d = clean.dedupe_agencies(ag).set_index("agency_id")["survivor_id"].to_dict()
    assert d["1"] == d["2"] == d["3"] == "1"  # earliest record survives
    assert d["4"] == "4" and d["5"] == "5"  # same name, different state: NOT merged
    assert d["6"] == "6" and d["7"] == "7"  # different agencies in the same state: NOT merged


def test_zero_noncanonical_sources(clean_result):
    assert clean_result.agencies.lead_source.isin(clean.CANONICAL_SOURCES).all()
    assert set(generate.CANONICAL_SOURCES) == set(clean.CANONICAL_SOURCES)
    for variants in generate.SOURCE_LABEL_VARIANTS.values():
        for v in variants:
            assert clean.canonical_source(v) in clean.CANONICAL_SOURCES
    with pytest.raises(ValueError):
        clean.canonical_source("mystery channel")


def test_zero_impossible_values(clean_result):
    sb, ag = clean_result.submissions, clean_result.agencies
    assert all(not funnel.validate_submission(r) for r in sb.to_dict("records"))
    assert (ag.prior_bind_rate_pct.dropna() <= 100).all()
    assert (sb.quote_turnaround_hours.dropna() >= 0).all()
    assert ag.size_producers.map(clean.is_plain_int).all()
    assert ag.size_producers.notna().all()


def test_reconciliation_with_injected_defects(gen_result, clean_result):
    c, h = gen_result["manifest"]["counts"], clean_result.stats["handled"]
    for k in ["missing_state", "missing_size", "mixed_size_formats", "inconsistent_source_labels",
              "bind_rate_over_100", "negative_turnaround", "quote_before_submission", "bound_before_quote"]:
        assert h[k] == c[k], k
    q = clean_result.quarantine
    rows_q = (q.action == "row_quarantined").sum()
    fixed = ((q.action == "repaired") | (q.action == "value_nullified")).sum()
    assert rows_q == c["quote_before_submission"] + c["bound_before_quote"]
    assert fixed == c["negative_turnaround"] + c["bind_rate_over_100"]
    assert rows_q + fixed == (c["quote_before_submission"] + c["bound_before_quote"]
                              + c["negative_turnaround"] + c["bind_rate_over_100"])
    assert h["bound_without_quote"] == 0
    # flagged, not silently altered
    ag = clean_result.agencies
    assert ag.state_missing.sum() == c["missing_state"] and (ag[ag.state_missing == 1].state == "UNK").all()
    assert ag.size_imputed.sum() == c["missing_size"]
    # row-level accounting
    raw = gen_result["raw"]
    assert len(clean_result.submissions) == len(raw["submissions"]) - rows_q
    assert len(clean_result.touches) == len(raw["touches"])
    assert len(clean_result.agencies) == len(raw["agencies"]) - len(gen_result["manifest"]["details"]["duplicates"])


def test_manifest_duplicates_gone_and_children_remapped(gen_result, clean_result):
    dups = gen_result["manifest"]["details"]["duplicates"]
    assert not set(dups) & set(clean_result.agencies.agency_id)
    ids = set(clean_result.agencies.agency_id)
    assert set(clean_result.touches.agency_id) <= ids
    assert set(clean_result.submissions.agency_id) <= ids
    assert set(clean_result.assignments.agency_id) <= ids


def test_foreign_keys_resolve_in_sqlite(gen_result, clean_result):
    conn = sqlite3.connect(gen_result["root"] / "data" / "clean" / "bgos.sqlite")
    conn.execute("PRAGMA foreign_keys = ON")
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("select count(*) from agencies").fetchone()[0] == len(clean_result.agencies)
    assert conn.execute("select count(*) from stage_events").fetchone()[0] == len(clean_result.stage_events)


def _hash_dir(d):
    out = {}
    for f in sorted(d.glob("*.csv")):
        out[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def test_idempotent_run_twice(gen_result, clean_result):
    root = gen_result["root"]
    before = _hash_dir(root / "data" / "clean")
    report_before = (root / "outputs" / "data_quality_report.md").read_text()
    clean.run_clean(root)
    assert _hash_dir(root / "data" / "clean") == before
    assert (root / "outputs" / "data_quality_report.md").read_text() == report_before


def test_idempotent_clean_of_clean(clean_result):
    res = clean_result
    again = clean.clean_tables({"agencies": res.agencies, "touches": res.touches,
                                "submissions": res.submissions, "experiment_assignments": res.assignments})
    pd.testing.assert_frame_equal(again.agencies.reset_index(drop=True), res.agencies.reset_index(drop=True), check_dtype=False)
    pd.testing.assert_frame_equal(again.submissions.reset_index(drop=True), res.submissions.reset_index(drop=True), check_dtype=False)
    assert len(again.touches) == len(res.touches) and len(again.quarantine) == 0


def test_cleaning_does_not_depend_on_manifest(gen_result, tmp_path):
    root2 = tmp_path / "nomanifest"
    shutil.copytree(gen_result["root"] / "data" / "raw", root2 / "data" / "raw")
    (root2 / "data" / "raw" / "injected_defects.json").unlink()
    clean.run_clean(root2)
    assert _hash_dir(root2 / "data" / "clean") == _hash_dir(gen_result["root"] / "data" / "clean")


def test_quality_report_and_quarantine_files(gen_result, clean_result):
    rep = (gen_result["root"] / "outputs" / "data_quality_report.md").read_text()
    for k in ["duplicate_agencies", "missing_state", "missing_size", "mixed_size_formats", "inconsistent_source_labels",
              "bind_rate_over_100", "negative_turnaround", "quote_before_submission", "bound_before_quote", "SYNTHETIC"]:
        assert k in rep
    q = pd.read_csv(gen_result["root"] / "data" / "clean" / "quarantine.csv")
    assert {"table", "record_id", "issue", "action", "detail"} <= set(q.columns)
    assert q.detail.notna().all()


def test_parse_size_and_bucket():
    assert clean.parse_size("11-25") == 18
    assert clean.parse_size("18 producers") == 18
    assert clean.parse_size("18.0") == 18
    assert clean.parse_size("51+") == 51
    assert pd.isna(clean.parse_size("n/a")) and pd.isna(clean.parse_size(""))
    assert [clean.size_bucket(n) for n in (1, 3, 8, 20, 40, 90)] == ["1-2", "3-5", "6-10", "11-25", "26-50", "51+"]


def test_suppress_small_n():
    df = pd.DataFrame({"n": [5, 50], "rate": [1.0, 0.4]})
    out = clean.suppress_small_n(df, "n", ["rate"], min_n=20)
    assert pd.isna(out.loc[0, "rate"]) and out.loc[1, "rate"] == 0.4
    assert out.suppressed.tolist() == [True, False]


def test_tiny_sources_flagged_in_stats(clean_result):
    assert set(clean_result.stats["tiny_n_sources"]) == set(generate.TINY_SOURCES)
