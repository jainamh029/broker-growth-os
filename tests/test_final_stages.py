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
