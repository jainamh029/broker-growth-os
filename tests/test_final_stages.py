"""Tests for the final credibility-layer work (stages 1-6)."""
import re

import pandas as pd
import pytest

import config
from bgos import docs

ROOT = config.ROOT


@pytest.fixture(scope="module")
def built(gen_result, marts):
    from bgos import experiments
    experiments.run_experiments(gen_result["root"])
    docs.run_docs(gen_result["root"])
    r = gen_result["root"]
    return dict(root=r, home=(r / "docs" / "index.html").read_text(), memo=(r / "docs" / "memo.html").read_text())


# ---- Stage 1: deployment truth --------------------------------------------------------------------------------------
def _fp(html):
    m = re.search(r'id="fingerprint">Data fingerprint ([0-9a-f]{10}) &middot; as of (\d{4}-\d\d-\d\d) &middot; seed (\d+) &middot; ([\d,]+) agencies', html)
    assert m, "fingerprint footer missing"
    return m.groups()


def test_both_committed_pages_carry_the_same_fingerprint_as_fresh_marts(built):
    home, memo = (ROOT / "docs" / "index.html").read_text(), (ROOT / "docs" / "memo.html").read_text()
    assert _fp(home) == _fp(memo)
    fresh = docs.data_fingerprint(built["root"])
    assert _fp(home)[0] == fresh and _fp(built["home"])[0] == fresh and _fp(built["memo"])[0] == fresh
    assert _fp(home)[1:] == (config.AS_OF.isoformat(), "42", "3,000")


def test_fingerprint_changes_when_any_mart_changes(built, tmp_path):
    import shutil
    root = tmp_path / "r"
    shutil.copytree(built["root"] / "data" / "marts", root / "data" / "marts")
    a = docs.data_fingerprint(root)
    f = root / "data" / "marts" / "topline.csv"
    f.write_text(f.read_text() + " ")
    assert docs.data_fingerprint(root) != a


def test_ci_fails_if_committed_docs_are_stale():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "git diff --exit-code" in ci and all(p in ci for p in ("docs", "STRATEGY_MEMO.md", "LOOM_SCRIPT.md", "DATA_DICTIONARY.md"))
    assert ci.index("make all") < ci.index("git diff --exit-code")


def test_verify_live_script_compares_both_pages():
    src = (ROOT / "scripts" / "verify_live.py").read_text()
    assert "index.html" in src and "memo.html" in src and "bust=" in src and "MISMATCH" in src


# ---- Stage 2: cross-platform determinism (B-22) -----------------------------------------------------------------------
def test_round_sig_rule():
    from bgos.rounding import SIG_DIGITS, round_df, round_obj, round_sig
    assert SIG_DIGITS == 10
    assert round_sig(2.2567328784098436e-05) == round_sig(2.256732878409844e-05) == 2.256732878e-05  # the reported last-digit drift
    assert round_sig(10079934.0) == 10079934.0 and round_sig(0.0) == 0.0 and round_sig(float("nan")) != round_sig(float("nan"))
    assert round_obj({"a": [1.23456789012345, {"b": 0.1 + 0.2}], "n": 3, "s": "x"}) == {"a": [1.23456789, {"b": 0.3}], "n": 3, "s": "x"}
    df = round_df(pd.DataFrame({"x": [1 / 3, 2.0], "n": [1, 2]}))
    assert df.x.iloc[0] == 0.3333333333 and df.n.tolist() == [1, 2]


def _digits_ok(x):
    from bgos.rounding import round_sig
    return round_sig(x) == x


def test_no_output_float_exceeds_the_precision_rule(built):
    import json
    root = built["root"]
    for f in sorted((root / "data" / "marts").glob("*.csv")) + [root / "outputs" / "ranked_accounts.csv"]:
        df = pd.read_csv(f)
        for c in df.select_dtypes("float").columns:
            bad = [v for v in df[c].dropna() if not _digits_ok(float(v))]
            assert not bad, (f.name, c, bad[:3])
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', built["home"], re.S).group(1))

    def walk(o):
        if isinstance(o, float):
            assert _digits_ok(o), o
        elif isinstance(o, dict):
            [walk(v) for v in o.values()]
        elif isinstance(o, list):
            [walk(v) for v in o]
    walk(data)


def test_statistics_keep_full_precision_in_memory():
    from bgos import experiments as ex
    z, p = ex.two_proportion_ztest(394, 1221, 504, 1245)
    assert p == pytest.approx(2.2567e-05, rel=1e-3)
    assert float(f"{p:.17g}") == p and len(repr(p).replace(".", "").replace("-", "").replace("e", "")) > 12  # not pre-rounded


def test_two_separate_processes_produce_byte_identical_pages_and_marts(tmp_path):
    import os
    import subprocess
    import sys
    outs = []
    for i in range(2):
        r = tmp_path / f"run{i}"
        env = {**os.environ, "BGOS_ROOT": str(r), "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}", "PYTHONHASHSEED": str(i)}
        subprocess.run([sys.executable, "-m", "bgos.cli", "all"], env=env, check=True, capture_output=True, cwd=ROOT, timeout=600)
        outs.append(r)
    files = ["docs/index.html", "docs/memo.html", "STRATEGY_MEMO.md", "LOOM_SCRIPT.md", "DATA_DICTIONARY.md"] + \
            [f"data/marts/{p.name}" for p in sorted((outs[0] / "data" / "marts").glob("*.csv"))]
    for f in files:
        assert (outs[0] / f).read_bytes() == (outs[1] / f).read_bytes(), f


def test_requirements_are_exactly_pinned_and_match_the_tested_environment():
    import importlib.metadata as md
    pins = [l.strip() for l in (ROOT / "requirements.txt").read_text().splitlines() if l.strip()]
    assert pins and all(re.fullmatch(r"[A-Za-z0-9_.-]+==\d[\w.]*", p) for p in pins), pins
    for p in pins:
        name, ver = p.split("==")
        assert md.version(name) == ver, f"{name}: installed {md.version(name)} != pinned {ver}"
    assert re.search(r"Tested with Python 3\.12", (ROOT / "README.md").read_text())
