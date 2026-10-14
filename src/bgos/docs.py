"""Generated documentation: DATA_DICTIONARY.md (from schema metadata), STRATEGY_MEMO.md and LOOM_SCRIPT.md
(numbers pulled from the generated outputs, never typed by hand). All data is SYNTHETIC."""
from __future__ import annotations

from pathlib import Path

import json

import pandas as pd

import config
from . import metrics, schema
from .funnel import STAGES

DISCLAIMER = "Synthetic data. Demonstrates the method, not Hedge's actual performance."


# ----------------------------------------------------------------------------------------------
# DATA DICTIONARY
# ----------------------------------------------------------------------------------------------
def build_data_dictionary() -> str:
    L = ["# Data Dictionary", "",
         f"> {DISCLAIMER} Generated from `src/bgos/schema.py` by `make docs`; do not edit by hand.", "",
         "## Funnel stages", "", "| # | Stage | Definition |", "|---|---|---|"]
    L += [f"| {s.order} | {s.name} | {s.definition} |" for s in STAGES]
    L += ["", "## Tables (SQLite, foreign keys on)", ""]
    for table, meta in schema.TABLES.items():
        L += [f"### `{table}`", "", meta["description"], "", "| Column | Type | Description | Constraints |", "|---|---|---|---|"]
        for name, typ, desc, cons in meta["columns"]:
            L.append(f"| `{name}` | {typ} | {desc} | {cons or ''} |")
        for c in meta.get("constraints", []):
            L.append(f"| _table constraint_ | | `{c}` | |")
        L.append("")
    L += ["## Metric marts (`data/marts/*.csv`, one per SQL file in `sql/`)", "", "| Mart | SQL file | Description |", "|---|---|---|"]
    L += [f"| `{m.name}` | `sql/{m.sql_file}` | {m.description} |" for m in metrics.REGISTRY.values()]
    L += ["", "## Raw files and injected defects", "",
          "`data/raw/*.csv` mirror the tables above but are deliberately dirty. `data/raw/injected_defects.json` lists every injected defect "
          "(counts by type, affected ids, and the planted experiment effects). The cleaning stage never reads it.", "",
          "| Defect type | Cleaning rule |", "|---|---|",
          "| duplicate_agencies | state-blocked fuzzy name match, earliest record wins, children remapped |",
          "| missing_state / missing_size | flagged (`state_missing`, `size_imputed`); size imputed with specialty median |",
          "| mixed_size_formats | parsed to integer (range -> floor midpoint) |",
          "| inconsistent_source_labels | explicit mapping table to canonical sources |",
          "| bind_rate_over_100 | value nullified, logged in quarantine.csv |",
          "| negative_turnaround | repaired from timestamps |",
          "| quote_before_submission / bound_before_quote | row quarantined |",
          "| tiny-n sources | kept; rates suppressed when n < %d |" % config.MIN_N, ""]
    return "\n".join(L)


# ----------------------------------------------------------------------------------------------
# FACTS (every number in the memo/loom comes from here)
# ----------------------------------------------------------------------------------------------
def _n(x) -> str:
    return f"{int(round(x)):,}"


def _p(x, d=0) -> str:
    return f"{x * 100:.{d}f}%"


def memo_facts(root: Path | str | None = None) -> dict[str, str]:
    paths = config.get_paths(root)
    m = lambda name: pd.read_csv(paths.marts / f"{name}.csv")
    f = m("funnel_counts").set_index("stage")
    ranked = pd.read_csv(paths.marts / "ranked_accounts.csv")
    hold = pd.read_csv(paths.marts / "tier_holdout.csv")
    tiers = ranked.tier.value_counts()
    act = m("activation_rate").set_index("cohort").loc["ALL"]
    sq = m("source_quality")
    ok = sq[sq.suppressed == 0].dropna(subset=["bind_rate_per_lead"])
    best, worst = ok.loc[ok.bind_rate_per_lead.idxmax()], ok.loc[ok.bind_rate_per_lead.idxmin()]
    leads = ok.leads.sum()
    ex = m("experiment_results").set_index("experiment_id")
    ttq = m("time_to_quote")
    med = ttq[(ttq.scope == "all_submissions") & (ttq.dimension == "overall")].iloc[0].median_hours
    sweep = json.loads((config.ROOT / "docs" / "seed_sweep.json").read_text())["summary"]
    d = {
        "n_seeds": str(sweep["n_seeds"]),
        "a_ship": str(sweep["A"]["decisions"].get("SHIP", 0)), "b_ship": str(sweep["B"]["decisions"].get("SHIP", 0)),
        "c_sig": str(sweep["C"]["significant_p_lt_0.05"]),
        "raw": _n(f.loc["raw_lead", "agencies"]), "icp": _n(f.loc["icp_qualified", "agencies"]),
        "icp_pct": _p(f.loc["icp_qualified", "mature_cumulative_conversion"]),
        "engaged": _n(f.loc["engaged", "agencies"]), "first_sub": _n(f.loc["first_submission", "agencies"]),
        "bound": _n(f.loc["bound", "agencies"]), "bound_pct": _p(f.loc["bound", "mature_cumulative_conversion"], 1),
        "bound_obs_pct": _p(f.loc["bound", "observed_cumulative_conversion"], 1),
        "repeat": _n(f.loc["repeat_submission", "agencies"]),
        "tier1": _n(tiers.get("Tier 1", 0)), "tier2": _n(tiers.get("Tier 2", 0)), "react": _n(tiers.get("Reactivation", 0)),
        "active": _n(tiers.get("Active", 0)), "hold_t1": _p(hold.set_index("tier").loc["Tier 1", "rate"]), "hold_t3": _p(hold.set_index("tier").loc["Tier 3", "rate"]),
        "act_rate": _p(act.activation_rate),
        "act_gain": _n(0.10 * f.loc["engaged", "agencies"]),
        "worst_src": str(worst.lead_source), "worst_share": _p(worst.leads / leads), "worst_rate": _p(worst.bind_rate_per_lead, 1),
        "best_src": str(best.lead_source), "best_rate": _p(best.bind_rate_per_lead, 1),
        "src_ratio": f"{best.bind_rate_per_lead / worst.bind_rate_per_lead:.1f}x",
        "src_gain": _n(0.10 * leads * (best.bind_rate_per_lead - worst.bind_rate_per_lead)),
        "ttq": f"{med:.0f}",
        "a_lift": f"{ex.loc['A', 'rel_lift'] * 100:+.1f}%", "a_lo": f"{ex.loc['A', 'rel_ci_low'] * 100:+.1f}%",
        "a_hi": f"{ex.loc['A', 'rel_ci_high'] * 100:+.1f}%", "a_dec": str(ex.loc["A", "decision"]),
        "b_dec": str(ex.loc["B", "decision"]), "b_lift": f"{ex.loc['B', 'rel_lift'] * 100:+.1f}%",
        "b_n_have": _n(min(ex.loc["B", "n_control"], ex.loc["B", "n_treatment"])), "b_n_need": _n(ex.loc["B", "n_required_per_arm"]),
        "c_dec": str(ex.loc["C", "decision"]),
    }
    return d


STATIC_NUMBERS = {"1", "2", "3", "7", "10", "14", "30", "31", "60", "61", "90", "95", "5"}


def build_memo(facts: dict[str, str]) -> str:
    return f"""# Strategy Memo: Broker Growth OS

> {DISCLAIMER} Every number below comes from the generated synthetic outputs.

**Growth thesis.** A specialty wholesaler grows by turning more agencies into repeat submitters, not by sending more email. Our north star is weekly qualified submissions from active agencies; every lever is judged by downstream bind and repeat, never by sends or connections.

**Funnel.** Raw lead, ICP-qualified, Engaged, First submission (complete, underwriting-ready), Quoted, Bound, Repeat (another complete submission within 90 days of bind). Synthetic baseline: {facts['raw']} leads, {facts['icp']} ICP-qualified ({facts['icp_pct']}), {facts['engaged']} engaged, {facts['first_sub']} first submissions, {facts['bound']} bound, {facts['repeat']} repeat. Counting only leads old enough to have converted, {facts['bound_pct']} reach a bind ({facts['bound_obs_pct']} raw, which understates it). The funnel is deliberately generous so Experiment A can be powered; real rates will be lower.

**ICP.** Commercial lines with E&S or specialty exposure and at least 3 producers. A transparent fit score ranks every agency: {facts['active']} are active customers to expand, {facts['react']} dormant to reactivate, and among prospects {facts['tier1']} are Tier 1 (immediate outbound) and {facts['tier2']} Tier 2 (nurture). Scored 90 days before the as-of date using only data available then, Tier 1 prospects converted at {facts['hold_t1']} versus {facts['hold_t3']} for Tier 3. On synthetic data this checks plumbing, not real predictive power.

**Two highest-leverage gaps (synthetic baseline).**
1. Activation: only {facts['act_rate']} of engaged agencies send a complete submission within 14 days. Each +10 points adds about {facts['act_gain']} first submissions on this book.
2. Source mix: {facts['worst_src']} supplies {facts['worst_share']} of leads but binds {facts['worst_rate']} of them, versus {facts['best_rate']} for {facts['best_src']} ({facts['src_ratio']}). Moving 10% of lead volume to {facts['best_src']}-quality sources adds roughly {facts['src_gain']} bound agencies (back-of-envelope; assumes that channel scales).

Watch metric: median time to quote is {facts['ttq']} hours; protect it while volume grows.

**90-day plan.**
- Days 1-30, establish truth: join CRM and submission data at agency level, lock stage definitions, deduplicate, baseline every metric with minimum-n rules.
- Days 31-60, ship experiments: ICP-targeted outbound, submission-ready onboarding, and reactivation versus a holdout, each with a pre-registered effect size, sample size and decision rule.
- Days 61-90, prove lift: ship only what clears its rule. In simulation, ICP targeting returned {facts['a_dec']} ({facts['a_lift']}, 95% CI {facts['a_lo']} to {facts['a_hi']}), onboarding was {facts['b_dec']} (underpowered: {facts['b_n_have']} per arm versus {facts['b_n_need']} needed), reactivation was {facts['c_dec']}. This is one simulated draw: across {facts['n_seeds']} simulated seeds, A ships in {facts['a_ship']}, B in {facts['b_ship']}, and C shows a spurious significant result in {facts['c_sig']}. Running three experiments at once raises false-positive risk (multiple comparisons); a real programme would pre-register one primary. Real baselines will differ.

**Assumptions to validate in the first 30 days** (about Hedge, from its public positioning as an AI-native specialty insurer serving brokers; none confirmed):
- Brokers are the main growth channel and a complete submission is the activation event.
- Submission completeness is a real bottleneck to fast quotes.
- The ICP's E&S and specialty appetite matches carrier appetite.
- Agency-level history can be joined across CRM and underwriting systems.
- A 60-day silence is the right dormancy threshold.
"""


def build_loom(facts: dict[str, str]) -> str:
    return f"""# Loom Script (5-8 minutes)

> {DISCLAIMER} Say this in the first ten seconds and keep the dashboard banner visible.

## Do these yourself before recording
- [ ] Run `make setup && make all && make test`; confirm everything is green on your machine.
- [ ] Open `make dashboard` and click through every view once so nothing loads for the first time on camera.
- [ ] Re-read the numbers you will quote against the dashboard; they come from a synthetic dataset. Never present them as Hedge's.
- [ ] Decide what you will NOT claim: no real conversion rates, customers, carriers, funding or headcount for Hedge.
- [ ] Keep the "Assumptions to validate" list from `STRATEGY_MEMO.md` handy for the close.

## Timeline

| Time | Screen / click | Say |
|---|---|---|
| 0:00-0:30 | Dashboard, banner visible | "This is a growth-ops prototype for an AI-native specialty wholesaler. Everything is synthetic: it demonstrates how I would measure and run the broker funnel, not Hedge's real performance." |
| 0:30-1:30 | `src/bgos/funnel.py`, then the Monday Morning view | "I encoded the funnel as code: lead, ICP, engaged, first complete submission, quoted, bound, repeat. In the synthetic baseline {facts['raw']} leads become {facts['bound']} bound agencies ({facts['bound_pct']}). Stages are strictly nested so the funnel can only taper." |
| 1:30-2:30 | `outputs/data_quality_report.md` | "The raw data is deliberately dirty: duplicates, mixed source labels, impossible dates. Every defect is injected and counted, and cleaning reconciles to the exact injected counts. Tiny sources that show 100% are suppressed, not celebrated." |
| 2:30-3:30 | Ranked Accounts view | "The fit score is a transparent weighted sum, and every row says why. {facts['tier1']} Tier 1 accounts, {facts['react']} dormant ones to win back. The tier ordering check is a plumbing test: the generator makes conversion depend on fit, so I do not call it predictive." |
| 3:30-4:30 | Weekly Growth Review, then Source Quality | "North star is qualified submissions from active agencies. Source quality is judged on bind, not lead count: {facts['worst_src']} gives the volume but {facts['best_src']} binds {facts['src_ratio']} better. Activation is {facts['act_rate']} within 14 days, the first gap I would attack." |
| 4:30-5:30 | Experiments view | "Three experiments with pre-registered rules. ICP targeting: {facts['a_dec']} on a simulated {facts['a_lift']} lift. Onboarding looks positive but is underpowered, so the framework says {facts['b_dec']}, not ship. Say plainly that this is one simulated draw: across {facts['n_seeds']} seeds A ships in {facts['a_ship']}. Reactivation is a planted null and returns {facts['c_dec']}. These are simulated results that demonstrate the method." |
| 5:30-6:30 | `outputs/ai_demo.md` | "The AI layer is human-in-the-loop: research, a deterministic submission-quality score, next-best-action, and email first lines. Drafts always require review and there is no send function anywhere in the code." |
| 6:30-7:30 | `STRATEGY_MEMO.md` | "First 30 days: establish truth. Join the real CRM and submission data, validate these assumptions about Hedge, lock definitions, baseline every metric. Days 31-60 ship the three experiments; days 61-90 prove lift." |

## Close
"I would start by validating the assumptions on the last page against real data, because everything here is only as good as those definitions."
"""


def run_docs(root: Path | str | None = None) -> None:
    paths = config.get_paths(root)
    facts = memo_facts(root)
    (paths.root / "DATA_DICTIONARY.md").write_text(build_data_dictionary())
    (paths.root / "STRATEGY_MEMO.md").write_text(build_memo(facts))
    (paths.root / "LOOM_SCRIPT.md").write_text(build_loom(facts))
    from . import site
    site.run_site(root)  # docs/index.html for GitHub Pages (needs the memo written above)
