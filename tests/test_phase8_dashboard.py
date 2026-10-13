import os
import socket
import subprocess
import sys
import time
import urllib.request

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import config
from bgos import insights, metrics

APP = str(config.ROOT / "app" / "dashboard.py")
VIEWS = ["Monday Morning", "Weekly Growth Review", "Source Quality", "Time-to-Quote", "Activation and Cohorts",
         "Dormancy and Reactivation", "Pipeline and Revenue Projection", "Ranked Accounts", "Experiments"]
BANNER = "Synthetic data. Demonstrates the method, not Hedge's actual performance."


@pytest.fixture(scope="module")
def pipeline_root(gen_result, marts):
    from bgos import experiments
    experiments.run_experiments(gen_result["root"])
    return gen_result["root"]


def run_view(root, view, monkeypatch):
    monkeypatch.setenv("BGOS_ROOT", str(root))
    at = AppTest.from_file(APP, default_timeout=90).run()
    assert not at.exception, at.exception
    at.sidebar.radio[0].set_value(view).run()
    return at


@pytest.mark.parametrize("view", VIEWS)
def test_every_view_renders_without_exception_and_has_banner_and_takeaway(view, pipeline_root, monkeypatch):
    at = run_view(pipeline_root, view, monkeypatch)
    assert not at.exception, at.exception
    md = [m.value for m in at.markdown]
    assert any(BANNER in m for m in md), "synthetic-data banner missing"
    assert any("Takeaway." in m for m in md), "chart takeaway missing"
    assert len(at.subheader) >= 1 or len(at.markdown) > 3


def test_all_views_listed():
    src = open(APP).read()
    for v in VIEWS:
        assert f'"{v}"' in src


def test_monday_headline_numbers_equal_metrics_layer(pipeline_root, monkeypatch):
    at = run_view(pipeline_root, "Monday Morning", monkeypatch)
    conn = metrics.connect(pipeline_root)
    t = metrics.run_metric("topline", conn).iloc[0]
    shown = {m.label: m.value for m in at.metric}
    assert shown["New ICP agencies (7d)"] == f"{int(t.new_icp_7d):,}"
    assert shown["Complete submissions (7d)"] == f"{int(t.complete_submissions_7d):,}"
    assert shown["Active agencies (60d)"] == f"{int(t.active_agencies_60d):,}"
    assert shown["Dormant agencies"] == f"{int(t.dormant_agencies):,}"
    assert shown["ICP-qualified agencies"] == f"{int(t.icp_agencies):,}"
    assert shown["Commission, last 90d"] == insights.money(t.commission_last_90d)
    f = metrics.run_metric("funnel_counts", conn)
    take = [m.value for m in at.markdown if "Takeaway." in m.value][0]
    assert f"{int(f.iloc[0].agencies):,}" in take
    conn.close()


def test_experiment_view_matches_results(pipeline_root, monkeypatch):
    at = run_view(pipeline_root, "Experiments", monkeypatch)
    e = pd.read_csv(pipeline_root / "data" / "marts" / "experiment_results.csv")
    decisions = [m.value for m in at.metric if m.label == "Decision"]
    assert decisions == e.decision.tolist()
    assert any("SIMULATED" in w.value for w in at.warning)


def test_pipeline_view_totals_match_metric(pipeline_root, monkeypatch):
    at = run_view(pipeline_root, "Pipeline and Revenue Projection", monkeypatch)
    conn = metrics.connect(pipeline_root)
    p = metrics.run_metric("pipeline_projection", conn)
    shown = {m.label: m.value for m in at.metric}
    assert shown["Projected first-bind commission"] == insights.money(p.projected_commission.sum())
    assert shown["Expected new bound agencies"] == f"{p.expected_new_bound_agencies.sum():.0f}"
    conn.close()


def test_no_hardcoded_numbers_in_dashboard_source():
    import re
    src = open(APP).read()
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "read_csv" in body and "marts" in body
    # headline literals such as "1,500" or "$2.3M" must not appear
    assert not re.search(r"\$\d|\b\d{1,3},\d{3}\b", body)


def test_takeaways_use_data(pipeline_root):
    sq = pd.read_csv(pipeline_root / "data" / "marts" / "source_quality.csv")
    s = insights.takeaway_sources(sq)
    ok = sq[sq.suppressed == 0]
    assert ok.loc[ok.bind_rate_per_lead.idxmax(), "lead_source"] in s and ok.loc[ok.bind_rate_per_lead.idxmin(), "lead_source"] in s
    w = pd.read_csv(pipeline_root / "data" / "marts" / "weekly_growth_review.csv")
    full = w[w.is_partial_week == 0]
    assert f"{full.tail(4).qualified_submissions.mean():.1f}" in insights.takeaway_north_star(w)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_streamlit_runs_headless_and_health_ok(pipeline_root):
    port = _free_port()
    env = {**os.environ, "BGOS_ROOT": str(pipeline_root)}
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", APP, "--server.headless", "true",
                             "--server.port", str(port), "--server.address", "127.0.0.1",
                             "--browser.gatherUsageStats", "false"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(config.ROOT))
    try:
        ok = False
        for _ in range(90):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as r:
                    if r.read().decode().strip().lower() == "ok":
                        ok = True
                        break
            except Exception:
                time.sleep(1)
        assert ok, "streamlit health check never returned ok"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
