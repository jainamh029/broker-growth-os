"""Broker Growth OS dashboard (Streamlit). Reads ONLY from data/marts (written by the SQL metrics layer).

All data is SYNTHETIC. The banner below must stay on every view.
"""
import json
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
from bgos import theme  # noqa: E402
from bgos import experiments as ex  # noqa: E402

INK, ACCENT, MUTED, ALERT = theme.INK, theme.BLUE, theme.MUTED, theme.AMBER
GREEN, TEAL, SKY, MINT = theme.GREEN, theme.TEAL, theme.SKY, theme.MINT
REPO = "https://github.com/jainamh029/broker-growth-os"
SITE = "https://jainamh029.github.io/broker-growth-os/"

st.set_page_config(page_title="Broker Growth OS", layout="wide", page_icon=":bar_chart:")
st.markdown(theme.APP_CSS, unsafe_allow_html=True)
st.markdown(
    "<div class='hero'><h1>Broker Growth OS</h1>"
    "<p>Funnel, fit scoring, metrics and experiments for an AI-native specialty insurance wholesaler.</p>"
    "<span class='pill'>Synthetic data</span><span class='pill'>Simulated experiments</span><span class='pill'>Human-in-the-loop AI</span></div>",
    unsafe_allow_html=True)
st.markdown(f"<div class='banner'><b>{BANNER}</b></div>", unsafe_allow_html=True)


def mart(name: str) -> pd.DataFrame:
    path = config.get_paths().marts / f"{name}.csv"
    if not path.exists():
        # First run (e.g. on Streamlit Community Cloud): generate the synthetic data, then read the marts.
        with st.spinner("First run: generating synthetic data (about a minute)..."):
            from bgos.cli import bootstrap_once
            bootstrap_once(None)
    if not path.exists():
        st.error(f"Missing data mart `{name}`. Run `make all` first.")
        st.stop()
    return pd.read_csv(path)


def takeaway(text: str) -> None:
    st.markdown(f"<div class='takeaway'><b>Takeaway.</b> {text}</div>", unsafe_allow_html=True)


def style(fig: go.Figure, h: int = 340) -> go.Figure:
    fig.update_layout(template="plotly_white", height=h, margin=dict(l=10, r=10, t=30, b=10), font=dict(color=INK, size=13),
                      legend=dict(orientation="h", y=-0.2), colorway=theme.COLORWAY, hovermode="closest", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor="#ffffff", font_size=13))
    fig.update_xaxes(gridcolor=theme.GRID)
    fig.update_yaxes(gridcolor=theme.GRID)
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
    c1, c2 = st.columns(2)
    mode = c1.toggle("Show share of raw leads instead of share of previous stage", value=False, key="funnel_mode")
    observed = c2.toggle("Include leads too recent to have converted (observed, understates)", value=False, key="funnel_observed")
    if observed:
        share = ff.observed_cumulative_conversion if mode else ff.observed_step_conversion
    else:
        share = ff.mature_cumulative_conversion if mode else ff.mature_step_conversion
    fig = go.Figure(go.Bar(y=[stage_name(s) for s in ff.stage], x=ff.agencies, orientation="h",
                           marker=dict(color=list(range(len(ff))), colorscale=[[0, ACCENT], [1, GREEN]]),
                           text=[f"{int(a):,}" + ("" if pd.isna(v) else f"  ({v:.0%})") for a, v in zip(ff.agencies, share)],
                           textposition="auto", hovertemplate="%{y}: %{x} agencies<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(style(fig, 360), width="stretch")
    takeaway(ins.takeaway_funnel(f))
    st.caption("Rates shown are cohort-mature: each step is measured only on agencies that reached the previous stage long enough ago to have converted "
               "(windows set from the observed lags). The synthetic funnel is deliberately generous so Experiment A can be statistically powered; real conversion rates will be lower.")
    r = mart("ranked_accounts")
    new_biz = r[r.tier.isin(["Tier 1", "Tier 2"])]
    n_show = st.slider("Accounts to show", 3, 25, 8, key="monday_n")
    top = new_biz.sort_values(["tier", "score"], ascending=[True, False]).head(n_show)[["name", "score", "tier", "next_action", "owner", "channel", "reason"]]
    st.markdown("**Work first this week: highest-fit prospects that are not yet submitting**")
    st.dataframe(top, hide_index=True, width="stretch",
                 column_config={"score": st.column_config.ProgressColumn("score", min_value=0.0, max_value=1.0, format="%.2f")})


def view_weekly():
    w = mart("weekly_growth_review")
    st.subheader("Weekly Growth Review")
    st.caption("North star: qualified submissions per week = complete submissions from ICP agencies that are new or active (previous submission < 60 days earlier).")
    full = w[w.is_partial_week == 0].copy()
    full["wk"] = pd.to_datetime(full.week_start)
    weeks = full.week_start.tolist()
    c1, c2 = st.columns([3, 1])
    lo, hi = c1.select_slider("Weeks shown", options=weeks, value=(weeks[0], weeks[-1]), key="week_range")
    show_ma = c2.toggle("4-week average", value=True, key="show_ma")
    full["ma4"] = full.qualified_submissions.rolling(4).mean()
    sel = full[(full.week_start >= lo) & (full.week_start <= hi)]
    fig = go.Figure()
    fig.add_bar(x=sel.wk, y=sel.qualified_submissions, name="Qualified submissions", marker_color=ACCENT,
                hovertemplate="Week of %{x|%b %d}: %{y}<extra></extra>")
    if show_ma:
        fig.add_scatter(x=sel.wk, y=sel.ma4, name="4-week average", line=dict(color=GREEN, width=3))
    st.plotly_chart(style(fig), width="stretch")
    takeaway(ins.takeaway_north_star(w))
    st.markdown("**Inputs** (what we control)")
    fig = go.Figure()
    for col, nm, colr in (("new_icp_agencies", "New ICP agencies", ACCENT), ("new_engaged_agencies", "Newly engaged", TEAL), ("new_activations", "Activations (first complete submission)", GREEN)):
        fig.add_scatter(x=sel.wk, y=full[col].rolling(4).mean().loc[sel.index], name=nm + " (4-wk avg)", line=dict(color=colr, width=2))
    st.plotly_chart(style(fig, 300), width="stretch")
    st.markdown("**Diagnostics** (why the north star moved)")
    fig = go.Figure()
    for col, nm, colr in (("completeness_rate", "Submission completeness", ACCENT), ("quote_rate", "Quote rate", TEAL), ("bind_rate_of_quoted", "Bind rate of quoted", GREEN)):
        fig.add_scatter(x=sel.wk, y=sel[col], name=nm, line=dict(color=colr, width=2), connectgaps=False)
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(style(fig, 300), width="stretch")
    last = full.dropna(subset=["completeness_rate"]).tail(4)
    takeaway(f"Over the last 4 weeks with data, {ins.pct(last.completeness_rate.mean(), 0)} of submissions arrived complete; "
             f"{int(full.tail(4).reactivated_submissions.sum())} submissions came from reactivated (previously dormant) agencies and are excluded from the north star.")
    st.dataframe(sel.tail(8)[["week_start", "qualified_submissions", "new_icp_agencies", "new_engaged_agencies", "new_activations", "completeness_rate", "quote_rate", "bind_rate_of_quoted"]],
                 hide_index=True, width="stretch")


def view_sources():
    sq = mart("source_quality")
    st.subheader("Source Quality")
    st.caption("Judged by downstream bind and repeat, not lead count. Sources with fewer than %d agencies are suppressed." % config.MIN_N)
    labels = {"bind_rate_per_lead": "Bound agencies per lead", "first_submission_rate": "First-submission rate",
              "repeat_rate_of_bound": "Repeat rate of bound agencies", "commission_per_lead": "Commission per lead"}
    metric = st.selectbox("Quality metric", list(labels), format_func=labels.get, key="src_metric")
    ok = sq[sq.suppressed == 0].dropna(subset=[metric]).sort_values(metric, ascending=False)
    c1, c2 = st.columns(2)
    is_money = metric == "commission_per_lead"
    fig = go.Figure(go.Bar(x=ok.lead_source, y=ok[metric], marker_color=ACCENT,
                           text=[ins.money(v) if is_money else ins.pct(v) for v in ok[metric]], textposition="outside"))
    fig.update_yaxes(tickformat=None if is_money else ".0%", title=labels[metric])
    c1.plotly_chart(style(fig), width="stretch")
    fig = go.Figure(go.Bar(x=sq[sq.suppressed == 0].lead_source, y=sq[sq.suppressed == 0].leads, marker_color=GREEN,
                           text=sq[sq.suppressed == 0].leads, textposition="outside"))
    fig.update_yaxes(title="Leads (volume)")
    c2.plotly_chart(style(fig), width="stretch")
    takeaway(ins.takeaway_sources(sq))
    show_tiny = st.toggle("Include suppressed tiny-n sources in the table", value=True, key="src_tiny")
    table = sq if show_tiny else sq[sq.suppressed == 0]
    st.dataframe(table[["lead_source", "leads", "first_submission_rate", "bind_rate_per_lead", "repeat_rate_of_bound", "commission_per_lead", "suppressed"]],
                 hide_index=True, width="stretch")


def view_ttq():
    t = mart("time_to_quote")
    st.subheader("Time-to-Quote")
    scope = st.radio("Scope", ["all_submissions", "first_submissions"], horizontal=True,
                     format_func=lambda s: "All quoted submissions" if s == "all_submissions" else "Each agency's first submission")
    d = t[t.scope == scope]
    c1, c2 = st.columns(2)
    cx = d[d.dimension == "risk_complexity"].set_index("value").reindex(["low", "medium", "high"]).dropna(subset=["median_hours"])
    fig = go.Figure(go.Bar(x=cx.index, y=cx.median_hours, marker_color=[SKY, ACCENT, theme.BLUE_DARK][:len(cx)],
                           text=[f"{v:.0f}h" for v in cx.median_hours], textposition="outside"))
    fig.update_yaxes(title="Median hours to quote")
    c1.plotly_chart(style(fig), width="stretch")
    lob = d[d.dimension == "line_of_business"].sort_values("median_hours")
    if len(lob):
        fig = go.Figure(go.Bar(y=lob.value, x=lob.median_hours, orientation="h", marker_color=GREEN))
        fig.update_xaxes(title="Median hours to quote")
        c2.plotly_chart(style(fig), width="stretch")
    else:
        c2.info("Line-of-business split is shown for the all-submissions scope.")
    takeaway(ins.takeaway_ttq(t))
    st.dataframe(d[["dimension", "value", "n", "median_hours"]], hide_index=True, width="stretch")


def view_activation():
    act, coh = mart("activation_rate"), mart("cohort_retention")
    st.subheader("Activation and Cohorts")
    m = act[act.cohort != "ALL"]
    fig = go.Figure(go.Bar(x=m.cohort, y=m.activation_rate, marker_color=GREEN, text=[ins.pct(v, 0) for v in m.activation_rate], textposition="outside"))
    fig.update_yaxes(tickformat=".0%", title="Engaged agencies submitting within 14 days")
    st.plotly_chart(style(fig), width="stretch")
    windows = {"All windows": ["retention_30", "retention_60", "retention_90"], "30 days": ["retention_30"],
               "60 days": ["retention_60"], "90 days": ["retention_90"]}
    choice = st.selectbox("Retention window", list(windows), key="ret_window")
    cols = windows[choice]
    c = coh[coh.cohort != "ALL"].set_index("cohort")[cols]
    heat = go.Figure(go.Heatmap(z=c.values, x=[x.replace("retention_", "") + " days" for x in cols], y=c.index,
                                colorscale=[[0, "#eef2f7"], [0.5, MINT], [1, theme.BLUE_DARK]],
                                text=[[ins.pct(v, 0) for v in row] for row in c.values], texttemplate="%{text}", zmin=0, zmax=1, showscale=False))
    heat.update_yaxes(autorange="reversed", title="First-submission month")
    st.plotly_chart(style(heat, 420), width="stretch")
    takeaway(ins.takeaway_activation(act, coh))
    st.caption("Only mature agencies (a full window observed before the as-of date) are in each denominator; blank cells are suppressed or immature. "
               "These repeat rates are anchored on the FIRST SUBMISSION (30/60/90 days); the funnel's Repeat stage is anchored on the first BIND (90 days), so the two differ by design.")


def view_dormant():
    d = mart("dormant_reactivation")
    st.subheader("Dormancy and Reactivation")
    c = st.columns(3)
    c[0].metric("Dormant agencies", f"{len(d):,}")
    c[1].metric("Prior bound premium", ins.money(d.prior_bound_premium.sum()))
    c[2].metric("Prior commission", ins.money(d.prior_commission.sum()))
    f1, f2 = st.columns([1, 2])
    top_n = f1.slider("Top agencies to chart", 5, 50, 25, key="dorm_n")
    specs = f2.multiselect("Specialty focus", sorted(d.specialty_focus.unique()), key="dorm_spec")
    sel = d[d.specialty_focus.isin(specs)] if specs else d
    top = sel.head(top_n)
    fig = go.Figure(go.Bar(y=top.name[::-1], x=top.prior_bound_premium[::-1], orientation="h", marker_color=ACCENT,
                           hovertemplate="%{y}<br>prior bound premium: %{x:$,.0f}<extra></extra>"))
    fig.update_xaxes(title="Prior bound premium (USD)")
    st.plotly_chart(style(fig, max(320, 22 * len(top) + 80)), width="stretch")
    takeaway(ins.takeaway_dormant(d))
    cols = ["priority_rank", "name", "owner", "state", "specialty_focus", "days_dormant", "prior_complete_submissions", "prior_bound_premium", "score"]
    st.dataframe(sel[cols], hide_index=True, width="stretch")
    st.download_button("Download this list (CSV)", sel[cols].to_csv(index=False), file_name="dormant_agencies.csv", mime="text/csv")


def view_pipeline():
    p_all = mart("pipeline_projection")
    st.subheader("Pipeline and Revenue Projection by Segment")
    with st.expander("Assumptions behind this projection"):
        st.markdown(f"- Open (pending) pipeline = agencies whose highest stage is ICP, engaged, first submission or quoted and that reached it within the maturity window of the next step; older ones are treated as lost.\n"
                    "- Each converts at the product of its segment's remaining cohort-mature step rates; the overall rate is used when a segment has fewer than %d agencies at that stage.\n"
                    "- Revenue per bound agency = observed average first-bind commission. Repeat revenue is excluded. This is a projection from synthetic rates, not a forecast." % config.MIN_N)
    segs = st.multiselect("Segments", sorted(p_all.segment), default=sorted(p_all.segment), key="pipe_segs")
    p = p_all[p_all.segment.isin(segs)] if segs else p_all
    c = st.columns(3)
    c[0].metric("Expected new bound agencies", f"{p.expected_new_bound_agencies.sum():.0f}")
    c[1].metric("Projected first-bind commission", ins.money(p.projected_commission.sum()))
    c[2].metric("Projected bound premium", ins.money(p.projected_premium.sum()))
    p = p.sort_values("projected_commission")
    fig = go.Figure()
    for col, nm, colr in (("open_icp", "ICP-qualified", SKY), ("open_engaged", "Engaged", MINT), ("open_first_submission", "First submission", ACCENT), ("open_quoted", "Quoted", GREEN)):
        fig.add_bar(y=p.segment, x=p[col], name=nm, orientation="h", marker_color=colr)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Open agencies by stage")
    st.plotly_chart(style(fig, 360), width="stretch")
    fig = go.Figure(go.Bar(y=p.segment, x=p.projected_commission, orientation="h", marker_color=GREEN))
    fig.update_xaxes(title="Projected first-bind commission (USD)")
    st.plotly_chart(style(fig, 320), width="stretch")
    takeaway(ins.takeaway_pipeline(p_all))
    st.dataframe(p.sort_values("projected_commission", ascending=False)[["segment", "expected_new_bound_agencies", "avg_first_bind_commission", "projected_commission", "projected_premium"]],
                 hide_index=True, width="stretch")


def view_ranked():
    r = mart("ranked_accounts")
    st.subheader("Ranked Accounts")
    c = st.columns(3)
    tiers = c[0].multiselect("Tier", ["Tier 1", "Tier 2", "Tier 3", "Active", "Reactivation"], default=["Tier 1", "Tier 2"])
    owners = c[1].multiselect("Owner", sorted(r.owner.unique()))
    q = c[2].text_input("Search name")
    d = st.columns([2, 1])
    states = d[0].multiselect("State", sorted(r.state.unique()), key="rank_states")
    min_score = d[1].slider("Minimum score", 0.0, 1.0, 0.0, 0.05, key="rank_min")
    f = r[r.tier.isin(tiers) & (r.score >= min_score)]
    if owners:
        f = f[f.owner.isin(owners)]
    if states:
        f = f[f.state.isin(states)]
    if q:
        f = f[f.name.str.contains(q, case=False, regex=False)]
    vc = r.tier.value_counts().reindex(["Tier 1", "Tier 2", "Tier 3", "Active", "Reactivation"])
    fig = go.Figure(go.Bar(x=vc.index, y=vc.values, marker_color=[GREEN, ACCENT, MUTED, TEAL, SKY], text=vc.values, textposition="outside"))
    st.plotly_chart(style(fig, 260), width="stretch")
    takeaway(ins.takeaway_ranked(r))
    hold = mart("tier_holdout")
    st.markdown("**Out-of-sample check.** Prospects scored 90 days before the as-of date using only data available then; first submissions counted in the following 90 days.")
    st.dataframe(hold[["tier", "prospects", "converted", "rate"]], hide_index=True, width="stretch",
                 column_config={"rate": st.column_config.NumberColumn("conversion", format="percent")})
    st.caption("Tiers 1-3 contain prospects only; customers are Active or Reactivation. Engagement counts opens, clicks, replies and meetings, never submissions. On synthetic data this checks plumbing, not real predictive power. Score = 0.30 specialty fit + 0.25 commercial volume + 0.20 E&S activity + 0.15 engagement + 0.10 geographic priority. Every reason names the top two drivers.")
    st.markdown(f"**{len(f):,} accounts match** (showing the first 500)")
    cols = ["name", "score", "tier", "next_action", "owner", "channel", "reason"]
    st.dataframe(f[cols].head(500), hide_index=True, width="stretch",
                 column_config={"score": st.column_config.ProgressColumn("score", min_value=0.0, max_value=1.0, format="%.2f")})
    st.download_button("Download filtered accounts (CSV)", f[cols].to_csv(index=False), file_name="ranked_accounts_filtered.csv", mime="text/csv")


def view_experiments():
    e = mart("experiment_results")
    st.subheader("Experiments")
    st.warning("These are SIMULATED results on synthetic data. They demonstrate the method; the generator planted the effects (A +30%, B +15%, C 0).")
    sweep_path = ROOT / "docs" / "seed_sweep.json"
    note = "Each result below is one simulated draw. Running three experiments at once carries a multiple comparisons risk; no alpha adjustment is applied."
    if sweep_path.exists():
        sm = json.loads(sweep_path.read_text())["summary"]
        note += (f" Across {sm['n_seeds']} simulated seeds: A ships in {sm['A']['decisions'].get('SHIP', 0)}, B in {sm['B']['decisions'].get('SHIP', 0)}, "
                 f"and C looks significant by chance in {sm['C']['significant_p_lt_0.05']}.")
    st.caption(note)
    tabs = st.tabs([f"{r.experiment_id}: {r['name']}" for _, r in e.iterrows()])
    for tab, (_, r) in zip(tabs, e.iterrows()):
        with tab:
            c = st.columns(4)
            c[0].metric("Decision", r.decision)
            if r.experiment_id == "C":
                st.info("Experiment C cannot be powered at this size; INCONCLUSIVE is expected. Absolute lift is the headline; relative lift on a small base is shown only as a secondary figure.")
                c[1].metric("Absolute lift (points)", f"{r.abs_lift * 100:+.1f}")
            else:
                c[1].metric("Relative lift", f"{r.rel_lift:+.1%}")
            c[2].metric("p-value", "< 0.001" if r.p_value < 0.001 else f"{r.p_value:.3f}")
            c[3].metric("Confidence level", f"{(1 - r.alpha):.0%}")
            if r.experiment_id == "C":
                d = st.columns(3)
                d[0].metric("95% CI (points)", f"{r.abs_ci_low * 100:+.1f} to {r.abs_ci_high * 100:+.1f}")
                d[1].metric("Detectable lift at 80% power (points)", f"{r.mde_abs_at_n * 100:.1f}")
                d[2].metric("Detectable lift, relative", f"{r.mde_rel_at_n:+.0%}")
                st.caption(f"Secondary: relative lift {r.rel_lift:+.1%} (95% CI {r.rel_ci_low:+.1%} to {r.rel_ci_high:+.1%}).")
            fig = go.Figure()
            fig.add_scatter(x=[r.rel_lift * 100], y=[r["name"]], mode="markers", marker=dict(size=13, color=ACCENT),
                            error_x=dict(type="data", symmetric=False, array=[(r.rel_ci_high - r.rel_lift) * 100], arrayminus=[(r.rel_lift - r.rel_ci_low) * 100], color=ACCENT),
                            name="Estimate (95% CI)")
            fig.add_vline(x=0, line_dash="dot", line_color=MUTED)
            if pd.notna(r.planted_true_lift):
                fig.add_vline(x=r.planted_true_lift * 100, line_color=GREEN, line_width=3, annotation_text="planted truth", annotation_position="top")
            fig.update_xaxes(title="Relative lift (%)")
            st.plotly_chart(style(fig, 170), width="stretch")
            takeaway(ins.takeaway_experiment(r))
            have, need = min(int(r.n_control), int(r.n_treatment)), int(r.n_required_per_arm)
            st.progress(min(1.0, have / need), text=f"Sample reached: {have:,} of {need:,} required per arm")
            st.caption(f"Control {int(r.x_control)}/{int(r.n_control)} = {r.rate_control:.1%}; treatment {int(r.x_treatment)}/{int(r.n_treatment)} = {r.rate_treatment:.1%}; "
                       f"power at the pre-registered {r.mde_relative:.0%} lift {r.power_at_mde:.0%}; SRM p = {r.srm_p_value:.2f}.")
            if not r.ci_low_clears_ship:
                st.caption(f"Note: the lower bound of the 95% CI ({r.rel_ci_low:+.1%}) is below the {r.mde_relative:.0%} ship threshold. The rule ships on the point estimate, so there is winner's-curse risk.")
    split = mart("experiment_a_icp_split")
    st.markdown("### Observational panel (not an experiment)")
    st.caption("First-submission rate of ICP vs non-ICP agencies within Experiment A's control arm, same outcome window and mature-only rule. "
               "The generator never lets non-ICP agencies submit, so on synthetic data this contrast holds by construction.")
    st.dataframe(split.assign(group=split.is_icp.map({1: "ICP", 0: "non-ICP"}))[["group", "n", "x", "rate", "ci_low", "ci_high"]], hide_index=True, width="stretch",
                 column_config={"rate": st.column_config.NumberColumn("rate", format="percent"), "ci_low": st.column_config.NumberColumn("95% Wilson low", format="percent"),
                                "ci_high": st.column_config.NumberColumn("95% Wilson high", format="percent")})
    takeaway(ins.takeaway_icp_split(split))
    st.markdown("### Sample-size calculator")
    st.caption("How many agencies per arm would a real test need? Uses the same two-proportion formula as the framework.")
    k = st.columns(4)
    base = k[0].slider("Baseline rate (%)", 2, 60, 10, key="calc_base")
    lift = k[1].slider("Relative lift to detect (%)", 5, 60, 20, key="calc_lift")
    alpha = k[2].selectbox("Alpha", [0.10, 0.05, 0.01], index=1, key="calc_alpha")
    power = k[3].selectbox("Power", [0.80, 0.90, 0.95], index=0, key="calc_power")
    p1 = base / 100
    p2 = min(0.99, p1 * (1 + lift / 100))
    n_arm = ex.sample_size_two_proportions(p1, p2, alpha, power)
    out = st.columns(3)
    out[0].metric("Required per arm", f"{n_arm:,}")
    out[1].metric("Total agencies", f"{2 * n_arm:,}")
    out[2].metric("Treatment rate to detect", f"{p2:.1%}")


RENDER = {"Monday Morning": view_monday, "Weekly Growth Review": view_weekly, "Source Quality": view_sources,
          "Time-to-Quote": view_ttq, "Activation and Cohorts": view_activation, "Dormancy and Reactivation": view_dormant,
          "Pipeline and Revenue Projection": view_pipeline, "Ranked Accounts": view_ranked, "Experiments": view_experiments}

st.sidebar.markdown("### Broker Growth OS")
view = st.sidebar.radio("View", VIEWS, key="view")
st.sidebar.caption("All data is synthetic. As-of date: %s." % config.AS_OF)
with st.sidebar.expander("About this prototype"):
    st.markdown(f"Funnel, scoring, SQL metrics, experiments and a human-in-the-loop AI layer, all on generated data.\n\n"
                f"[Source code]({REPO}) &middot; [Static showcase]({SITE})")
RENDER[view]()
st.markdown("<div class='footer'>Synthetic data. Experiment results are simulated and demonstrate the method only.</div>", unsafe_allow_html=True)
