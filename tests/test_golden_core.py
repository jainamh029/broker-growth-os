"""Golden values for the FROZEN core (seed 42, 3,000 agencies). Presentation, documentation and reporting work must never move these.
If one fails you introduced a regression in generated data, scoring, SQL metrics or experiment statistics: revert it."""
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def golden(gen_result, marts):
    from bgos import experiments
    experiments.run_experiments(gen_result["root"])
    root = gen_result["root"]
    m = lambda n: pd.read_csv(root / "data" / "marts" / f"{n}.csv")
    return dict(exp=m("experiment_results").set_index("experiment_id"), funnel=m("funnel_counts").set_index("stage"),
                ranked=pd.read_csv(root / "outputs" / "ranked_accounts.csv"), hold=m("tier_holdout").set_index("tier"))


def test_experiment_a(golden):
    r = golden["exp"].loc["A"]
    assert (r.x_control, r.n_control, r.x_treatment, r.n_treatment) == (394, 1221, 504, 1245)
    assert r.rel_lift == pytest.approx(0.2545, abs=5e-5)
    assert r.p_value == pytest.approx(2.2567e-05, rel=1e-3)
    assert r.n_required_per_arm == 862 and r.decision == "SHIP"


def test_experiment_b(golden):
    r = golden["exp"].loc["B"]
    assert (r.x_control, r.n_control, r.x_treatment, r.n_treatment) == (295, 801, 349, 822)
    assert r.rel_lift == pytest.approx(0.1528, abs=5e-5)
    assert r.p_value == pytest.approx(0.020492, rel=1e-4)
    assert r.n_required_per_arm == 2744 and r.decision == "ITERATE"


def test_experiment_c(golden):
    r = golden["exp"].loc["C"]
    assert (r.x_control, r.n_control, r.x_treatment, r.n_treatment) == (33, 147, 28, 147)
    assert r.p_value == pytest.approx(0.472068, rel=1e-4)
    assert r.n_required_per_arm == 940 and r.decision == "INCONCLUSIVE"


def test_segments(golden):
    assert golden["ranked"].tier.value_counts().to_dict() == {"Tier 3": 1193, "Tier 2": 706, "Active": 672, "Reactivation": 405, "Tier 1": 24}


def test_funnel(golden):
    f = golden["funnel"]
    order = ["raw_lead", "icp_qualified", "engaged", "first_submission", "quoted", "bound", "repeat_submission"]
    assert [int(f.loc[s, "agencies"]) for s in order] == [3000, 2282, 1695, 1077, 1033, 466, 343]
    assert f.loc["bound", "mature_cumulative_conversion"] == pytest.approx(0.2170, abs=5e-5)
    assert f.loc["bound", "observed_cumulative_conversion"] == pytest.approx(0.1553, abs=5e-5)


def test_holdout(golden):
    h = golden["hold"]
    assert [(int(h.loc[t, "converted"]), int(h.loc[t, "prospects"])) for t in ("Tier 1", "Tier 2", "Tier 3")] == [(9, 32), (62, 531), (5, 885)]
    assert h.scored_as_of.iloc[0] == "2026-07-02"
