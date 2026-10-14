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


# ---- Stage 3: Experiment C and A reporting (B-23, B-24) ---------------------------------------------------------------------
STATEMENT = "Experiment C cannot be powered at this size; INCONCLUSIVE is expected."


def test_mde_matches_statsmodels_and_power_definition():
    import math

    from statsmodels.stats.power import NormalIndPower

    from bgos import experiments as ex
    for p1, n in [(0.2245, 147), (0.30, 500), (0.10, 2000)]:
        m = ex.minimum_detectable_effect(p1, n)
        assert ex.achieved_power(p1, m["p2"], n, n) == pytest.approx(0.80, abs=1e-6)
        h = NormalIndPower().solve_power(effect_size=None, nobs1=n, alpha=0.05, power=0.80, ratio=1.0)
        p2_arcsine = math.sin(math.asin(math.sqrt(p1)) + h / 2) ** 2
        assert m["p2"] == pytest.approx(p2_arcsine, abs=0.006)
        assert m["abs"] == pytest.approx(m["p2"] - p1) and m["rel"] == pytest.approx(m["p2"] / p1 - 1)
    assert ex.minimum_detectable_effect(0.5, 5)["abs"] != ex.minimum_detectable_effect(0.5, 5)["abs"]  # NaN when unreachable


def test_c_headline_is_absolute_and_decision_unchanged(built):
    r = pd.read_csv(built["root"] / "data" / "marts" / "experiment_results.csv").set_index("experiment_id").loc["C"].copy()
    r["experiment_id"] = "C"
    assert r.decision == "INCONCLUSIVE" and r.abs_lift == pytest.approx(28 / 147 - 33 / 147)
    assert r.mde_abs_at_n > abs(r.abs_lift) and r.mde_abs_at_n > 0.10  # nothing near this size could have been detected
    from bgos import insights
    t = insights.takeaway_experiment(r)
    assert t.index("absolute lift") < t.index("INCONCLUSIVE is expected") and STATEMENT in t
    assert "relative lift" not in t.split("INCONCLUSIVE is expected")[0]


def test_c_card_shows_absolute_lift_first_in_streamlit(built, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("BGOS_ROOT", str(built["root"]))
    at = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=120).run()
    at.sidebar.radio[0].set_value("Experiments").run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert labels.count("Absolute lift (points)") == 1 and labels.count("Relative lift") == 2  # only C leads with absolute
    c_start = labels.index("Absolute lift (points)")
    assert labels[c_start - 1] == "Decision" and "Detectable lift at 80% power (points)" in labels
    assert any(STATEMENT in i.value for i in at.info)
    assert [m.value for m in at.metric if m.label == "Decision"] == ["SHIP", "ITERATE", "INCONCLUSIVE"]


def test_statement_present_in_site_readme_memo(built):
    for text in (built["home"], (ROOT / "README.md").read_text(), (built["root"] / "STRATEGY_MEMO.md").read_text()):
        assert "cannot be powered at this size" in text and "INCONCLUSIVE is expected" in text


def test_readme_c_numbers_match_marts(built):
    e = pd.read_csv(built["root"] / "data" / "marts" / "experiment_results.csv").set_index("experiment_id").loc["C"]
    readme = (ROOT / "README.md").read_text()
    assert f"{int(min(e.n_control, e.n_treatment))} agencies per arm against {int(e.n_required_per_arm)} required" in readme


def test_icp_split_matches_independent_pandas_and_wilson(built, clean_tables):
    from statsmodels.stats.proportion import proportion_confint
    ag, sb, asg = clean_tables["agencies"], clean_tables["submissions"], clean_tables["assignments"]
    a = asg[(asg.experiment_id == "A") & (asg.arm == "control")]
    a = a[a.assigned_at + pd.Timedelta(days=config.A_OUTCOME_DAYS) <= pd.Timestamp(config.AS_OF)]
    comp = sb[sb.is_complete == 1].groupby("agency_id").submitted_at.min().dt.normalize()
    first = a.agency_id.map(comp)
    won = (first >= a.assigned_at) & (first <= a.assigned_at + pd.Timedelta(days=config.A_OUTCOME_DAYS))
    icp = a.agency_id.map(ag.set_index("agency_id").is_icp)
    got = pd.read_csv(built["root"] / "data" / "marts" / "experiment_a_icp_split.csv").set_index("is_icp")
    for flag in (1, 0):
        n, x = int((icp == flag).sum()), int(won[icp == flag].sum())
        assert (got.loc[flag, "n"], got.loc[flag, "x"]) == (n, x)
        lo, hi = proportion_confint(x, n, alpha=0.05, method="wilson")
        assert got.loc[flag, "ci_low"] == pytest.approx(lo, abs=1e-8) and got.loc[flag, "ci_high"] == pytest.approx(hi, abs=1e-8)
    assert got.n.sum() == 1221  # equals Experiment A's control arm


def test_icp_split_is_labelled_observational_on_both_front_ends(built, monkeypatch):
    from streamlit.testing.v1 import AppTest
    assert "Observational panel (not an experiment)" in built["home"] and "icp_split" in built["home"]
    monkeypatch.setenv("BGOS_ROOT", str(built["root"]))
    at = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=120).run()
    at.sidebar.radio[0].set_value("Experiments").run()
    assert any("Observational panel (not an experiment)" in m.value for m in at.markdown)
    assert any("Observational, not an experiment" in m.value for m in at.markdown)


# ---- Stage 4: dataset-size disclosure and sensitivity (B-25) ----------------------------------------------------------------
import json  # noqa: E402


def _nsd():
    return json.loads((ROOT / "docs" / "n_sensitivity.json").read_text())


def test_n_sensitivity_file_structure_and_internal_consistency():
    d = _nsd()
    assert config.N_TRUE_AGENCIES == 3000  # the default N is not changed by the sensitivity sweep
    assert d["seeds"] == list(range(1, 21)) and sorted(d["summary"]) == ["1500", "2000", "3000"]
    for n, seeds in d["per_seed"].items():
        assert len(seeds) == 20
        for k in "ABC":
            counts = {}
            for v in seeds.values():
                counts[v[k]["decision"]] = counts.get(v[k]["decision"], 0) + 1
            assert counts == d["summary"][n][k]["decisions"], (n, k)
            assert d["summary"][n][k]["mean_achieved_per_arm"] == round(sum(v[k]["n_per_arm"] for v in seeds.values()) / 20)
    # more agencies can only help A reach the sample it needs
    a = {n: d["summary"][n]["A"]["mean_achieved_per_arm"] for n in d["summary"]}
    assert a["1500"] < a["2000"] < a["3000"]
    assert d["summary"]["1500"]["A"]["mean_required_per_arm"] > d["summary"]["1500"]["A"]["mean_achieved_per_arm"]  # underpowered at 1,500


def test_n_sensitivity_file_matches_a_rerun_of_two_seeds_at_1500():
    from bgos import sweep
    d = _nsd()
    for sd in (1, 2):
        assert d["per_seed"]["1500"][str(sd)] == sweep.run_one(sd, n_agencies=1500, extended=True)


def test_page_and_streamlit_show_the_same_counts_as_the_json(built, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from bgos import insights
    d = _nsd()
    rows = insights.n_sensitivity_rows(d)
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', built["home"], re.S).group(1))
    assert data["n_sens"] == rows and data["n_sens_seeds"] == 20 and data["n_sens_take"] == insights.takeaway_n_sensitivity(d)
    monkeypatch.setenv("BGOS_ROOT", str(built["root"]))
    at = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=120).run()
    at.sidebar.radio[0].set_value("Experiments").run()
    shown = [df.value for df in at.dataframe if "ship" in df.value.columns]
    assert len(shown) == 1 and shown[0][["agencies", "experiment", "ship", "iterate", "inconclusive"]].values.tolist() == \
        [[r["agencies"], r["experiment"], r["ship"], r["iterate"], r["inconclusive"]] for r in rows]


def test_disclosure_sentence_in_readme_memo_loom_with_json_counts(built):
    d = _nsd()
    x, y, z = (d["summary"][n]["A"]["decisions"].get("SHIP", 0) for n in ("1500", "2000", "3000"))
    readme = (ROOT / "README.md").read_text()
    assert f"At 1,500 agencies Experiment A ships in {x} of 20 simulated seeds; at 2,000, {y}; at 3,000, {z}." in readme
    memo, loom = (built["root"] / "STRATEGY_MEMO.md").read_text(), (built["root"] / "LOOM_SCRIPT.md").read_text()
    for t in (memo, loom):
        assert "enlarged from about 1,500" in t and "binding constraint on what" in t and "3,000" in t
        assert f"{x} of 20" in t and f"{z}" in t
    assert len(memo.split()) < 550


# ---- Stage 5: documentation honesty (B-26) ------------------------------------------------------------------------------------
CURRENT_DOCS = ["STRATEGY_MEMO.md", "LOOM_SCRIPT.md", "DATA_DICTIONARY.md", "DEPLOY.md", "docs/index.html", "docs/memo.html", "app/dashboard.py"]


def _current_texts():
    out = {f: (ROOT / f).read_text() for f in CURRENT_DOCS}
    for f in (ROOT / "src").rglob("*.py"):
        out[str(f.relative_to(ROOT))] = f.read_text()
    return out


def test_no_stale_figures_in_current_docs_or_code():
    allowed_1500 = ("enlarged from", "At 1,500", "at 1,500", "about 1,500", "N = 1,500", "1,500, 2,000")
    for name, text in _current_texts().items():
        for pat in (r"37\.5%", r"13\.9%", r"achieved power", r"Achieved power"):
            assert not re.search(pat, text), (name, pat)
        for line in text.splitlines():
            if "1,500" in line:
                assert any(a in line for a in allowed_1500), (name, line[:120])


def test_threshold_numbers_in_text_match_config():
    t = config.TIER_THRESHOLDS
    pat = re.compile(r"engagement\s*(?:>=|>|at least|of at least)\s*(\.?\d*\.\d+)", re.I)
    files = ["README.md", "STRATEGY_MEMO.md", "DATA_DICTIONARY.md", "src/bgos/scoring.py", "src/bgos/schema.py", "src/bgos/funnel.py", "config.py"]
    for f in files:
        for m in pat.finditer((ROOT / f).read_text()):
            assert float(m.group(1)) == t["tier1_engagement"], (f, m.group(0))
    doc = __import__("bgos.scoring", fromlist=["x"]).assign_tier.__doc__
    assert "config.TIER_THRESHOLDS" in doc and not re.search(r"[>=]=?\s*\.\d", doc)  # docstring refers to config, no copied numbers


def test_readme_has_audit_history_with_numbers_from_outputs(built):
    readme = (ROOT / "README.md").read_text()
    assert "## Audit history" in readme
    for needle in ("Circular scoring", "Immature cohorts", "sized for +30% but shipped at +20%", "Post-hoc", "planted effect was diluted", "stale deployed memo"):
        assert needle in readme, needle
    r = built["root"]
    h = pd.read_csv(r / "data" / "marts" / "tier_holdout.csv").set_index("tier")
    f = pd.read_csv(r / "data" / "marts" / "funnel_counts.csv").set_index("stage")
    e = pd.read_csv(r / "data" / "marts" / "experiment_results.csv").set_index("experiment_id")
    rate = lambda t: f"{h.loc[t, 'converted'] / h.loc[t, 'prospects'] * 100:.1f}%"
    for needle in (f"Tier 1 {rate('Tier 1')}, Tier 2 {rate('Tier 2')}, Tier 3 {rate('Tier 3')}",
                   f"{f.loc['bound', 'mature_cumulative_conversion'] * 100:.1f}% mature ({f.loc['bound', 'observed_cumulative_conversion'] * 100:.1f}% observed)",
                   f"{int(e.loc['A', 'n_required_per_arm'])} per arm required, {int(e.loc['A', 'n_control']):,} available",
                   f"{e.loc['A', 'power_at_mde'] * 100:.0f}%"):
        assert needle in readme, needle


def test_threshold_sensitivity_and_auc_claims_are_reproduced(clean_result, monkeypatch):
    from scipy.stats import rankdata

    from bgos import scoring
    ag, tc, sb = clean_result.agencies, clean_result.touches, clean_result.submissions
    rates = {}
    for th in (0.10, 0.20, 0.30):
        monkeypatch.setitem(config.TIER_THRESHOLDS, "tier1_engagement", th)
        h = scoring.holdout_conversion_by_tier(ag, tc, sb).set_index("tier")
        rates[th] = (h.loc["Tier 1", "converted"] / h.loc["Tier 1", "prospects"], h.loc["Tier 2", "converted"] / h.loc["Tier 2", "prospects"], int(h.loc["Tier 1", "prospects"]))
    for th, (t1, t2, n) in rates.items():
        assert 1.8 <= t1 / t2 <= 3.4 and n < 60, (th, t1, t2, n)  # always roughly twice Tier 2 (or more); small n, so wide intervals
    assert [round(rates[t][0] * 100) for t in (0.10, 0.20, 0.30)] == [23, 28, 35]
    monkeypatch.setitem(config.TIER_THRESHOLDS, "tier1_engagement", 0.20)
    cutoff = pd.Timestamp(config.AS_OF) - pd.Timedelta(days=config.HOLDOUT_DAYS)
    comp = sb[sb.is_complete == 1].assign(d=lambda d: pd.to_datetime(d.submitted_at).dt.normalize())
    pool = ag[(pd.to_datetime(ag.first_touch_date) <= cutoff) & ~ag.agency_id.isin(set(comp[comp.d <= cutoff].agency_id))]
    sc = scoring.score_agencies(pool, tc, sb, cutoff)
    y = sc.agency_id.isin(set(comp[(comp.d > cutoff) & (comp.d <= pd.Timestamp(config.AS_OF))].agency_id)).to_numpy()
    rk = rankdata(sc.score.to_numpy())
    auc = (rk[y].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (len(y) - y.sum()))
    assert round(auc, 2) == 0.84
    rep = (ROOT / "AUDIT_REPORT.md").read_text()
    assert "23% / 28% / 35%" in rep and "0.84" in rep and "generator plants that signal" in rep and "Second audit" in rep


def test_loom_tells_the_honest_story(built):
    loom = (built["root"] / "LOOM_SCRIPT.md").read_text()
    for needle in ("old enough to have converted", "out-of-sample", "lower confidence bound", "below the 20% hurdle", "B: ITERATE", "cannot be powered at this size",
                   "enlarged from about 1,500 to 3,000", "binding constraint", "validates plumbing, not real predictive power", "Engagement never counts submissions"):
        assert needle in loom, needle
    stamps = re.findall(r"\|\s*(\d+):(\d\d)-(\d+):(\d\d)\s*\|", loom)
    assert int(stamps[-1][2]) * 60 + int(stamps[-1][3]) <= 8 * 60


# ---- Stage 6: small items (B-27) -----------------------------------------------------------------------------------------------------
def _empty_db():
    from bgos import schema
    conn = schema.connect(":memory:")
    schema.create_schema(conn)
    return conn


def test_leading_partial_week_is_flagged_at_the_window_boundary():
    from bgos import metrics
    conn = _empty_db()
    for name in ("weekly_growth_review", "new_icp_agencies_weekly"):
        w = metrics.run_metric(name, conn, window_start="2025-10-01", as_of="2026-09-30")  # 2025-10-01 is a Wednesday
        assert w.week_start.iloc[0] == "2025-09-29" and w.is_partial_week.iloc[0] == 1
        assert w.is_partial_week.iloc[1] == 0 and w.is_partial_week.iloc[-1] == 1  # trailing week ends after the as-of date
        assert w.is_partial_week.iloc[1:-1].sum() == 0
        w2 = metrics.run_metric(name, conn, window_start="2025-09-29", as_of="2026-10-04")  # window starts on a Monday and ends on a Sunday
        assert w2.week_start.iloc[0] == "2025-09-29" and w2.is_partial_week.sum() == 0


def test_partial_weeks_are_excluded_from_the_north_star_baseline():
    from bgos import insights
    rows = [dict(week_start=f"2026-0{1 + i // 4}-{(i % 4) * 7 + 1:02d}", is_partial_week=0, qualified_submissions=10 + i) for i in range(12)]
    base = pd.DataFrame(rows)
    spiked = pd.concat([pd.DataFrame([dict(week_start="2025-09-29", is_partial_week=1, qualified_submissions=10_000)]), base], ignore_index=True)
    assert insights.takeaway_north_star(spiked) == insights.takeaway_north_star(base)


def test_header_strip_shows_all_seven_stages_with_mature_and_observed_bound(built):
    m = re.search(r'<div class="kpis" aria-label="Headline funnel numbers">(.*?)</div></div>(?=\s*<div id="view">)', built["home"], re.S)
    strip = m.group(1) if m else built["home"].split('aria-label="Headline funnel numbers">')[1].split('<div id="view">')[0]
    labels = re.findall(r"<div class='l'>([^<]+)</div>", strip)
    assert labels == ["Raw leads", "ICP-qualified", "Engaged", "First submissions", "Quoted", "Bound", "Repeat"]
    f = pd.read_csv(built["root"] / "data" / "marts" / "funnel_counts.csv").set_index("stage")
    assert f"{f.loc['bound', 'mature_cumulative_conversion'] * 100:.1f}% mature" in strip and f"{f.loc['bound', 'observed_cumulative_conversion'] * 100:.1f}% observed" in strip
    counts = re.findall(r"<div class='v'>([\d,]+)</div>", strip)
    assert counts == [f"{int(f.loc[s, 'agencies']):,}" for s in ("raw_lead", "icp_qualified", "engaged", "first_submission", "quoted", "bound", "repeat_submission")]


def test_both_pages_have_an_inline_favicon(built):
    for page in (built["home"], built["memo"], (ROOT / "docs" / "index.html").read_text(), (ROOT / "docs" / "memo.html").read_text()):
        assert re.search(r'<link rel="icon" href="data:image/svg\+xml,', page)


# ---- Stage 7 additions (a mutant survived: analyze_experiment could pass the wrong power to the MDE) ------------------------------
def test_reported_mde_matches_an_independent_bisection(built):
    import math

    from scipy import stats
    e = pd.read_csv(built["root"] / "data" / "marts" / "experiment_results.csv").set_index("experiment_id")

    def power(p1, p2, n, a=0.05):
        za = stats.norm.ppf(1 - a / 2)
        pb = (p1 + p2) / 2
        se0, se1 = math.sqrt(2 * pb * (1 - pb) / n), math.sqrt((p1 * (1 - p1) + p2 * (1 - p2)) / n)
        d = abs(p2 - p1)
        return stats.norm.sf((za * se0 - d) / se1) + stats.norm.cdf((-za * se0 - d) / se1)
    for k in "ABC":
        p1, n = e.loc[k, "rate_control"], int(min(e.loc[k, "n_control"], e.loc[k, "n_treatment"]))
        lo, hi = p1 + 1e-9, 0.999
        for _ in range(80):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if power(p1, mid, n) < 0.80 else (lo, mid)
        assert e.loc[k, "mde_abs_at_n"] == pytest.approx(lo - p1, abs=1e-6), k
        assert e.loc[k, "mde_rel_at_n"] == pytest.approx(lo / p1 - 1, abs=1e-6), k
