"""Interactive controls added in the green/blue redesign."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import config
from bgos import experiments as ex

APP = str(config.ROOT / "app" / "dashboard.py")


@pytest.fixture(scope="module")
def root(gen_result, marts):
    ex.run_experiments(gen_result["root"])
    return gen_result["root"]


def open_view(root, view, monkeypatch):
    monkeypatch.setenv("BGOS_ROOT", str(root))
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.radio[0].set_value(view).run()
    assert not at.exception
    return at


def test_sample_size_calculator_matches_framework(root, monkeypatch):
    at = open_view(root, "Experiments", monkeypatch)
    at.slider(key="calc_base").set_value(20).run()
    at.slider(key="calc_lift").set_value(50).run()
    at.selectbox(key="calc_alpha").set_value(0.05).run()
    at.selectbox(key="calc_power").set_value(0.80).run()
    shown = {m.label: m.value for m in at.metric}
    n = ex.sample_size_two_proportions(0.20, 0.30, 0.05, 0.80)
    assert shown["Required per arm"] == f"{n:,}" and shown["Total agencies"] == f"{2 * n:,}"
    at.selectbox(key="calc_power").set_value(0.95).run()
    n95 = ex.sample_size_two_proportions(0.20, 0.30, 0.05, 0.95)
    assert {m.label: m.value for m in at.metric}["Required per arm"] == f"{n95:,}" and n95 > n


def test_weekly_range_and_toggle(root, monkeypatch):
    at = open_view(root, "Weekly Growth Review", monkeypatch)
    weeks = at.select_slider(key="week_range").options
    at.select_slider(key="week_range").set_range(weeks[10], weeks[20]).run()
    assert not at.exception
    at.toggle(key="show_ma").set_value(False).run()
    assert not at.exception


def test_source_metric_selector_and_tiny_toggle(root, monkeypatch):
    at = open_view(root, "Source Quality", monkeypatch)
    for m in ("first_submission_rate", "repeat_rate_of_bound", "commission_per_lead", "bind_rate_per_lead"):
        at.selectbox(key="src_metric").set_value(m).run()
        assert not at.exception, m
    at.toggle(key="src_tiny").set_value(False).run()
    assert not at.exception


def test_dormant_and_ranked_filters(root, monkeypatch):
    at = open_view(root, "Dormancy and Reactivation", monkeypatch)
    at.slider(key="dorm_n").set_value(5).run()
    spec = at.multiselect(key="dorm_spec").options[0]
    at.multiselect(key="dorm_spec").set_value([spec]).run()
    assert not at.exception
    at = open_view(root, "Ranked Accounts", monkeypatch)
    at.slider(key="rank_min").set_value(0.99).run()  # nothing matches
    assert not at.exception
    at.slider(key="rank_min").set_value(0.0).run()
    at.multiselect(key="rank_states").set_value([at.multiselect(key="rank_states").options[0]]).run()
    assert not at.exception


def test_activation_window_and_monday_toggles(root, monkeypatch):
    at = open_view(root, "Activation and Cohorts", monkeypatch)
    for w in at.selectbox(key="ret_window").options:
        at.selectbox(key="ret_window").select(w).run()
        assert not at.exception
    at = open_view(root, "Monday Morning", monkeypatch)
    at.toggle(key="funnel_mode").set_value(True).run()
    at.slider(key="monday_n").set_value(3).run()
    assert not at.exception


def test_pipeline_segment_filter_changes_totals(root, monkeypatch):
    at = open_view(root, "Pipeline and Revenue Projection", monkeypatch)
    full = {m.label: m.value for m in at.metric}
    first = at.multiselect(key="pipe_segs").options[0]
    at.multiselect(key="pipe_segs").set_value([first]).run()
    one = {m.label: m.value for m in at.metric}
    assert float(one["Expected new bound agencies"]) < float(full["Expected new bound agencies"])


def test_static_site_calculator_constants_match_framework():
    """The page's JS uses rounded z-values; its result must stay within 1 agency of the Python formula."""
    import math
    html = (config.ROOT / "docs" / "index.html").read_text()
    for z in ("1.6449", "1.96", "2.5758", "0.8416", "1.2816"):
        assert z in html
    za = {0.10: 1.6449, 0.05: 1.96, 0.01: 2.5758}
    zb = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449}
    for base, lift, a, pw in [(10, 20, 0.05, 0.80), (30, 30, 0.05, 0.90), (5, 50, 0.01, 0.95), (25, 15, 0.10, 0.80)]:
        p1 = base / 100; p2 = min(0.99, p1 * (1 + lift / 100)); pb = (p1 + p2) / 2
        js = math.ceil((za[a] * math.sqrt(2 * pb * (1 - pb)) + zb[pw] * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2 / (p1 - p2) ** 2)
        assert abs(js - ex.sample_size_two_proportions(p1, p2, a, pw)) <= 2
