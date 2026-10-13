import pytest

import config
from bgos import generate


@pytest.fixture(scope="session")
def gen_result(tmp_path_factory):
    """One generated dataset (written to a temp dir) shared across tests."""
    root = tmp_path_factory.mktemp("gen")
    res = generate.generate(root=root)
    res["root"] = root
    return res


@pytest.fixture(scope="session")
def clean_result(gen_result):
    from bgos import clean
    res = clean.run_clean(gen_result["root"])
    return res


@pytest.fixture(scope="session")
def scored(gen_result, clean_result):
    from bgos import scoring
    return scoring.run_score(gen_result["root"])


@pytest.fixture(scope="session")
def marts(gen_result, clean_result, scored):
    from bgos import metrics
    return metrics.run_all(gen_result["root"])


@pytest.fixture(scope="session")
def clean_tables(gen_result, clean_result):
    """Clean CSVs loaded from disk with parsed datetimes (independent of SQL/stage_events)."""
    import pandas as pd
    d = gen_result["root"] / "data" / "clean"
    ag = pd.read_csv(d / "agencies.csv")
    tc = pd.read_csv(d / "touches.csv", parse_dates=["touched_at"])
    sb = pd.read_csv(d / "submissions.csv", parse_dates=["submitted_at", "quoted_at", "bound_at"])
    asg = pd.read_csv(d / "experiment_assignments.csv", parse_dates=["assigned_at"])
    return dict(agencies=ag, touches=tc, submissions=sb, assignments=asg)
