import hashlib
import json
import re

import pandas as pd
import pytest

import config
from bgos import funnel, generate

BLANK = {"", "n/a", "na", "unknown", "null", "none"}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_row_counts_in_range(gen_result):
    raw, m = gen_result["raw"], gen_result["manifest"]
    assert len(raw["agencies"]) == config.N_TRUE_AGENCIES + m["counts"]["duplicate_agencies"]
    assert 1450 <= config.N_TRUE_AGENCIES <= 1550
    assert 60 <= m["counts"]["duplicate_agencies"] <= 90  # ~5%
    assert 5_000 <= len(raw["touches"]) <= 25_000
    assert 1_500 <= len(raw["submissions"]) <= 8_000
    assert set(raw["experiment_assignments"].experiment_id) == {"A", "B", "C"}


def test_seeded_determinism(gen_result, tmp_path):
    root2 = tmp_path / "again"
    generate.generate(root=root2)
    for f in ["agencies.csv", "touches.csv", "submissions.csv", "experiment_assignments.csv", "injected_defects.json"]:
        assert _sha(gen_result["root"] / "data" / "raw" / f) == _sha(root2 / "data" / "raw" / f), f


def test_different_seed_differs(tmp_path):
    a = generate.generate(root=tmp_path / "s", seed=1, n_agencies=200, write=False)["raw"]["agencies"]
    b = generate.generate(root=tmp_path / "t", seed=2, n_agencies=200, write=False)["raw"]["agencies"]
    assert not a.equals(b)


def test_funnel_monotone_non_increasing(gen_result):
    tr = gen_result["truth"]
    ag = tr["agencies"].copy()
    ag["is_icp"] = ag["is_icp"].astype(int)
    ev = funnel.derive_stage_events(ag, tr["touches"], tr["submissions"])
    counts = funnel.funnel_counts(ev)
    assert counts.is_monotonic_decreasing, counts.to_dict()
    assert counts["raw_lead"] == config.N_TRUE_AGENCIES
    # heavy top of funnel, real tapering
    assert counts["raw_lead"] > 2 * counts["first_submission"] > 4 * counts["bound"] * 0.9


def test_defect_counts_match_manifest(gen_result):
    raw, m = gen_result["raw"], gen_result["manifest"]
    ag, sb = raw["agencies"], raw["submissions"]
    c = m["counts"]
    assert ag.state.fillna("").str.strip().str.lower().isin(BLANK).sum() == c["missing_state"]
    assert ag.size_producers.fillna("").str.strip().str.lower().isin(BLANK).sum() == c["missing_size"]
    plain = ag.size_producers.fillna("").str.fullmatch(r"\d+")
    blank = ag.size_producers.fillna("").str.strip().str.lower().isin(BLANK)
    assert (~plain & ~blank).sum() == c["mixed_size_formats"]
    assert (~ag.lead_source.isin(generate.CANONICAL_SOURCES)).sum() == c["inconsistent_source_labels"]
    assert (ag.prior_bind_rate_pct.astype(float) > 100).sum() == c["bind_rate_over_100"]
    sub, quo, bnd = (pd.to_datetime(sb[k]) for k in ("submitted_at", "quoted_at", "bound_at"))
    qbs = quo < sub
    assert qbs.sum() == c["quote_before_submission"]
    assert ((bnd < quo) & ~qbs).sum() == c["bound_before_quote"]
    assert ((sb.quote_turnaround_hours < 0) & ~qbs).sum() == c["negative_turnaround"]
    # duplicates listed in the manifest exist in the raw table and point at a real agency
    dups = m["details"]["duplicates"]
    assert len(dups) == c["duplicate_agencies"]
    assert set(dups) <= set(ag.agency_id) and set(dups.values()) <= set(ag.agency_id)
    # 2-3 tiny-n sources, each fully converting
    assert c["tiny_n_sources"] in (2, 3)
    assert set(m["details"]["tiny_n_sources"]) <= set(ag.lead_source.map(lambda x: x)) | set(generate.TINY_SOURCES)


def test_tiny_n_sources_show_100pct_bound(gen_result):
    tr = gen_result["truth"]
    ag, sb = tr["agencies"], tr["submissions"]
    bound = set(sb[sb.outcome == "bound"].agency_id)
    for src, n in generate.TINY_SOURCES.items():
        ids = ag[ag.lead_source == src].agency_id
        assert len(ids) == n and n <= 5
        assert set(ids) <= bound


def test_planted_effects_recorded(gen_result):
    gt = gen_result["manifest"]["ground_truth"]
    assert gt["experiment_A"]["true_relative_lift"] == pytest.approx(0.30)
    assert gt["experiment_B"]["true_relative_lift"] == pytest.approx(0.15)
    assert gt["experiment_C"]["true_relative_lift"] == 0.0
    assert gt["source_quality"]["highest_quality_low_volume"] == "referral"
    on_disk = json.loads((gen_result["root"] / "data" / "raw" / "injected_defects.json").read_text())
    assert on_disk["counts"] == gen_result["manifest"]["counts"]


def test_dates_inside_window(gen_result):
    raw = gen_result["raw"]
    lo, hi = pd.Timestamp(config.WINDOW_START), pd.Timestamp(config.WINDOW_END) + pd.Timedelta(days=1)
    for tbl, cols in {"agencies": ["first_touch_date", "last_activity_date"], "touches": ["touched_at"],
                      "submissions": ["submitted_at", "quoted_at", "bound_at"],
                      "experiment_assignments": ["assigned_at"]}.items():
        for c in cols:
            d = pd.to_datetime(raw[tbl][c]).dropna()
            assert d.min() >= lo and d.max() < hi, (tbl, c, d.min(), d.max())


def test_source_quality_shape(gen_result):
    tr = gen_result["truth"]
    ag = tr["agencies"]
    tr_ag = ag.copy(); tr_ag["is_icp"] = tr_ag["is_icp"].astype(int)
    ev = funnel.derive_stage_events(tr_ag, tr["touches"], tr["submissions"])
    bound = set(ev[ev.stage == "bound"].agency_id)
    vol = ag.lead_source.value_counts()
    big = ag[ag.lead_source.isin(generate.SOURCE_WEIGHTS)]
    rate = big.assign(b=big.agency_id.isin(bound)).groupby("lead_source")["b"].mean()
    assert vol["linkedin"] == vol[list(generate.SOURCE_WEIGHTS)].max()
    assert vol["referral"] == vol[list(generate.SOURCE_WEIGHTS)].min()
    # NOTE (audit B-10): on one small draw (referral n~113) the bind-rate ordering at the top is noisy, so the full
    # ordering is verified at large n in test_audit_regressions.py; here we keep the robust parts.
    assert rate["linkedin"] == rate.min()
    assert rate["referral"] >= rate.drop("referral").median()


def test_children_reference_known_agencies(gen_result):
    raw = gen_result["raw"]
    ids = set(raw["agencies"].agency_id)
    assert set(raw["touches"].agency_id) <= ids
    assert set(raw["submissions"].agency_id) <= ids
    assert set(raw["experiment_assignments"].agency_id) <= ids
    assert raw["agencies"].agency_id.is_unique and raw["submissions"].submission_id.is_unique
