"""Every SQL metric is cross-checked against an independent pandas computation on the same clean data."""
import re

import numpy as np
import pandas as pd
import pytest

import config
from bgos import funnel, metrics

AS_OF = pd.Timestamp(config.AS_OF)
AS_OF_END = AS_OF + pd.Timedelta(hours=23, minutes=59, seconds=59)
ENG = funnel.ENGAGEMENT_TOUCH_TYPES


@pytest.fixture(scope="module")
def nest(clean_tables):
    """Independent nested-funnel computation (no stage_events, no SQL)."""
    ag, tc, sb = (clean_tables[k] for k in ("agencies", "touches", "submissions"))
    d = ag.set_index("agency_id").copy()
    lines_ok = d.commercial_lines.fillna("").str.len() > 0
    expo = d.es_appetite.isin(["high", "medium"]) | (d.specialty_focus.map(config.SPECIALTY_WEIGHTS) >= 0.7)
    d["icp"] = lines_ok & expo & (d.size_producers >= config.ICP_MIN_PRODUCERS)
    comp = sb[sb.is_complete == 1]
    first_sub = comp.groupby("agency_id").submitted_at.min()
    first_eng_touch = tc[tc.touch_type.isin(ENG)].groupby("agency_id").touched_at.min()
    d["first_sub"] = first_sub
    d["eng_at"] = pd.concat([first_eng_touch, first_sub], axis=1).min(axis=1)
    d["fs_at"] = d["first_sub"]
    d["has_quote"] = comp[comp.quoted_at.notna()].groupby("agency_id").size().reindex(d.index).fillna(0) > 0
    first_bind = comp[comp.bound_at.notna()].groupby("agency_id").bound_at.min()
    d["first_bind"] = first_bind
    d["s2"] = d.icp & d.eng_at.notna()
    d["s3"] = d.s2 & d.fs_at.notna()
    d["s4"] = d.s3 & d.has_quote
    d["s5"] = d.s4 & d.first_bind.notna()
    rep = comp.merge(first_bind.rename("fb"), left_on="agency_id", right_index=True)
    rep = rep[(rep.submitted_at > rep.fb) & (rep.submitted_at <= rep.fb + pd.Timedelta(days=config.REPEAT_WINDOW_DAYS))]
    d["has_rep"] = d.index.isin(rep.agency_id)
    d["s6"] = d.s5 & d.has_rep
    return d


def test_registry_and_sql_files_match_both_ways():
    files = {p.name for p in config.get_paths().sql.glob("*.sql")}
    assert files == {m.sql_file for m in metrics.REGISTRY.values()}
    src = (config.ROOT / "src" / "bgos" / "metrics.py").read_text()
    for f in files:
        assert f in src
    for f in files:  # no hard-coded dates in SQL logic: dates arrive as parameters
        body = "\n".join(l for l in (config.get_paths().sql / f).read_text().splitlines() if not l.strip().startswith("--"))
        assert not re.search(r"20\d\d-\d\d-\d\d", body), f


def test_funnel_counts_match_pandas_and_reconcile(marts, nest, clean_tables):
    f = marts["funnel_counts"].set_index("stage")["agencies"]
    assert f["raw_lead"] == len(clean_tables["agencies"])
    assert f["icp_qualified"] == nest.icp.sum()
    assert f["engaged"] == nest.s2.sum()
    assert f["first_submission"] == nest.s3.sum()
    assert f["quoted"] == nest.s4.sum()
    assert f["bound"] == nest.s5.sum()
    assert f["repeat_submission"] == nest.s6.sum()
    assert f.is_monotonic_decreasing
    # out-of-funnel reconciliation: agencies with a complete submission that never passed ICP/engaged gates
    comp_agencies = set(clean_tables["submissions"].query("is_complete == 1").agency_id)
    out_of_funnel = len(comp_agencies) - f["first_submission"]
    assert out_of_funnel == len(comp_agencies - set(nest.index[nest.s3]))
    assert out_of_funnel >= 0
    cc = marts["funnel_counts"].set_index("stage")["cumulative_conversion"]
    assert cc["raw_lead"] == 1.0 and cc["bound"] == pytest.approx(f["bound"] / f["raw_lead"], abs=1e-4)


def test_new_icp_weekly(marts, nest):
    w = marts["new_icp_agencies_weekly"]
    assert w.new_icp_agencies.sum() == nest.icp.sum()
    ft = pd.to_datetime(nest[nest.icp].first_touch_date)
    expect = ft.dt.to_period("W-SUN").dt.start_time.value_counts()
    got = w.set_index(pd.to_datetime(w.week_start)).new_icp_agencies
    for wk, n in expect.items():
        assert got[wk] == n
    assert pd.to_datetime(w.week_start).is_monotonic_increasing and (w.week_start == w.week_start.drop_duplicates()).all()


def test_source_quality(marts, nest):
    sq = marts["source_quality"].set_index("lead_source")
    g = nest.groupby("lead_source")
    for src, row in sq.iterrows():
        sub = nest[nest.lead_source == src]
        assert row.leads == len(sub)
        assert row.bound_agencies == sub.s5.sum()
        assert row.repeat_agencies == sub.s6.sum()
        assert row.first_submissions == sub.s3.sum()
        if len(sub) >= config.MIN_N:
            assert row.bind_rate_per_lead == pytest.approx(sub.s5.sum() / len(sub), abs=1e-4)
            assert row.suppressed == 0
        else:
            assert np.isnan(row.bind_rate_per_lead) and row.suppressed == 1
    big = sq.bind_rate_per_lead.drop(["podcast_sponsor", "state_assoc_booth", "wholesaler_alumni"])
    assert big.idxmin() == "linkedin"  # audit B-10: referral-is-best is verified at large n (test_audit_regressions.py)
    assert big["referral"] >= big.drop("referral").median()


def test_time_to_quote(marts, clean_tables):
    sb = clean_tables["submissions"]
    q = sb[(sb.is_complete == 1) & sb.quoted_at.notna()].copy()
    # first complete submission regardless of quote:
    first_any = sb[sb.is_complete == 1].groupby("agency_id").submitted_at.min()
    q["is_first"] = q.apply(lambda r: r.submitted_at == first_any[r.agency_id], axis=1)
    t = marts["time_to_quote"].set_index(["scope", "dimension", "value"])
    assert t.loc[("all_submissions", "overall", "all"), "median_hours"] == pytest.approx(q.quote_turnaround_hours.median(), abs=0.01)
    for line, g in q.groupby("line_of_business"):
        assert t.loc[("all_submissions", "line_of_business", line), "median_hours"] == pytest.approx(g.quote_turnaround_hours.median(), abs=0.01)
        assert t.loc[("all_submissions", "line_of_business", line), "n"] == len(g)
    for cx, g in q.groupby("risk_complexity"):
        assert t.loc[("all_submissions", "risk_complexity", cx), "median_hours"] == pytest.approx(g.quote_turnaround_hours.median(), abs=0.01)
    f = q[q.is_first]
    assert t.loc[("first_submissions", "overall", "all"), "median_hours"] == pytest.approx(f.quote_turnaround_hours.median(), abs=0.01)
    meds = [t.loc[("all_submissions", "risk_complexity", c), "median_hours"] for c in ("low", "medium", "high")]
    assert meds[0] < meds[1] < meds[2]  # complexity slows quotes


def test_dormant_list(marts, clean_tables, scored):
    sb = clean_tables["submissions"]
    comp = sb[sb.is_complete == 1]
    last = comp.groupby("agency_id").submitted_at.max().dt.normalize()
    dormant = last[(AS_OF - last).dt.days >= config.DORMANCY_DAYS].index
    prior = comp[comp.bound_at.notna()].groupby("agency_id").premium.sum().reindex(dormant).fillna(0)
    score = scored.set_index("agency_id").score.reindex(dormant)
    exp = pd.DataFrame({"prem": prior, "score": score}).reset_index().rename(columns={"index": "agency_id"})
    exp = exp.sort_values(["prem", "score", "agency_id"], ascending=[False, False, True])
    got = marts["dormant_reactivation"]
    assert got.agency_id.tolist() == exp.agency_id.tolist()
    assert (got.days_dormant >= config.DORMANCY_DAYS).all()
    assert got.prior_bound_premium.is_monotonic_decreasing


def test_pipeline_projection(marts, nest):
    pp = marts["pipeline_projection"].set_index("segment")
    d = nest.copy()
    d["top"] = np.select([d.s5, d.s4, d.s3, d.s2, d.icp], [6, 5, 4, 3, 2], default=1)
    reached = {k: d[col].groupby(d.specialty_focus).sum() for k, col in {2: "icp", 3: "s2", 4: "s3", 5: "s4", 6: "s5"}.items()}
    overall = {k: v.sum() for k, v in reached.items()}
    age = (AS_OF - pd.to_datetime(d.last_activity_date)).dt.days
    open_ = d[(d.top.between(2, 5)) & (age <= config.PIPELINE_OPEN_DAYS)]
    for seg, row in pp.iterrows():
        exp_bound = 0.0
        for k, openk in ((2, "open_icp"), (3, "open_engaged"), (4, "open_first_submission"), (5, "open_quoted")):
            n_open = ((open_.specialty_focus == seg) & (open_.top == k)).sum()
            assert row[openk] == n_open, (seg, openk)
            r_k = reached[k][seg] if reached[k][seg] >= config.MIN_N else overall[k]
            r_6 = reached[6][seg] if reached[k][seg] >= config.MIN_N else overall[6]
            exp_bound += n_open * r_6 / r_k
        assert row.expected_new_bound_agencies == pytest.approx(exp_bound, abs=0.02), seg
    total = pp.expected_new_bound_agencies.sum()
    assert total > 0 and (pp.projected_commission >= 0).all()


def test_cohort_retention(marts, nest, clean_tables):
    sb = clean_tables["submissions"]
    comp = sb[sb.is_complete == 1]
    fs = nest[nest.s3]
    rows = []
    for aid, r in fs.iterrows():
        later = comp[(comp.agency_id == aid) & (comp.submitted_at > r.fs_at)].submitted_at
        gap = (later.min() - r.fs_at).total_seconds() / 86400 if len(later) else np.inf
        age = (AS_OF_END - r.fs_at).total_seconds() / 86400
        rows.append((aid, r.fs_at.strftime("%Y-%m"), age, gap))
    pa = pd.DataFrame(rows, columns=["agency_id", "cohort", "age", "gap"])
    allrow = marts["cohort_retention"].set_index("cohort").loc["ALL"]
    assert allrow.agencies == len(pa)
    for n in config.COHORT_WINDOWS:
        mature = pa[pa.age >= n]
        assert allrow[f"mature_{n}"] == len(mature)
        assert allrow[f"repeat_{n}"] == (mature.gap <= n).sum()
        assert allrow[f"retention_{n}"] == pytest.approx((mature.gap <= n).mean(), abs=1e-4)
    # retention grows with window length (more time to come back)
    assert allrow.retention_30 <= allrow.retention_60 <= allrow.retention_90
    m = marts["cohort_retention"].set_index("cohort")
    assert m.drop("ALL").agencies.sum() == len(pa)


def test_activation_rate(marts, nest):
    e = nest[nest.s2].copy()
    age = (AS_OF_END - e.eng_at).dt.total_seconds() / 86400
    gap = (e.fs_at - e.eng_at).dt.total_seconds() / 86400
    mature = age >= config.ACTIVATION_DAYS
    act = mature & (gap <= config.ACTIVATION_DAYS)
    row = marts["activation_rate"].set_index("cohort").loc["ALL"]
    assert row.engaged_agencies == len(e) and row.mature_agencies == mature.sum() and row.activated_agencies == act.sum()
    assert row.activation_rate == pytest.approx(act.sum() / mature.sum(), abs=1e-4)


def test_owner_performance(marts, nest):
    op = marts["owner_performance"].set_index("owner")
    for owner, g in nest.groupby("owner"):
        r = op.loc[owner]
        assert r.agencies == len(g) and r.icp_agencies == g.icp.sum() and r.engaged_agencies == g.s2.sum()
        assert r.first_submissions == g.s3.sum() and r.bound_agencies == g.s5.sum()
        assert r.activation_rate == pytest.approx(g.s3.sum() / g.s2.sum(), abs=1e-4)
    assert op.agencies.sum() == len(nest)


def test_weekly_growth_review(marts, clean_tables, nest):
    sb = clean_tables["submissions"]
    comp = sb[sb.is_complete == 1].sort_values(["agency_id", "submitted_at", "submission_id"]).copy()
    comp["prev"] = comp.groupby("agency_id").submitted_at.shift()
    icp = nest.icp.reindex(comp.agency_id).to_numpy()
    gap = (comp.submitted_at - comp.prev).dt.total_seconds() / 86400
    comp["qual"] = icp & (comp.prev.isna() | (gap < config.DORMANCY_DAYS))
    comp["react"] = icp & comp.prev.notna() & (gap >= config.DORMANCY_DAYS)
    comp["wk"] = comp.submitted_at.dt.to_period("W-SUN").dt.start_time
    exp_q = comp.groupby("wk").qual.sum()
    exp_r = comp.groupby("wk").react.sum()
    w = marts["weekly_growth_review"]
    w = w.set_index(pd.to_datetime(w.week_start))
    assert w.qualified_submissions.sum() == comp.qual.sum()
    for wk, n in exp_q.items():
        assert w.loc[wk, "qualified_submissions"] == n
        assert w.loc[wk, "reactivated_submissions"] == exp_r[wk]
    assert w.is_partial_week.iloc[-1] == 1 and w.is_partial_week.iloc[:-1].sum() == 0
    allsub = sb.submitted_at.dt.to_period("W-SUN").dt.start_time.value_counts()
    for wk, n in allsub.items():
        assert w.loc[wk, "all_submissions"] == n
    new_act = nest[nest.s3].fs_at.dt.to_period("W-SUN").dt.start_time.value_counts()
    for wk, n in new_act.items():
        assert w.loc[wk, "new_activations"] == n


def test_topline(marts, nest, clean_tables):
    t = marts["topline"].iloc[0]
    assert t.agencies == len(nest) and t.icp_agencies == nest.icp.sum() and t.engaged_agencies == nest.s2.sum()
    assert t.activated_agencies == nest.s3.sum() and t.bound_agencies == nest.s5.sum()
    sb = clean_tables["submissions"]
    c = sb[(sb.is_complete == 1)]
    last7 = c[(c.submitted_at.dt.normalize() > AS_OF - pd.Timedelta(days=7)) & (c.submitted_at.dt.normalize() <= AS_OF)]
    assert t.complete_submissions_7d == len(last7)
    ftd = pd.to_datetime(nest[nest.icp].first_touch_date)
    assert t.new_icp_7d == ((ftd > AS_OF - pd.Timedelta(days=7)) & (ftd <= AS_OF)).sum()
    b = sb[sb.bound_at.notna() & ((AS_OF - sb.bound_at.dt.normalize()).dt.days < 90)]
    assert t.commission_last_90d == pytest.approx(b.commission.sum(), abs=0.01)


def test_experiment_outcomes(marts, clean_tables):
    eo = marts["experiment_outcomes"]
    sb = clean_tables["submissions"]
    comp = sb[sb.is_complete == 1]
    a = eo[eo.experiment_id == "A"]
    first = comp.groupby("agency_id").submitted_at.min().dt.normalize()
    asg = pd.to_datetime(a.assigned_at)
    gap = (a.agency_id.map(first) - asg).dt.days
    exp = (gap >= 0) & (gap <= config.A_OUTCOME_DAYS)
    assert (a.outcome.to_numpy() == exp.to_numpy().astype(int)).all()
    c = eo[eo.experiment_id == "C"]
    t0 = pd.Timestamp(config.REACTIVATION_T0)
    after = comp[(comp.submitted_at.dt.normalize() > t0) & (comp.submitted_at.dt.normalize() <= t0 + pd.Timedelta(days=config.C_OUTCOME_DAYS))]
    assert set(c[c.outcome == 1].agency_id) == set(after.agency_id) & set(c.agency_id)
    assert set(eo.arm) == {"control", "treatment"}


def test_no_nan_or_inf_outside_suppressed_columns(marts):
    for name, m in metrics.REGISTRY.items():
        df = marts[name]
        assert not np.isinf(df.select_dtypes("number").to_numpy()).any(), name
        bad = [c for c in df.columns if df[c].isna().any() and c not in m.nullable_cols]
        assert not bad, (name, bad)


def test_min_n_suppression_works(gen_result, clean_result, scored):
    conn = metrics.connect(gen_result["root"])
    hi = metrics.run_metric("source_quality", conn, min_n=10_000)
    lo = metrics.run_metric("source_quality", conn, min_n=1)
    assert hi.bind_rate_per_lead.isna().all() and (hi.suppressed == 1).all()
    assert lo.bind_rate_per_lead.notna().all() and (lo.suppressed == 0).all()
    t_hi = metrics.run_metric("time_to_quote", conn, min_n=10_000)
    assert t_hi.median_hours.isna().all()
    conn.close()


def test_marts_written_to_disk(gen_result, marts):
    for name in metrics.REGISTRY:
        on_disk = pd.read_csv(gen_result["root"] / "data" / "marts" / f"{name}.csv")
        assert len(on_disk) == len(marts[name])
