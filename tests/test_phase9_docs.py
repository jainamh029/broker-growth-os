import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import config
from bgos import docs, schema

ROOT = config.ROOT
README = (ROOT / "README.md").read_text()
OPENING = ("This project simulates the growth operating system for Hedge, an AI-native specialty insurance wholesaler. "
           "It models the broker funnel from lead identification through repeat submissions, identifies activation bottlenecks, "
           "scores agency fit, and provides an experiment framework for acquisition, onboarding, and reactivation.")


@pytest.fixture(scope="module")
def doc_root(gen_result, marts):
    from bgos import experiments
    experiments.run_experiments(gen_result["root"])
    docs.run_docs(gen_result["root"])
    return gen_result["root"]


# ---- data dictionary --------------------------------------------------------------------------------
def test_data_dictionary_documents_every_table_and_column(doc_root):
    text = (doc_root / "DATA_DICTIONARY.md").read_text()
    for table, meta in schema.TABLES.items():
        assert f"### `{table}`" in text
        section = text.split(f"### `{table}`")[1].split("\n### ")[0].split("\n## ")[0]
        for name, typ, desc, _c in meta["columns"]:
            row = [l for l in section.splitlines() if l.startswith(f"| `{name}` |")]
            assert row, f"{table}.{name} missing from dictionary"
            assert desc in row[0] and typ in row[0]
    assert "SYNTHETIC" in text.upper() or "Synthetic" in text


def test_committed_data_dictionary_is_current():
    assert (ROOT / "DATA_DICTIONARY.md").read_text() == docs.build_data_dictionary()


# ---- memo -------------------------------------------------------------------------------------------
def test_memo_word_count(doc_root):
    n = len((doc_root / "STRATEGY_MEMO.md").read_text().split())
    assert 400 <= n < 550, n


def test_memo_has_required_sections_and_disclaimer(doc_root):
    t = (doc_root / "STRATEGY_MEMO.md").read_text()
    for s in ["Growth thesis", "Funnel", "ICP", "highest-leverage gaps (synthetic baseline)", "90-day plan",
              "Days 1-30", "Days 31-60", "Days 61-90", "Assumptions to validate in the first 30 days", docs.DISCLAIMER]:
        assert s in t, s


def _numbers(text):
    return set(re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text))


def test_memo_numbers_match_generated_outputs(doc_root, clean_tables):
    memo = (doc_root / "STRATEGY_MEMO.md").read_text()
    facts = docs.memo_facts(doc_root)
    allowed = set(docs.STATIC_NUMBERS)
    for v in facts.values():
        allowed |= _numbers(v)
    stray = _numbers(memo) - allowed
    assert not stray, f"numbers in memo not traceable to outputs: {stray}"
    # independent spot checks against the clean tables and marts
    ag = clean_tables["agencies"]
    assert facts["raw"] == f"{len(ag):,}" and facts["raw"] in memo
    f = pd.read_csv(doc_root / "data" / "marts" / "funnel_counts.csv").set_index("stage").agencies
    assert facts["bound"] == f"{f['bound']:,}" and facts["first_sub"] == f"{f['first_submission']:,}"
    icp = (ag.is_icp == 1).sum()
    assert facts["icp"] == f"{icp:,}"
    ex = pd.read_csv(doc_root / "data" / "marts" / "experiment_results.csv").set_index("experiment_id")
    assert facts["a_dec"] == ex.loc["A", "decision"] and facts["a_dec"] in memo
    assert f"{ex.loc['A', 'rel_lift'] * 100:+.1f}%" in memo
    ranked = pd.read_csv(doc_root / "outputs" / "ranked_accounts.csv")
    assert facts["tier1"] == f"{(ranked.tier == 'Tier 1').sum():,}"


def test_committed_memo_matches_regenerated_numbers(doc_root):
    """The memo in the repo equals the one regenerated from a fresh seeded run (so it cannot drift from the outputs)."""
    committed = (ROOT / "STRATEGY_MEMO.md")
    assert committed.exists(), "run `make docs`"
    assert committed.read_text() == (doc_root / "STRATEGY_MEMO.md").read_text()
    assert (ROOT / "LOOM_SCRIPT.md").read_text() == (doc_root / "LOOM_SCRIPT.md").read_text()


# ---- README / honesty --------------------------------------------------------------------------------
def test_readme_opening_and_disclaimers():
    body = [l for l in README.splitlines() if l.strip()]
    assert body[1] == OPENING
    low = README.lower()
    for s in ["all data is synthetic", "simulated results that demonstrate the method", "known limits", "design decisions",
              "architecture", "screenshots", "quickstart", "assumptions to validate in the first 30 days"]:
        assert s in low, s


def test_every_doc_labels_synthetic_data(doc_root):
    for f in ["README.md", "STRATEGY_MEMO.md", "LOOM_SCRIPT.md", "DEPLOY.md", "DATA_DICTIONARY.md"]:
        assert "synthetic" in (doc_root / f if (doc_root / f).exists() else ROOT / f).read_text().lower(), f
    assert "SIMULATED" in (doc_root / "outputs" / "experiment_results.md").read_text()


def _slug(h):
    h = re.sub(r"[`*_]", "", h.strip().lower())
    h = re.sub(r"[^\w\s-]", "", h)
    return re.sub(r"\s", "-", h)


def test_internal_links_resolve(doc_root):
    link = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)|!\[[^\]]*\]\(([^)\s]+)\)")
    for md in sorted(ROOT.glob("*.md")) + sorted((ROOT / "docs").rglob("*.md")):
        text = md.read_text()
        for m in link.finditer(text):
            target = m.group(1) or m.group(2)
            if re.match(r"^(https?:|mailto:)", target):
                continue
            path, _, anchor = target.partition("#")
            base = md.parent
            dest = (base / path) if path else md
            if not dest.exists():  # generated artefacts (data/, outputs/) exist after `make all`
                dest = doc_root / dest.relative_to(ROOT) if str(dest).startswith(str(ROOT)) else dest
            assert dest.exists(), f"{md.name}: broken link {target}"
            if anchor and dest.suffix == ".md":
                slugs = {_slug(l.lstrip("# ")) for l in dest.read_text().splitlines() if l.startswith("#")}
                assert anchor in slugs, f"{md.name}: missing anchor {target}"


def test_readme_quickstart_commands_succeed(tmp_path):
    """Execute the quickstart `make` commands (except setup/dashboard/test) in a temp output root."""
    section = README.split("## Quickstart")[1].split("\n## ")[0]
    block = re.search(r"```bash\n(.*?)```", section, re.S).group(1)
    cmds = [l.split("#")[0].strip() for l in block.splitlines() if l.strip().startswith("make ")]
    assert cmds == ["make setup", "make all", "make dashboard", "make test"]
    env = {**os.environ, "BGOS_ROOT": str(tmp_path), "PY": sys.executable}
    ran = []
    for c in cmds:
        target = c.split()[1]
        if target in ("setup", "dashboard", "test"):
            continue
        r = subprocess.run(["make", "-C", str(ROOT), target], env=env, capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, (c, r.stdout[-800:], r.stderr[-800:])
        ran.append(target)
    assert ran == ["all"]
    for f in ["outputs/ranked_accounts.csv", "outputs/data_quality_report.md", "outputs/ai_demo.md", "outputs/experiment_results.md",
              "data/marts/topline.csv", "STRATEGY_MEMO.md", "DATA_DICTIONARY.md"]:
        assert (tmp_path / f).exists(), f


def test_make_all_is_deterministic(tmp_path, doc_root):
    env = {**os.environ, "BGOS_ROOT": str(tmp_path), "PY": sys.executable}
    r = subprocess.run(["make", "-C", str(ROOT), "all"], env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-800:]
    for f in ["data/raw/agencies.csv", "data/clean/submissions.csv", "outputs/ranked_accounts.csv",
              "data/marts/experiment_results.csv", "STRATEGY_MEMO.md"]:
        assert (tmp_path / f).read_bytes() == (doc_root / f).read_bytes(), f


# ---- loom / deploy -----------------------------------------------------------------------------------
def test_loom_script_timeline_and_self_flags(doc_root):
    t = (doc_root / "LOOM_SCRIPT.md").read_text()
    stamps = re.findall(r"\|\s*(\d+):(\d\d)-(\d+):(\d\d)\s*\|", t)
    assert len(stamps) >= 6
    secs = [(int(a) * 60 + int(b), int(c) * 60 + int(d)) for a, b, c, d in stamps]
    assert secs[0][0] == 0 and all(e > s for s, e in secs) and all(secs[i][1] <= secs[i + 1][0] for i in range(len(secs) - 1))
    assert 5 * 60 <= secs[-1][1] <= 8 * 60
    assert "Do these yourself" in t and "first 30 days" in t.lower() and "Assumptions" in t
    assert "Synthetic data. Demonstrates the method" in t


def test_deploy_doc_has_exact_steps():
    t = (ROOT / "DEPLOY.md").read_text()
    for s in ["git remote add origin", "git push -u origin main", "share.streamlit.io", "app/dashboard.py", "Python 3.12", "Do not attempt deployment"]:
        assert s.lower() in t.lower(), s
