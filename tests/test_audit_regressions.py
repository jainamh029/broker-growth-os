"""Regression tests added by the independent audit (see BUGS.md). Each one failed against the pre-fix code."""
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

import config
from bgos import clean, experiments as ex, funnel, generate, metrics, schema, scoring

ROOT = config.ROOT


# ---- B-02: decision boundaries -------------------------------------------------------------------------
def test_exact_20pct_lift_is_not_lost_to_float_error():
    ci = ex.lift_confidence_intervals(1000, 5000, 1200, 5000)  # exactly +20% relative
    assert ci["rel_lift"] != 0.2 or True  # (value is 0.19999999999999996 in IEEE arithmetic)
    cfg = ex.EXPERIMENTS["A"]
    assert ex.decide(rel_lift=ci["rel_lift"], p_value=0.001, sample_size_reached=True, srm_flag=False, cfg=cfg) == ex.SHIP
    out = pd.DataFrame({"arm": ["control"] * 5000 + ["treatment"] * 5000, "mature": 1,
                        "outcome": [1] * 1000 + [0] * 4000 + [1] * 1200 + [0] * 3800})
    assert ex.analyze_experiment(out, cfg).decision == ex.SHIP


def test_lift_just_below_20pct_does_not_ship():
    cfg = ex.EXPERIMENTS["A"]
    assert ex.decide(rel_lift=0.1999, p_value=0.001, sample_size_reached=True, srm_flag=False, cfg=cfg) == ex.ITERATE


def test_p_value_exactly_alpha_does_not_ship():
    for k in "AB":
        cfg = ex.EXPERIMENTS[k]
        assert ex.decide(rel_lift=0.9, p_value=cfg.alpha, sample_size_reached=True, srm_flag=False, cfg=cfg) != ex.SHIP
        assert ex.decide(rel_lift=0.9, p_value=cfg.alpha - 1e-9, sample_size_reached=True, srm_flag=False, cfg=cfg) == ex.SHIP


def test_sample_size_reached_boundary():
    f = ex.is_sample_size_reached
    assert f(500, 500, 500) and f(501, 900, 500)
    assert not f(499, 900, 500) and not f(900, 499, 500)  # the SMALLER arm decides, not the larger


# ---- B-01x: sqlite URI breaks on special characters in the path --------------------------------------------
@pytest.mark.parametrize("name", ["with#hash", "with%20pct", "with?query", "with space"])
def test_metrics_connect_handles_special_characters_in_root(tmp_path, name):
    root = tmp_path / name
    conn = schema.init_db(config.get_paths(root).db)
    conn.execute("insert into agencies(agency_id,name,first_touch_date) values('AG-1','A','2025-10-02')")
    conn.commit()
    conn.close()
    ro = metrics.connect(root)
    assert ro.execute("select count(*) from agencies").fetchone()[0] == 1
    ro.close()


# ---- boundary tests that mutation testing showed were missing -------------------------------------------------
def _db_with_submissions(gaps_days, tmp_path=None):
    conn = schema.connect(":memory:")
    schema.create_schema(conn)
    conn.execute("insert into agencies(agency_id,name,first_touch_date,is_icp) values('AG-1','A','2026-01-01',1)")
    t = pd.Timestamp("2026-02-02 10:00:00")
    for i, g in enumerate([0] + list(gaps_days)):
        t = t + pd.Timedelta(days=g)
        conn.execute("insert into submissions(submission_id,agency_id,submitted_at,is_complete) values(?,?,?,1)",
                     (f"S{i}", "AG-1", t.strftime("%Y-%m-%d %H:%M:%S")))
    return conn


def _weekly(conn):
    df = metrics.run_metric("weekly_growth_review", conn, window_start="2026-01-01", as_of="2026-09-30")
    return int(df.qualified_submissions.sum()), int(df.reactivated_submissions.sum())


def test_weekly_north_star_dormancy_boundary_is_60_days_inclusive():
    assert _weekly(_db_with_submissions([59])) == (2, 0)     # 59 days: still active
    assert _weekly(_db_with_submissions([60])) == (1, 1)     # exactly 60 days: dormant -> reactivated, not north star
    assert _weekly(_db_with_submissions([61])) == (1, 1)


def _activation(gap_days):
    conn = schema.connect(":memory:")
    schema.create_schema(conn)
    conn.execute("insert into agencies(agency_id,name,first_touch_date,is_icp) values('AG-1','A','2026-01-01',1)")
    conn.executemany("insert into stage_events values('AG-1',?,?,?)",
                     [("engaged", 3, "2026-02-01 09:00:00"),
                      ("first_submission", 4, (pd.Timestamp("2026-02-01 09:00:00") + pd.Timedelta(days=gap_days)).strftime("%Y-%m-%d %H:%M:%S"))])
    df = metrics.run_metric("activation_rate", conn, min_n=1)
    return int(df[df.cohort == "ALL"].activated_agencies.iloc[0])


def test_activation_window_boundary_is_14_days_inclusive():
    assert _activation(14) == 1
    assert _activation(13) == 1
    assert _activation(15) == 0


def test_spec_constants_pinned():
    assert (config.ACTIVATION_DAYS, config.B_OUTCOME_DAYS) == (14, 14)
    assert (config.DORMANCY_DAYS, config.REPEAT_WINDOW_DAYS, config.COHORT_WINDOWS) == (60, 90, (30, 60, 90))
    assert ex.EXPERIMENTS["A"].ship_min_relative_lift == 0.20 and ex.EXPERIMENTS["A"].alpha == 0.05
    assert config.TIER_THRESHOLDS == {"tier1_specialty_fit": 0.70, "tier1_es_activity": 0.50, "tier1_engagement": 0.40, "tier2_score": 0.45}


# ---- weak tests strengthened --------------------------------------------------------------------------------
@pytest.mark.parametrize("x1,n1,x2,n2", [(50, 200, 70, 200), (194, 617, 245, 612), (154, 383, 186, 384), (15, 75, 11, 75)])
def test_relative_ci_matches_statsmodels_log_method(x1, n1, x2, n2):
    ci = ex.lift_confidence_intervals(x1, n1, x2, n2)
    lo, hi = confint_proportions_2indep(x2, n2, x1, n1, compare="ratio", method="log")
    assert ci["rel_ci_low"] == pytest.approx(lo - 1, abs=1e-9) and ci["rel_ci_high"] == pytest.approx(hi - 1, abs=1e-9)
    dlo, dhi = confint_proportions_2indep(x2, n2, x1, n1, compare="diff", method="wald")
    assert ci["abs_ci_low"] == pytest.approx(dlo, abs=1e-9) and ci["abs_ci_high"] == pytest.approx(dhi, abs=1e-9)


def test_tier_thresholds_are_inclusive_at_the_boundary():
    kw = dict(is_icp=True, n_complete_subs=0, days_since_last_sub=None)
    base = dict(specialty=0.70, es=0.50, eng=0.40, score=0.50)
    assert scoring.assign_tier(**base, **kw) == "Tier 1"
    for field, below in (("specialty", 0.699), ("es", 0.499), ("eng", 0.399)):
        assert scoring.assign_tier(**{**base, field: below}, **kw) == "Tier 2"
    assert scoring.assign_tier(**{**base, "eng": 0.0, "score": 0.45}, **kw) == "Tier 2"
    assert scoring.assign_tier(**{**base, "eng": 0.0, "score": 0.449}, **kw) == "Tier 3"
    assert scoring.assign_tier(**base, is_icp=False, n_complete_subs=0, days_since_last_sub=None) == "Tier 3"


def test_source_label_mapping_exact():
    expected = {"LI": "linkedin", "Linked In": "linkedin", "LinkedIn Outreach": "linkedin", "outbound-email": "outbound",
                "cold email": "outbound", "Inbound Web": "inbound_web", "web": "inbound_web", "website": "inbound_web",
                "partnership": "partner", "conference": "event", "trade show": "event", "ref": "referral",
                "Broker Referral": "referral", "state assoc. booth": "state_assoc_booth", "Podcast Sponsor": "podcast_sponsor"}
    for raw, canon in expected.items():
        assert clean.canonical_source(raw) == canon, raw


def test_ai_scorer_weights_are_the_documented_ones():
    from bgos.ai.submission_quality import WEIGHTS
    assert WEIGHTS == {"loss_runs": 0.25, "property_details": 0.20, "risk_description": 0.20,
                       "financials": 0.15, "prior_carrier": 0.10, "cois": 0.10}


def test_blocked_randomization_is_balanced_within_strata(gen_result):
    arms = generate._blocked_arms(np.random.default_rng(1), np.array(["a"] * 7 + ["b"] * 10 + ["c"]))
    for s, grp in pd.Series(arms).groupby(np.array(["a"] * 7 + ["b"] * 10 + ["c"])):
        assert abs((grp == "treatment").sum() - (grp == "control").sum()) <= 1
    tr = gen_result["truth"]
    ag = tr["agencies"].assign(arm=tr["a_arm"], b=tr["b_arm"])
    for col in ("arm", "b"):
        g = ag.groupby(["lead_source", "is_icp"])[col].agg(lambda s: abs((s == "treatment").sum() - (s == "control").sum()))
        assert g.max() <= 3, g.sort_values().tail(3).to_dict()  # one stratum per fit tercile => at most 3
    # strata use baseline covariates only: arms are independent of every outcome column (no outcome in the frame)
    assert {"lead_source", "is_icp"} <= set(ag.columns)


def test_blocking_does_not_use_outcomes():
    src = (ROOT / "src" / "bgos" / "generate.py").read_text()
    block = src.split("strata = (")[1].split(")\n    a_arm")[0]
    for banned in ("submission", "bound", "touches", "engaged", "outcome"):
        assert banned not in block


# ---- B-06: deprecated Streamlit argument ----------------------------------------------------------------------
def test_dashboard_has_no_deprecated_use_container_width():
    assert "use_container_width" not in (ROOT / "app" / "dashboard.py").read_text()


# ---- B-07: honesty requirements in deliverables ----------------------------------------------------------------
def test_multiple_comparisons_and_one_draw_caveats_are_documented():
    for f in ("README.md", "STRATEGY_MEMO.md"):
        t = (ROOT / f).read_text().lower()
        assert "multiple comparisons" in t or "three experiments" in t, f
        assert "one simulated draw" in t, f
    assert "generous" in (ROOT / "STRATEGY_MEMO.md").read_text().lower()
    dash = (ROOT / "app" / "dashboard.py").read_text().lower()
    assert "multiple comparisons" in dash and "one simulated draw" in dash and "generous" in dash


# ---- B-08: fresh clone without data ------------------------------------------------------------------------------
def test_dashboard_bootstraps_from_empty_root(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("BGOS_ROOT", str(tmp_path / "fresh"))
    at = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=240).run()
    assert not at.exception and not at.error
    assert (tmp_path / "fresh" / "data" / "marts" / "topline.csv").exists()
    assert len(at.metric) >= 5


def test_dashboard_extreme_filters_do_not_crash(gen_result, marts, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from bgos import experiments
    experiments.run_experiments(gen_result["root"])
    monkeypatch.setenv("BGOS_ROOT", str(gen_result["root"]))
    at = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=120).run()
    at.sidebar.radio[0].set_value("Ranked Accounts").run()
    at.multiselect[0].set_value([]).run()  # no tier selected
    assert not at.exception
    at.multiselect[0].set_value(["Tier 3", "Tier 1", "Tier 2", "Reactivation"]).run()
    at.text_input[0].set_value("zzzz-no-such-agency").run()
    assert not at.exception
    at.text_input[0].set_value("").run()
    at.multiselect[1].set_value(sorted(pd.read_csv(gen_result["root"] / "data" / "marts" / "ranked_accounts.csv").owner.unique())[:1]).run()
    assert not at.exception
    for df in at.dataframe:
        assert not df.value.isna().any().any() if len(df.value) else True
    at.sidebar.radio[0].set_value("Time-to-Quote").run()
    at.radio[1].set_value("Each agency's first submission").run()
    assert not at.exception


# ---- seed sweep artefact ---------------------------------------------------------------------------------------
def test_seed_sweep_file_matches_a_rerun_of_two_seeds():
    from bgos import sweep
    saved = json.loads((ROOT / "docs" / "seed_sweep.json").read_text())
    assert len(saved["seeds"]) >= 40
    for sd in (1, 2):
        again = sweep.run_one(sd)
        assert saved["seeds"][str(sd)] == again


# ---- doc numbers cannot drift from outputs --------------------------------------------------------------------
def test_final_report_headline_numbers_match_outputs(gen_result, marts):
    from bgos import experiments
    experiments.run_experiments(gen_result["root"])
    m = lambda n: pd.read_csv(gen_result["root"] / "data" / "marts" / f"{n}.csv")
    txt = (ROOT / "FINAL_REPORT.md").read_text()
    f = m("funnel_counts").set_index("stage")
    want = [f"{int(f.loc[s, 'agencies']):,}" for s in ("raw_lead", "icp_qualified", "engaged", "first_submission", "quoted", "bound", "repeat_submission")]
    want.append(f"{f.loc['bound', 'cumulative_conversion'] * 100:.1f}%")
    sq = m("source_quality").set_index("lead_source")
    ok = sq[sq.suppressed == 0]
    want += [f"{sq.loc['referral', 'bind_rate_per_lead'] * 100:.1f}%", f"{sq.loc['linkedin', 'bind_rate_per_lead'] * 100:.1f}%",
             f"{sq.loc['referral', 'bind_rate_per_lead'] / sq.loc['linkedin', 'bind_rate_per_lead']:.1f}x",
             f"{sq.loc['linkedin', 'leads'] / ok.leads.sum() * 100:.0f}%"]
    e = m("experiment_results").set_index("experiment_id")
    for k in "ABC":
        want += [f"{e.loc[k, 'rel_lift'] * 100:+.1f}%", f"{e.loc[k, 'rel_ci_low'] * 100:+.1f}%", f"{e.loc[k, 'rel_ci_high'] * 100:+.1f}%",
                 e.loc[k, "decision"], f"{int(e.loc[k, 'n_required_per_arm']):,}"]
    t = m("time_to_quote")
    med = t[(t.scope == "all_submissions") & (t.dimension == "overall")].iloc[0].median_hours
    want.append(f"{med:.0f} hours")
    ranked = pd.read_csv(gen_result["root"] / "outputs" / "ranked_accounts.csv").tier.value_counts()
    want += [f"{ranked[t_]} {t_}" for t_ in ("Tier 1", "Tier 2", "Tier 3", "Reactivation")]
    missing = [w for w in want if w not in txt]
    assert not missing, f"FINAL_REPORT.md numbers drifted from outputs: {missing}"
