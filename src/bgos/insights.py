"""Plain-English takeaway lines, computed from the metric tables (no hard-coded numbers). SYNTHETIC data."""
from __future__ import annotations

import pandas as pd

from . import funnel
from .experiments import fmt_p


def pct(x: float, d: int = 1) -> str:
    return "n/a" if pd.isna(x) else f"{x * 100:.{d}f}%"


def money(x: float) -> str:
    return "n/a" if pd.isna(x) else (f"${x / 1e6:.2f}M" if abs(x) >= 1e6 else f"${x / 1e3:,.0f}K" if abs(x) >= 1e4 else f"${x:,.0f}")


def takeaway_funnel(f: pd.DataFrame) -> str:
    """Uses COHORT-MATURE conversion (each step measured only on agencies old enough to have converted)."""
    f = f.sort_values("stage_order")
    raw, bound = int(f.iloc[0].agencies), f[f.stage == "bound"].iloc[0]
    steps = f.iloc[1:].dropna(subset=["mature_step_conversion"])
    worst = steps.loc[steps.mature_step_conversion.idxmin()]
    prev = f[f.stage_order == worst.stage_order - 1].iloc[0]
    return (f"Of {raw:,} raw leads, {int(bound.agencies):,} have bound so far ({pct(bound.observed_cumulative_conversion)} observed, which understates it because recent leads have not had time to convert). "
            f"Counting only agencies old enough to have converted, {pct(bound.mature_cumulative_conversion)} of leads reach a bind. "
            f"The biggest drop is {funnel.STAGE_BY_KEY[prev.stage].name} to {funnel.STAGE_BY_KEY[worst.stage].name}: only {pct(worst.mature_step_conversion, 0)} continue.")


def takeaway_north_star(w: pd.DataFrame) -> str:
    full = w[w.is_partial_week == 0]
    recent, before = full.tail(4).qualified_submissions.mean(), full.iloc[-8:-4].qualified_submissions.mean()
    chg = (recent / before - 1) if before else float("nan")
    return (f"Qualified submissions averaged {recent:.1f} per week over the last 4 full weeks, "
            f"{'up' if chg >= 0 else 'down'} {pct(abs(chg), 0)} vs the 4 weeks before ({before:.1f}).")


def takeaway_sources(sq: pd.DataFrame) -> str:
    ok = sq[sq.suppressed == 0].dropna(subset=["bind_rate_per_lead"])
    best, worst = ok.loc[ok.bind_rate_per_lead.idxmax()], ok.loc[ok.bind_rate_per_lead.idxmin()]
    tiny = sq[sq.suppressed == 1]
    share = worst.leads / ok.leads.sum()
    s = (f"{best.lead_source} turns {pct(best.bind_rate_per_lead)} of leads into bound business versus {pct(worst.bind_rate_per_lead)} for "
         f"{worst.lead_source} ({best.bind_rate_per_lead / worst.bind_rate_per_lead:.1f}x), yet {worst.lead_source} supplies "
         f"{pct(share, 0)} of lead volume and {best.lead_source} only {pct(best.leads / ok.leads.sum(), 0)}.")
    if len(tiny):
        s += f" {len(tiny)} tiny sources (n < 20) are suppressed: a 100% rate on a handful of agencies is noise."
    return s


def takeaway_ttq(t: pd.DataFrame) -> str:
    o = t[(t.scope == "all_submissions") & (t.dimension == "overall")].iloc[0]
    cx = t[(t.scope == "all_submissions") & (t.dimension == "risk_complexity")].set_index("value").median_hours
    fs = t[(t.scope == "first_submissions") & (t.dimension == "overall")].iloc[0]
    return (f"Median time to quote is {o.median_hours:.0f} hours across {int(o.n):,} quoted submissions ({fs.median_hours:.0f} hours for first submissions); "
            f"high-complexity risks take {cx['high'] / cx['low']:.1f}x as long as low-complexity ones ({cx['high']:.0f}h vs {cx['low']:.0f}h).")


def takeaway_activation(act: pd.DataFrame, coh: pd.DataFrame) -> str:
    a = act[act.cohort == "ALL"].iloc[0]
    c = coh[coh.cohort == "ALL"].iloc[0]
    m = act[(act.cohort != "ALL")].dropna(subset=["activation_rate"])
    low = m.loc[m.activation_rate.idxmin()]
    return (f"{pct(a.activation_rate, 0)} of engaged agencies send a complete submission within 14 days (weakest cohort: {low.cohort} at {pct(low.activation_rate, 0)}); "
            f"{pct(c.retention_30, 0)} / {pct(c.retention_60, 0)} / {pct(c.retention_90, 0)} of first-time submitters come back within 30 / 60 / 90 days.")


def takeaway_dormant(d: pd.DataFrame) -> str:
    top = d.head(25)
    return (f"{len(d):,} dormant agencies hold {money(d.prior_bound_premium.sum())} of prior bound premium; the top 25 hold "
            f"{pct(top.prior_bound_premium.sum() / d.prior_bound_premium.sum(), 0)} of it, so start there.")


def takeaway_pipeline(p: pd.DataFrame) -> str:
    top = p.loc[p.projected_commission.idxmax()]
    return (f"Open pipeline projects to ~{p.expected_new_bound_agencies.sum():.0f} new bound agencies and {money(p.projected_commission.sum())} of first-bind commission "
            f"(assumption-driven); {top.segment} contributes the most ({money(top.projected_commission)}). Repeat revenue is excluded.")


def takeaway_ranked(r: pd.DataFrame) -> str:
    vc = r.tier.value_counts()
    return (f"Of {len(r):,} agencies, {vc.get('Active', 0):,} are active customers to expand and {vc.get('Reactivation', 0):,} need win-back. "
            f"Among prospects, {vc.get('Tier 1', 0):,} are Tier 1 for immediate outbound, {vc.get('Tier 2', 0):,} are Tier 2 nurture and {vc.get('Tier 3', 0):,} are monitor-only.")


def takeaway_experiment(r: pd.Series) -> str:
    have, need = min(int(r["n_control"]), int(r["n_treatment"])), int(r["n_required_per_arm"])
    if r["experiment_id"] == "C":  # cannot be powered at this size: lead with the absolute lift and the detectable effect
        return (f"{r['decision']}: absolute lift {r['abs_lift'] * 100:+.1f} points (95% CI {r['abs_ci_low'] * 100:+.1f} to {r['abs_ci_high'] * 100:+.1f}), p {fmt_p(r['p_value'])}. "
                f"Experiment C cannot be powered at this size; INCONCLUSIVE is expected. ({have:,} per arm vs {need:,} required.) "
                f"At {have:,} per arm only a lift of {r['mde_abs_at_n'] * 100:.1f} points ({r['mde_rel_at_n']:+.0%} relative) or more would be detectable at 80% power.")
    return (f"{r['decision']}: relative lift {r['rel_lift']:+.1%} (95% CI {r['rel_ci_low']:+.1%} to {r['rel_ci_high']:+.1%}), p {fmt_p(r['p_value'])}; "
            f"{have:,} per arm vs {need:,} required.")


def wilson_ci(x: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    from scipy import stats
    z = stats.norm.ppf(1 - alpha / 2)
    p = x / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return centre - half, centre + half


def takeaway_icp_split(d: pd.DataFrame) -> str:
    a = d.set_index("is_icp")
    return (f"Observational, not an experiment: in the control arm, ICP agencies reached a first submission at {pct(a.loc[1, 'rate'])} versus {pct(a.loc[0, 'rate'])} for non-ICP agencies "
            f"(n = {int(a.loc[1, 'n']):,} and {int(a.loc[0, 'n']):,}). Experiment A tests the v2 sequence against v1, not the ICP definition.")


def n_sensitivity_rows(doc: dict) -> list[dict]:
    rows = []
    for n, exps in doc["summary"].items():
        for k in "ABC":
            d = exps[k]["decisions"]
            rows.append({"agencies": int(n), "experiment": k, "ship": d.get("SHIP", 0), "iterate": d.get("ITERATE", 0), "inconclusive": d.get("INCONCLUSIVE", 0),
                         "mean_required": exps[k]["mean_required_per_arm"], "mean_achieved": exps[k]["mean_achieved_per_arm"]})
    return rows


def takeaway_n_sensitivity(doc: dict) -> str:
    seeds = len(doc["seeds"])
    a = {int(n): v["A"]["decisions"].get("SHIP", 0) for n, v in doc["summary"].items()}
    ns = sorted(a)
    parts = [f"{'at' if i == 0 else 'at'} {n:,}, {a[n]}" for i, n in enumerate(ns)]
    return (f"At {ns[0]:,} agencies Experiment A ships in {a[ns[0]]} of {seeds} simulated seeds; " + "; ".join(f"at {n:,}, {a[n]}" for n in ns[1:]) +
            ". The dataset was enlarged from the brief's about 1,500 agencies so the 20% ship rule could be powered; in a real launch the number of agencies is the binding constraint on what can be proven.")
