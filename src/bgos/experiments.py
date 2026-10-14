"""Experiment framework: config, sample size, z-test, CIs, power, SRM check, SHIP/ITERATE/INCONCLUSIVE.

IMPORTANT: every result produced from the generated dataset is a SIMULATED result that demonstrates the method.
The generator plants known effects (A +30%, B +15%, C 0) so tests can check the pipeline recovers them.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import config
from .rounding import round_df

SIM_NOTE = "SIMULATED RESULT on synthetic data; demonstrates the method, not real performance."
SHIP, ITERATE, INCONCLUSIVE = "SHIP", "ITERATE", "INCONCLUSIVE"


@dataclass(frozen=True)
class ExperimentConfig:
    experiment_id: str
    name: str
    hypothesis: str
    control: str
    treatment: str
    primary_metric: str
    secondary_metrics: tuple[str, ...]
    alpha: float
    mde_relative: float          # pre-registered minimum detectable relative lift used for sample-size planning
    ship_min_relative_lift: float
    decision_rule: str
    population: str
    force_iterate_if_not_ship: bool = False  # Experiment A: "otherwise ITERATE the ICP definition"
    power: float = 0.80

    def __post_init__(self):
        # Size the test for the SMALLEST effect we would act on. Sizing for a bigger effect than the ship threshold
        # (the original A: sized for +30%, shipped at +20%) makes "sample size reached" misleading (audit B-19).
        if abs(self.mde_relative - self.ship_min_relative_lift) > 1e-12:
            raise ValueError(f"{self.experiment_id}: mde_relative must equal ship_min_relative_lift")


EXPERIMENTS: dict[str, ExperimentConfig] = {
    "A": ExperimentConfig(
        "A", "ICP-targeted outbound",
        "The ICP-targeted v2 outbound sequence lifts first-submission conversion by at least 20% relative versus the standard v1 sequence (all agencies are enrolled in one or the other; non-ICP agencies dilute the effect).",
        "Standard v1 outbound sequence", "ICP-Targeted v2 outbound sequence",
        f"first complete submission within {config.A_OUTCOME_DAYS} days of first touch",
        ("engaged rate", "quote rate of submitters", "bind rate per lead"),
        config.EXPERIMENT_ALPHA, 0.20, 0.20,
        "SHIP only if relative lift >= 20% AND p < alpha AND required sample size reached; otherwise ITERATE the ICP definition.",
        "All enrolled agencies, randomized 50/50 (stratified) at first touch; only units with a full follow-up window are analyzed. Sized for the 20% ship threshold, not for the planted effect.",
        force_iterate_if_not_ship=True),
    "B": ExperimentConfig(
        "B", "Submission-ready onboarding",
        "A submission-ready onboarding kit (checklist + walkthrough) raises the 14-day submission rate by ~15% relative.",
        "Standard onboarding", "Submission-ready onboarding",
        f"complete submission within {config.B_OUTCOME_DAYS} days of engagement",
        ("share of first submissions that are complete", "median time to first submission"),
        config.EXPERIMENT_ALPHA, 0.10, 0.10,
        "SHIP if relative lift >= 10% AND p < alpha AND required sample reached; ITERATE if significant but small, or powered null; INCONCLUSIVE if underpowered and not significant.",
        "Engaged ICP agencies, randomized 50/50 at engagement."),
    "C": ExperimentConfig(
        "C", "Reactivation outreach",
        "A reactivation sequence brings dormant agencies back to submitting versus doing nothing.",
        "No-outreach holdout", "Reactivation outreach sequence",
        f"complete submission within {config.C_OUTCOME_DAYS} days after the reactivation date",
        ("reply rate", "meeting rate"),
        config.EXPERIMENT_ALPHA, 0.25, 0.25,
        "SHIP if relative lift >= 25% AND p < alpha AND required sample reached; ITERATE if significant but small, or powered null; INCONCLUSIVE if underpowered and not significant.",
        f"Agencies with a complete submission and none in the {config.DORMANCY_DAYS} days before {config.REACTIVATION_T0}; 50/50 vs holdout."),
}


# ----------------------------------------------------------------------------------------------
# statistics
# ----------------------------------------------------------------------------------------------
def fmt_p(p: float) -> str:
    """p-value for display: never print 0.000."""
    return "< 0.001" if p < 0.001 else f"= {p:.3f}"


def sample_size_two_proportions(p1: float, p2: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """Per-arm n for a two-sided two-proportion z-test (pooled variance under H0), rounded up."""
    if not (0 < p1 < 1 and 0 < p2 < 1) or p1 == p2:
        raise ValueError("p1 and p2 must be in (0,1) and different")
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    pbar = (p1 + p2) / 2
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return int(math.ceil(num / (p1 - p2) ** 2))


def two_proportion_ztest(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    """Pooled two-sided z-test of H0: p1 == p2. Returns (z, p). z > 0 means arm 2 (treatment) is higher."""
    p1, p2, pp = x1 / n1, x2 / n2, (x1 + x2) / (n1 + n2)
    se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p2 - p1) / se
    return z, float(2 * stats.norm.sf(abs(z)))


def lift_confidence_intervals(x1: int, n1: int, x2: int, n2: int, alpha: float = 0.05) -> dict:
    """Absolute lift (Wald, unpooled) and relative lift (Katz log-ratio) confidence intervals."""
    z = stats.norm.ppf(1 - alpha / 2)
    p1, p2 = x1 / n1, x2 / n2
    d = p2 - p1
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    out = {"abs_lift": d, "abs_ci_low": d - z * se, "abs_ci_high": d + z * se}
    if x1 > 0 and x2 > 0:
        rr = p2 / p1
        se_log = math.sqrt((1 - p2) / x2 + (1 - p1) / x1)
        out.update(rel_lift=rr - 1, rel_ci_low=math.exp(math.log(rr) - z * se_log) - 1,
                   rel_ci_high=math.exp(math.log(rr) + z * se_log) - 1)
    else:
        out.update(rel_lift=float("nan"), rel_ci_low=float("nan"), rel_ci_high=float("nan"))
    return out


def achieved_power(p1: float, p2: float, n1: int, n2: int, alpha: float = 0.05) -> float:
    """Power of the two-sided two-proportion z-test to detect (p1, p2) with n1, n2 (normal approximation)."""
    if p1 == p2:
        return alpha
    za = stats.norm.ppf(1 - alpha / 2)
    pbar = (n1 * p1 + n2 * p2) / (n1 + n2)
    se0 = math.sqrt(pbar * (1 - pbar) * (1 / n1 + 1 / n2))
    se1 = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    d = abs(p2 - p1)
    return float(stats.norm.sf((za * se0 - d) / se1) + stats.norm.cdf((-za * se0 - d) / se1))


def srm_check(n_control: int, n_treatment: int, expected_ratio: float = 0.5, threshold: float = 0.001) -> dict:
    """Sample-ratio-mismatch chi-square goodness-of-fit test on assignment counts."""
    total = n_control + n_treatment
    exp = [total * (1 - expected_ratio), total * expected_ratio]
    chi2, p = stats.chisquare([n_control, n_treatment], f_exp=exp)
    return {"chi2": float(chi2), "p_value": float(p), "flag": bool(p < threshold)}


LIFT_TOL = 1e-9  # IEEE guard: a lift of exactly 20% computes as 0.19999999999999996


def is_sample_size_reached(n_control: int, n_treatment: int, n_required: int) -> bool:
    """The SMALLER arm must meet the per-arm requirement (inclusive)."""
    return min(n_control, n_treatment) >= n_required


def decide(*, rel_lift: float, p_value: float, sample_size_reached: bool, srm_flag: bool, cfg: ExperimentConfig) -> str:
    """SHIP / ITERATE / INCONCLUSIVE.

    * SRM flagged -> INCONCLUSIVE (assignment is broken; the test is invalid).
    * SHIP: p < alpha AND rel_lift >= ship_min_relative_lift AND required sample size reached.
    * Experiment A (force_iterate_if_not_ship): anything else -> ITERATE the ICP definition.
    * Otherwise: ITERATE if the test is significant (but small/negative) or powered with no effect;
      INCONCLUSIVE if underpowered and not significant (do not iterate on noise).
    """
    if srm_flag:
        return INCONCLUSIVE
    if (p_value < cfg.alpha and not math.isnan(rel_lift) and rel_lift + LIFT_TOL >= cfg.ship_min_relative_lift
            and sample_size_reached):
        return SHIP
    if cfg.force_iterate_if_not_ship:
        return ITERATE
    if p_value < cfg.alpha:
        return ITERATE
    if sample_size_reached:
        return ITERATE
    return INCONCLUSIVE


# ----------------------------------------------------------------------------------------------
# analysis
# ----------------------------------------------------------------------------------------------
@dataclass
class ExperimentResult:
    experiment_id: str
    name: str
    n_assigned_control: int
    n_assigned_treatment: int
    n_control: int
    n_treatment: int
    x_control: int
    x_treatment: int
    rate_control: float
    rate_treatment: float
    abs_lift: float
    abs_ci_low: float
    abs_ci_high: float
    rel_lift: float
    rel_ci_low: float
    rel_ci_high: float
    z: float
    p_value: float
    alpha: float
    mde_relative: float
    n_required_per_arm: int
    sample_size_reached: bool
    power_at_mde: float
    ci_low_clears_ship: bool
    srm_p_value: float
    srm_flag: bool
    decision: str
    rationale: str
    note: str = SIM_NOTE
    planted_true_lift: float = float("nan")


def analyze_experiment(outcomes: pd.DataFrame, cfg: ExperimentConfig) -> ExperimentResult:
    """outcomes: rows for ONE experiment with columns arm, mature, outcome."""
    assigned = outcomes.groupby("arm").size().reindex(["control", "treatment"]).fillna(0).astype(int)
    srm = srm_check(int(assigned["control"]), int(assigned["treatment"]))
    m = outcomes[outcomes["mature"] == 1]
    g = m.groupby("arm")["outcome"].agg(["sum", "count"]).reindex(["control", "treatment"])
    x1, n1, x2, n2 = int(g.loc["control", "sum"]), int(g.loc["control", "count"]), int(g.loc["treatment", "sum"]), int(g.loc["treatment", "count"])
    p1, p2 = x1 / n1, x2 / n2
    z, p = two_proportion_ztest(x1, n1, x2, n2)
    ci = lift_confidence_intervals(x1, n1, x2, n2, cfg.alpha)
    target = min(0.99, p1 * (1 + cfg.mde_relative))
    n_req = sample_size_two_proportions(p1, target, cfg.alpha, cfg.power) if 0 < p1 < 1 else 10 ** 9
    reached = is_sample_size_reached(n1, n2, n_req)
    power = achieved_power(p1, target, n1, n2, cfg.alpha)  # power at the PRE-REGISTERED effect (not post-hoc power)
    decision = decide(rel_lift=ci["rel_lift"], p_value=p, sample_size_reached=reached, srm_flag=srm["flag"], cfg=cfg)
    why = (f"rel lift {ci['rel_lift']:+.1%} (95% CI {ci['rel_ci_low']:+.1%} to {ci['rel_ci_high']:+.1%}), p {fmt_p(p)}; "
           f"n/arm {min(n1, n2)} vs {n_req} required for a {cfg.mde_relative:.0%} lift at baseline {p1:.1%} (power at that lift {power:.0%}); "
           f"{'lower CI bound clears' if ci['rel_ci_low'] >= cfg.ship_min_relative_lift else 'NOTE: lower CI bound is below'} the {cfg.ship_min_relative_lift:.0%} ship threshold (the rule uses the point estimate; winner's-curse risk); "
           f"SRM {'FLAGGED' if srm['flag'] else 'ok'}.")
    return ExperimentResult(
        cfg.experiment_id, cfg.name, int(assigned["control"]), int(assigned["treatment"]), n1, n2, x1, x2, p1, p2,
        ci["abs_lift"], ci["abs_ci_low"], ci["abs_ci_high"], ci["rel_lift"], ci["rel_ci_low"], ci["rel_ci_high"],
        z, p, cfg.alpha, cfg.mde_relative, int(n_req), bool(reached), power, bool(ci["rel_ci_low"] >= cfg.ship_min_relative_lift), srm["p_value"], srm["flag"], decision, why)


def run_experiments(root: Path | str | None = None) -> pd.DataFrame:
    from . import metrics
    paths = config.get_paths(root).ensure()
    conn = metrics.connect(root)
    try:
        outcomes = metrics.run_metric("experiment_outcomes", conn)
    finally:
        conn.close()
    truth = {}
    mp = paths.raw / "injected_defects.json"
    if mp.exists():  # reporting only: shows planted truth next to the estimate; never used for decisions
        gt = json.loads(mp.read_text()).get("ground_truth", {})
        truth = {k: gt.get(f"experiment_{k}", {}).get("true_relative_lift", float("nan")) for k in EXPERIMENTS}
    rows = []
    for k, cfg in EXPERIMENTS.items():
        res = analyze_experiment(outcomes[outcomes.experiment_id == k], cfg)
        res.planted_true_lift = truth.get(k, float("nan"))
        rows.append(asdict(res))
    df = pd.DataFrame(rows)
    round_df(df).to_csv(paths.marts / "experiment_results.csv", index=False)
    write_report(df, paths.outputs / "experiment_results.md")
    return df


def write_report(df: pd.DataFrame, path: Path) -> None:
    lines = ["# Experiment Results", "", f"> **{SIM_NOTE}** The generator plants a +30% lift (A), +15% (B) and 0 (C); "
             "this report shows whether the pipeline recovers them. These are not findings about any real company.", ""]
    for r in df.to_dict("records"):
        cfg = EXPERIMENTS[r["experiment_id"]]
        lines += [f"## Experiment {r['experiment_id']}: {r['name']}", "",
                  f"- Hypothesis: {cfg.hypothesis}",
                  f"- Control: {cfg.control}; Treatment: {cfg.treatment}",
                  f"- Primary metric: {cfg.primary_metric}",
                  f"- Decision rule: {cfg.decision_rule}",
                  f"- Control {r['x_control']}/{r['n_control']} = {r['rate_control']:.1%}; "
                  f"Treatment {r['x_treatment']}/{r['n_treatment']} = {r['rate_treatment']:.1%}",
                  f"- Relative lift {r['rel_lift']:+.1%} (95% CI {r['rel_ci_low']:+.1%} to {r['rel_ci_high']:+.1%}); "
                  f"p {fmt_p(r['p_value'])}; planted truth {r['planted_true_lift']:+.0%}",
                  f"- Sample: {min(r['n_control'], r['n_treatment'])} per arm vs {r['n_required_per_arm']} required "
                  f"(reached: {r['sample_size_reached']}); power at the pre-registered {EXPERIMENTS[r['experiment_id']].mde_relative:.0%} lift {r['power_at_mde']:.0%}; lower CI bound clears the ship threshold: {r['ci_low_clears_ship']}; SRM p = {r['srm_p_value']:.3f}",
                  f"- **Decision: {r['decision']}** (simulated)", ""]
    path.write_text("\n".join(lines))
