"""Broker Growth OS dashboard (Streamlit). Reads ONLY from data/marts (written by the SQL metrics layer).

All data is SYNTHETIC. The banner below must stay on every view.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "src"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import config  # noqa: E402
from bgos import funnel, insights as ins, metrics  # noqa: E402

BANNER = "Synthetic data. Demonstrates the method, not Hedge's actual performance."
VIEWS = ["Monday Morning", "Weekly Growth Review", "Source Quality", "Time-to-Quote", "Activation and Cohorts",
         "Dormancy and Reactivation", "Pipeline and Revenue Projection", "Ranked Accounts", "Experiments"]
INK, ACCENT, MUTED, ALERT = "#1b2a41", "#1d4e89", "#9aa8b5", "#b5483a"

st.set_page_config(page_title="Broker Growth OS", layout="wide")
st.markdown(
    """<style>
    .banner{background:#fff4d6;border:1px solid #e6c667;color:#5b4500;padding:.55rem .9rem;border-radius:6px;font-size:.92rem;margin-bottom:.8rem}
    .takeaway{border-left:3px solid #1d4e89;padding:.25rem .8rem;margin:.2rem 0 1.1rem 0;color:#1b2a41;font-size:.98rem}
    .block-container{padding-top:1.6rem;max-width:1200px}
    </style>""", unsafe_allow_html=True)
st.markdown(f"<div class='banner'><b>{BANNER}</b></div>", unsafe_allow_html=True)


def mart(name: str) -> pd.DataFrame:
    path = config.get_paths().marts / f"{name}.csv"
    if not path.exists():
        st.error(f"Missing data mart `{name}`. Run `make all` first (synthetic data is generated locally).")
        st.stop()
    return pd.read_csv(path)


def takeaway(text: str) -> None:
    st.markdown(f"<div class='takeaway'><b>Takeaway.</b> {text}</div>", unsafe_allow_html=True)


def style(fig: go.Figure, h: int = 340) -> go.Figure:
    fig.update_layout(template="plotly_white", height=h, margin=dict(l=10, r=10, t=30, b=10), font=dict(color=INK, size=13),
                      legend=dict(orientation="h", y=-0.2), colorway=[ACCENT, MUTED, ALERT, "#5b8e7d"])
    return fig


def stage_name(k: str) -> str:
    return funnel.STAGE_BY_KEY[k].name


def delta(a, b):
    return f"{int(a) - int(b):+d} vs prior 7d"


# ------------------------------------------------------------------------------------------------
def view_monday():
    t = mart("topline").iloc[0]
    f = mart("funnel_counts")
    st.subheader("Monday Morning")
    c = st.columns(5)
    c[0].metric("New ICP agencies (7d)", f"{int(t.new_icp_7d):,}", delta(t.new_icp_7d, t.new_icp_prev_7d))
    c[1].metric("New activations (7d)", f"{int(t.new_activations_7d):,}")
    c[2].metric("Complete submissions (7d)", f"{int(t.complete_submissions_7d):,}", delta(t.complete_submissions_7d, t.complete_submissions_prev_7d))
    c[3].metric("Active agencies (60d)", f"{int(t.active_agencies_60d):,}")
    c[4].metric("Dormant agencies", f"{int(t.dormant_agencies):,}")
    c = st.columns(3)
    c[0].metric("ICP-qualified agencies", f"{int(t.icp_agencies):,}")
    c[1].metric("Commission, last 90d", ins.money(t.commission_last_90d))
    c[2].metric("Bound premium, last 90d", ins.money(t.bound_premium_last_90d))
    ff = f.sort_values("stage_order")
    fig = go.Figure(go.Bar(y=[stage_name(s) for s in ff.stage], x=ff.agencies, orientation="h", marker_color=ACCENT,
                           text=[f"{int(a):,}" + ("" if pd.isna(s) else f"  ({s:.0%} of prior)") for a, s in zip(ff.agencies, ff.step_conversion)],
                           textposition="auto"))
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(style(fig, 360), use_container_width=True)
    takeaway(ins.takeaway_funnel(f))
    r = mart("ranked_accounts")
    new_biz = r[r.tier.isin(["Tier 1", "Tier 2"]) & r.action.isin(["outbound", "onboarding"])]
    top = new_biz.sort_values(["tier", "score"], ascending=[True, False]).head(8)[["name", "score", "tier", "next_action", "owner", "channel", "reason"]]
    st.markdown("**Work first this week: highest-fit accounts that are not yet submitting**")
    st.dataframe(top, hide_index=True, use_container_width=True)


def view_weekly():
    w = mart("weekly_growth_review")
    st.subheader("Weekly Growth Review")
    st.caption("North star: qualified submissions per week = complete submissions from ICP agencies that are new or active (previous submission < 60 days earlier).")
    full = w[w.is_partial_week == 0].copy()
    full["wk"] = pd.to_datetime(full.week_start)
    full["ma4"] = full.qualified_submissions.rolling(4).mean()
    fig = go.Figure()
    fig.add_bar(x=full.wk, y=full.qualified_submissions, name="Qualified submissions", marker_color=ACCENT)
    fig.add_scatter(x=full.wk, y=full.ma4, name="4-week average", line=dict(color=ALERT, width=2))
    st.plotly_chart(style(fig), use_container_width=True)
    takeaway(ins.takeaway_north_star(w))
    st.markdown("**Inputs** (what we control)")
    fig = go.Figure()
    for col, nm, colr in (("new_icp_agencies", "New ICP agencies", ACCENT), ("new_engaged_agencies", "Newly engaged", MUTED), ("new_activations", "Activations (first complete submission)", ALERT)):
        fig.add_scatter(x=full.wk, y=full[col].rolling(4).mean(), name=nm + " (4-wk avg)", line=dict(color=colr))
    st.plotly_chart(style(fig, 300), use_container_width=True)
    st.markdown("**Diagnostics** (why the north star moved)")
    fig = go.Figure()
    for col, nm, colr in (("completeness_rate", "Submission completeness", ACCENT), ("quote_rate", "Quote rate", MUTED), ("bind_rate_of_quoted", "Bind rate of quoted", ALERT)):
        fig.add_scatter(x=full.wk, y=full[col], name=nm, line=dict(color=colr), connectgaps=False)
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(style(fig, 300), use_container_width=True)
    last = full.dropna(subset=["completeness_rate"]).tail(4)
    takeaway(f"Over the last 4 weeks with data, {ins.pct(last.completeness_rate.mean(), 0)} of submissions arrived complete; "
             f"{int(full.tail(4).reactivated_submissions.sum())} submissions came from reactivated (previously dormant) agencies and are excluded from the north star.")
    st.dataframe(full.tail(8)[["week_start", "qualified_submissions", "new_icp_agencies", "new_engaged_agencies", "new_activations", "completeness_rate", "quote_rate", "bind_rate_of_quoted"]],
                 hide_index=True, use_container_width=True)


def view_sources():
    sq = mart("source_quality")
    st.subheader("Source Quality")
    st.caption("Judged by downstream bind and repeat, not lead count. Sources with fewer than %d agencies are suppressed." % config.MIN_N)
    ok = sq[sq.suppressed == 0].sort_values("bind_rate_per_lead", ascending=False)
    c1, c2 = st.columns(2)
    fig = go.Figure(go.Bar(x=ok.lead_source, y=ok.bind_rate_per_lead, marker_color=ACCENT, text=[ins.pct(v) for v in ok.bind_rate_per_lead], textposition="outside"))
    fig.update_yaxes(tickformat=".0%", title="Bound agencies per lead")
    c1.plotly_chart(style(fig), use_container_width=True)
    fig = go.Figure(go.Bar(x=ok.lead_source, y=ok.leads, marker_color=MUTED, text=ok.leads, textposition="outside"))
    fig.update_yaxes(title="Leads (volume)")
    c2.plotly_chart(style(fig), use_container_width=True)
    takeaway(ins.takeaway_sources(sq))
    show = sq[["lead_source", "leads", "first_submission_rate", "bind_rate_per_lead", "repeat_rate_of_bound", "commission_per_lead", "suppressed"]]
    st.dataframe(show, hide_index=True, use_container_width=True)


def view_ttq():
    t = mart("time_to_quote")
    st.subheader("Time-to-Quote")
    scope = st.radio("Scope", ["all_submissions", "first_submissions"], horizontal=True,
                     format_func=lambda s: "All quoted submissions" if s == "all_submissions" else "Each agency's first submission")
    d = t[t.scope == scope]
    c1, c2 = st.columns(2)
    cx = d[d.dimension == "risk_complexity"].set_index("value").reindex(["low", "medium", "high"]).dropna(subset=["median_hours"])
    fig = go.Figure(go.Bar(x=cx.index, y=cx.median_hours, marker_color=ACCENT, text=[f"{v:.0f}h" for v in cx.median_hours], textposition="outside"))
    fig.update_yaxes(title="Median hours to quote")
    c1.plotly_chart(style(fig), use_container_width=True)
    lob = d[d.dimension == "line_of_business"].sort_values("median_hours")
    if len(lob):
        fig = go.Figure(go.Bar(y=lob.value, x=lob.median_hours, orientation="h", marker_color=MUTED))
        fig.update_xaxes(title="Median hours to quote")
        c2.plotly_chart(style(fig), use_container_width=True)
    else:
        c2.info("Line-of-business split is shown for the all-submissions scope.")
    takeaway(ins.takeaway_ttq(t))
    st.dataframe(d[["dimension", "value", "n", "median_hours"]], hide_index=True, use_container_width=True)


def view_activation():
    act, coh = mart("activation_rate"), mart("cohort_retention")
    st.subheader("Activation and Cohorts")
    m = act[act.cohort != "ALL"]
    fig = go.Figure(go.Bar(x=m.cohort, y=m.activation_rate, marker_color=ACCENT, text=[ins.pct(v, 0) for v in m.activation_rate], textposition="outside"))
    fig.update_yaxes(tickformat=".0%", title="Engaged agencies submitting within 14 days")
    st.plotly_chart(style(fig), use_container_width=True)
    c = coh[coh.cohort != "ALL"].set_index("cohort")[["retention_30", "retention_60", "retention_90"]]
    heat = go.Figure(go.Heatmap(z=c.values, x=["30 days", "60 days", "90 days"], y=c.index, colorscale=[[0, "#eef3f8"], [1, ACCENT]],
                                text=[[ins.pct(v, 0) for v in row] for row in c.values], texttemplate="%{text}", zmin=0, zmax=1, showscale=False))
    heat.update_yaxes(autorange="reversed", title="First-submission month")
    st.plotly_chart(style(heat, 420), use_container_width=True)
    takeaway(ins.takeaway_activation(act, coh))
    st.caption("Only mature agencies (a full window observed before the as-of date) are in each denominator; blank cells are suppressed or immature.")


def view_dormant():
    d = mart("dormant_reactivation")
    st.subheader("Dormancy and Reactivation")
    c = st.columns(3)
    c[0].metric("Dormant agencies", f"{len(d):,}")
    c[1].metric("Prior bound premium", ins.money(d.prior_bound_premium.sum()))
    c[2].metric("Prior commission", ins.money(d.prior_commission.sum()))
    top = d.head(25)
    fig = go.Figure(go.Bar(y=top.name[::-1], x=top.prior_bound_premium[::-1], orientation="h", marker_color=ACCENT))
    fig.update_xaxes(title="Prior bound premium (USD)")
    st.plotly_chart(style(fig, 620), use_container_width=True)
    takeaway(ins.takeaway_dormant(d))
    st.dataframe(d[["priority_rank", "name", "owner", "state", "specialty_focus", "days_dormant", "prior_complete_submissions", "prior_bound_premium", "score"]],
                 hide_index=True, use_container_width=True)


def view_pipeline():
    p = mart("pipeline_projection")
    st.subheader("Pipeline and Revenue Projection by Segment")
    with st.expander("Assumptions behind this projection"):
        st.markdown(f"- Open pipeline = agencies whose highest stage is ICP, engaged, first submission or quoted with activity in the last {config.PIPELINE_OPEN_DAYS} days.\n"
                    "- Each converts at its segment's observed P(bound | stage reached); the overall rate is used when a segment has fewer than %d agencies at that stage.\n"
                    "- Revenue per bound agency = observed average first-bind commission. Repeat revenue is excluded. This is a projection from synthetic rates, not a forecast." % config.MIN_N)
    c = st.columns(3)
    c[0].metric("Expected new bound agencies", f"{p.expected_new_bound_agencies.sum():.0f}")
    c[1].metric("Projected first-bind commission", ins.money(p.projected_commission.sum()))
    c[2].metric("Projected bound premium", ins.money(p.projected_premium.sum()))
    p = p.sort_values("projected_commission")
    fig = go.Figure()
    for col, nm, colr in (("open_icp", "ICP-qualified", MUTED), ("open_engaged", "Engaged", "#5b8e7d"), ("open_first_submission", "First submission", ACCENT), ("open_quoted", "Quoted", ALERT)):
        fig.add_bar(y=p.segment, x=p[col], name=nm, orientation="h", marker_color=colr)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Open agencies by stage")
    st.plotly_chart(style(fig, 360), use_container_width=True)
    fig = go.Figure(go.Bar(y=p.segment, x=p.projected_commission, orientation="h", marker_color=ACCENT))
    fig.update_xaxes(title="Projected first-bind commission (USD)")
    st.plotly_chart(style(fig, 320), use_container_width=True)
    takeaway(ins.takeaway_pipeline(p))
    st.dataframe(p.sort_values("projected_commission", ascending=False)[["segment", "expected_new_bound_agencies", "avg_first_bind_commission", "projected_commission", "projected_premium"]],
                 hide_index=True, use_container_width=True)


def view_ranked():
    r = mart("ranked_accounts")
    st.subheader("Ranked Accounts")
    c = st.columns(3)
    tiers = c[0].multiselect("Tier", ["Tier 1", "Tier 2", "Reactivation", "Tier 3"], default=["Tier 1", "Tier 2", "Reactivation"])
    owners = c[1].multiselect("Owner", sorted(r.owner.unique()))
    q = c[2].text_input("Search name")
    f = r[r.tier.isin(tiers)]
    if owners:
        f = f[f.owner.isin(owners)]
    if q:
        f = f[f.name.str.contains(q, case=False, regex=False)]
    vc = r.tier.value_counts().reindex(["Tier 1", "Tier 2", "Reactivation", "Tier 3"])
    fig = go.Figure(go.Bar(x=vc.index, y=vc.values, marker_color=ACCENT, text=vc.values, textposition="outside"))
    st.plotly_chart(style(fig, 260), use_container_width=True)
    takeaway(ins.takeaway_ranked(r))
    st.caption("Score = 0.30 specialty fit + 0.25 commercial volume + 0.20 E&S activity + 0.15 engagement + 0.10 geographic priority. Every reason names the top two drivers.")
    st.dataframe(f[["name", "score", "tier", "next_action", "owner", "channel", "reason"]].head(500), hide_index=True, use_container_width=True)


def view_experiments():
    e = mart("experiment_results")
    st.subheader("Experiments")
    st.warning("These are SIMULATED results on synthetic data. They demonstrate the method; the generator planted the effects (A +30%, B +15%, C 0).")
    for _, r in e.iterrows():
        st.markdown(f"### Experiment {r.experiment_id}: {r['name']}")
        c = st.columns(4)
        c[0].metric("Decision", r.decision)
        c[1].metric("Relative lift", f"{r.rel_lift:+.1%}")
        c[2].metric("p-value", f"{r.p_value:.3f}")
        c[3].metric("Confidence level", f"{(1 - r.alpha):.0%}")
        fig = go.Figure()
        fig.add_scatter(x=[r.rel_lift * 100], y=[r["name"]], mode="markers", marker=dict(size=12, color=ACCENT),
                        error_x=dict(type="data", symmetric=False, array=[(r.rel_ci_high - r.rel_lift) * 100], arrayminus=[(r.rel_lift - r.rel_ci_low) * 100], color=ACCENT), name="Estimate (95% CI)")
        fig.add_vline(x=0, line_dash="dot", line_color=MUTED)
        if pd.notna(r.planted_true_lift):
            fig.add_vline(x=r.planted_true_lift * 100, line_color=ALERT, annotation_text="planted truth", annotation_position="top")
        fig.update_xaxes(title="Relative lift (%)")
        st.plotly_chart(style(fig, 170), use_container_width=True)
        takeaway(ins.takeaway_experiment(r))
        st.caption(f"Control {int(r.x_control)}/{int(r.n_control)} = {r.rate_control:.1%}; treatment {int(r.x_treatment)}/{int(r.n_treatment)} = {r.rate_treatment:.1%}; "
                   f"achieved power {r.achieved_power:.0%}; SRM p = {r.srm_p_value:.2f}.")


RENDER = {"Monday Morning": view_monday, "Weekly Growth Review": view_weekly, "Source Quality": view_sources,
          "Time-to-Quote": view_ttq, "Activation and Cohorts": view_activation, "Dormancy and Reactivation": view_dormant,
          "Pipeline and Revenue Projection": view_pipeline, "Ranked Accounts": view_ranked, "Experiments": view_experiments}

st.sidebar.title("Broker Growth OS")
view = st.sidebar.radio("View", VIEWS, key="view")
st.sidebar.caption("All data is synthetic. As-of date: %s." % config.AS_OF)
RENDER[view]()
