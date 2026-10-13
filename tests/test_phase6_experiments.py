import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportions_ztest

import config
from bgos import experiments as ex


def test_config_structure_complete():
    assert set(ex.EXPERIMENTS) == {"A", "B", "C"}
    for cfg in ex.EXPERIMENTS.values():
        assert cfg.hypothesis and cfg.control and cfg.treatment and cfg.primary_metric
        assert len(cfg.secondary_metrics) >= 1 and cfg.decision_rule
        assert 0 < cfg.alpha < 0.2 and 0 < cfg.mde_relative < 1
    a = ex.EXPERIMENTS["A"]
    assert a.ship_min_relative_lift == 0.20 and a.force_iterate_if_not_ship


def test_sample_size_matches_textbook():
    # Fleiss/textbook: p1=.2, p2=.3, alpha=.05, power=.8 -> ~294 per arm
    assert ex.sample_size_two_proportions(0.2, 0.3) == pytest.approx(294, abs=2)
    # independent reference: statsmodels (arcsine effect size) within 3%
    h = 2 * math.asin(math.sqrt(0.3)) - 2 * math.asin(math.sqrt(0.2))
    ref = NormalIndPower().solve_power(effect_size=h, alpha=0.05, power=0.8, ratio=1.0)
    assert ex.sample_size_two_proportions(0.2, 0.3) == pytest.approx(ref, rel=0.03)
    assert ex.sample_size_two_proportions(0.5, 0.6) == pytest.approx(388, abs=3)
    assert ex.sample_size_two_proportions(0.2, 0.3, power=0.9) > ex.sample_size_two_proportions(0.2, 0.3)
    with pytest.raises(ValueError):
        ex.sample_size_two_proportions(0.2, 0.2)


@pytest.mark.parametrize("x1,n1,x2,n2", [(50, 200, 70, 200), (30, 500, 33, 480), (200, 1000, 260, 1000), (5, 90, 12, 80)])
def test_ztest_matches_references(x1, n1, x2, n2):
    z, p = ex.two_proportion_ztest(x1, n1, x2, n2)
    z_ref, p_ref = proportions_ztest([x2, x1], [n2, n1])
    assert z == pytest.approx(z_ref, rel=1e-9) and p == pytest.approx(p_ref, rel=1e-9)
    chi2 = stats.chi2_contingency([[x1, n1 - x1], [x2, n2 - x2]], correction=False)
    assert p == pytest.approx(chi2.pvalue, rel=1e-6)


def test_confidence_intervals_formulas():
    ci = ex.lift_confidence_intervals(50, 200, 70, 200)
    assert ci["abs_lift"] == pytest.approx(0.10)
    se = math.sqrt(0.25 * 0.75 / 200 + 0.35 * 0.65 / 200)
    assert ci["abs_ci_low"] == pytest.approx(0.10 - 1.959964 * se, abs=1e-5)
    assert ci["rel_lift"] == pytest.approx(0.40)
    assert ci["rel_ci_low"] < ci["rel_lift"] < ci["rel_ci_high"]
    assert ci["rel_ci_low"] > -1


def test_relative_ci_coverage_simulation():
    rng = np.random.default_rng(config.SEED)
    p1, p2, n, hits, sims = 0.30, 0.39, 500, 0, 3000
    for _ in range(sims):
        x1, x2 = rng.binomial(n, p1), rng.binomial(n, p2)
        ci = ex.lift_confidence_intervals(x1, n, x2, n)
        hits += ci["rel_ci_low"] <= p2 / p1 - 1 <= ci["rel_ci_high"]
    assert 0.93 <= hits / sims <= 0.97


def test_achieved_power():
    assert ex.achieved_power(0.2, 0.3, 294, 294) == pytest.approx(0.80, abs=0.02)
    assert ex.achieved_power(0.2, 0.3, 50, 50) < 0.3
    assert ex.achieved_power(0.2, 0.3, 2000, 2000) > 0.99
    assert ex.achieved_power(0.2, 0.2, 100, 100) == pytest.approx(0.05)


def test_srm_flags_deliberate_skew_and_passes_balanced():
    assert ex.srm_check(5000, 5000)["flag"] is False
    assert ex.srm_check(5060, 4940)["flag"] is False
    skew = ex.srm_check(5400, 4600)
    assert skew["flag"] is True and skew["p_value"] < 1e-6


def test_decision_function_all_three_outcomes():
    cfg = ex.EXPERIMENTS["B"]  # generic (non-forced) rule
    assert ex.decide(rel_lift=0.25, p_value=0.001, sample_size_reached=True, srm_flag=False, cfg=cfg) == ex.SHIP
    assert ex.decide(rel_lift=0.03, p_value=0.01, sample_size_reached=True, srm_flag=False, cfg=cfg) == ex.ITERATE  # significant but small
    assert ex.decide(rel_lift=0.25, p_value=0.001, sample_size_reached=False, srm_flag=False, cfg=cfg) == ex.ITERATE  # underpowered: do not ship
    assert ex.decide(rel_lift=0.05, p_value=0.40, sample_size_reached=False, srm_flag=False, cfg=cfg) == ex.INCONCLUSIVE
    assert ex.decide(rel_lift=0.05, p_value=0.40, sample_size_reached=True, srm_flag=False, cfg=cfg) == ex.ITERATE  # powered null
    assert ex.decide(rel_lift=0.50, p_value=0.001, sample_size_reached=True, srm_flag=True, cfg=cfg) == ex.INCONCLUSIVE  # broken assignment
    a = ex.EXPERIMENTS["A"]  # "otherwise ITERATE the ICP definition"
    assert ex.decide(rel_lift=0.19, p_value=0.001, sample_size_reached=True, srm_flag=False, cfg=a) == ex.ITERATE
    assert ex.decide(rel_lift=0.30, p_value=0.20, sample_size_reached=True, srm_flag=False, cfg=a) == ex.ITERATE
    assert ex.decide(rel_lift=0.30, p_value=0.001, sample_size_reached=False, srm_flag=False, cfg=a) == ex.ITERATE
    assert ex.decide(rel_lift=0.20, p_value=0.049, sample_size_reached=True, srm_flag=False, cfg=a) == ex.SHIP


def _synthetic_outcomes(n, p_c, p_t, seed=1, srm_skew=None):
    rng = np.random.default_rng(seed)
    arms = np.array(["control"] * n + ["treatment"] * (n if srm_skew is None else int(n * srm_skew)))
    y = np.where(arms == "control", rng.random(len(arms)) < p_c, rng.random(len(arms)) < p_t).astype(int)
    return pd.DataFrame({"arm": arms, "mature": 1, "outcome": y})


def test_analyze_experiment_end_to_end_synthetic():
    r = ex.analyze_experiment(_synthetic_outcomes(2000, 0.25, 0.325), ex.EXPERIMENTS["A"])
    assert r.decision == ex.SHIP and r.sample_size_reached and 0.1 < r.rel_lift < 0.5
    r0 = ex.analyze_experiment(_synthetic_outcomes(80, 0.1, 0.1), ex.EXPERIMENTS["C"])
    assert r0.decision in (ex.INCONCLUSIVE, ex.ITERATE) and not r0.sample_size_reached
    rs = ex.analyze_experiment(_synthetic_outcomes(2000, 0.25, 0.325, srm_skew=0.8), ex.EXPERIMENTS["A"])
    assert rs.srm_flag and rs.decision == ex.INCONCLUSIVE


# ---- on the generated data (simulated results) -----------------------------------------------------
@pytest.fixture(scope="module")
def results(gen_result, marts):
    from bgos import experiments
    return experiments.run_experiments(gen_result["root"]).set_index("experiment_id")


def test_A_recovered_as_ship(results):
    r = results.loc["A"]
    assert r.decision == "SHIP"
    assert r.rel_lift >= 0.20 and r.p_value < 0.05 and r.sample_size_reached
    assert r.rel_ci_low <= r.planted_true_lift <= r.rel_ci_high  # the planted +30% lies inside the 95% CI
    assert 0.10 <= r.rel_lift <= 0.60  # within tolerance of the planted lift
    assert not r.srm_flag


def test_B_directionally_positive(results):
    r = results.loc["B"]
    assert r.rel_lift > 0 and r.abs_lift > 0
    assert r.rel_ci_low <= r.planted_true_lift <= r.rel_ci_high
    assert r.decision != "SHIP"  # underpowered at ~15%: we do not claim a win
    assert not r.sample_size_reached


def test_C_planted_null_is_not_ship(results):
    r = results.loc["C"]
    assert r.decision in ("INCONCLUSIVE", "ITERATE") and r.decision != "SHIP"
    assert r.rel_ci_low <= 0 <= r.rel_ci_high or r.p_value > 0.05
    assert r.planted_true_lift == 0.0


def test_report_and_results_labelled_simulated(gen_result, results):
    md = (gen_result["root"] / "outputs" / "experiment_results.md").read_text()
    assert "SIMULATED" in md and "synthetic" in md.lower()
    assert (results.note.str.contains("SIMULATED")).all()
    assert len(results) == 3


def test_srm_not_flagged_on_generated_assignments(results):
    assert not results.srm_flag.any()
