"""Transparent Broker Fit Score, tiers, and next actions.

Broker Fit Score = 0.30 Specialty Fit + 0.25 Commercial Volume + 0.20 E&S Activity
                 + 0.15 Engagement + 0.10 Geographic Priority      (weights in config.SCORING_WEIGHTS)

Every component is normalized to [0, 1]; formulas are in the function docstrings below.
All data is synthetic; the tier sanity check validates plumbing, NOT predictive power.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

import config
from .rounding import round_df
from . import funnel

COMPONENTS = list(config.SCORING_WEIGHTS)
COMPONENT_LABEL = {"specialty_fit": "specialty fit", "commercial_volume": "commercial volume",
                   "es_activity": "E&S activity", "engagement": "engagement",
                   "geographic_priority": "geographic priority"}

TIERS = ("Reactivation", "Active", "Tier 1", "Tier 2", "Tier 3")

#: Single rule table: (tier, stage) -> action category. Shared with ai/next_best_action.py.
ACTION_TEXT = {
    "outbound": "Outbound: personalized first touch via the ICP-targeted sequence",
    "onboarding": "Onboarding: send the submission-ready checklist and book a submission walkthrough",
    "reactivation": "Reactivation: win-back note with a market update and new appetite",
    "expansion": "Expansion: ask for the next submission in an adjacent line of business",
    "monitor": "Monitor: no outreach now; re-score in 30 days",
    "nurture": "Nurture: add to the low-touch nurture sequence (monthly market note); re-score when they engage",
}
_PRE_ENGAGED = {"raw_lead", "icp_qualified"}
_POST_SUBMISSION = {"first_submission", "quoted", "bound", "repeat_submission"}


def recommend_action(tier: str, stage: str) -> str:
    """Action category from tier and highest funnel stage reached (see DECISIONS.md D8/D18/D38).

    Reactivation -> reactivation; Active customer -> expansion; Tier 3 -> monitor;
    Tier 1: not yet engaged -> outbound, engaged -> onboarding; Tier 2: not yet engaged -> nurture, engaged -> onboarding.
    (Tier 1/2 agencies with a submission would be Active or Reactivation; the fallback is defensive.)"""
    if tier == "Reactivation":
        return "reactivation"
    if tier == "Active":
        return "expansion"
    if tier == "Tier 3":
        return "monitor"
    if stage in _PRE_ENGAGED:
        return "outbound" if tier == "Tier 1" else "nurture"
    if stage == "engaged":
        return "onboarding"
    return "expansion"


def specialty_fit(agencies: pd.DataFrame) -> pd.Series:
    """0.6 * specialty weight of the agency's focus (config.SPECIALTY_WEIGHTS)
    + 0.4 * min(1, hard-to-place lines written / config.HARD_LINES_CAP)."""
    w = agencies["specialty_focus"].map(config.SPECIALTY_WEIGHTS).fillna(0.0)
    hard = agencies["commercial_lines"].fillna("").map(
        lambda s: sum(1 for l in str(s).split("|") if l in config.HARD_TO_PLACE_LINES))
    return (0.6 * w + 0.4 * np.minimum(1.0, hard / config.HARD_LINES_CAP)).clip(0, 1)


def commercial_volume(agencies: pd.DataFrame) -> pd.Series:
    """0.6 * min(1, ln(1+producers)/ln(1+VOLUME_PRODUCER_CAP)) + 0.4 * min(1, commercial lines/VOLUME_LINES_CAP)."""
    prod = pd.to_numeric(agencies["size_producers"], errors="coerce").fillna(0).clip(lower=0)
    nlines = agencies["commercial_lines"].fillna("").map(lambda s: len([l for l in str(s).split("|") if l]))
    return (0.6 * np.minimum(1.0, np.log1p(prod) / math.log1p(config.VOLUME_PRODUCER_CAP))
            + 0.4 * np.minimum(1.0, nlines / config.VOLUME_LINES_CAP)).clip(0, 1)


def es_activity(agencies: pd.DataFrame) -> pd.Series:
    """0.5 * appetite score (high 1, medium .6, low .25, none 0) + 0.5 * min(1, prior-year E&S submissions/ES_SUBMISSIONS_CAP)."""
    app = agencies["es_appetite"].map(config.ES_APPETITE_SCORES).fillna(0.0)
    subs = pd.to_numeric(agencies["es_submissions_py"], errors="coerce").fillna(0)
    return (0.5 * app + 0.5 * np.minimum(1.0, subs / config.ES_SUBMISSIONS_CAP)).clip(0, 1)


def geographic_priority(agencies: pd.DataFrame) -> pd.Series:
    """Priority state 1.0, secondary state 0.6, other 0.3, unknown 0.0 (config.GEO_SCORES)."""
    def f(s):
        s = str(s).upper()
        if s in config.PRIORITY_STATES: return config.GEO_SCORES["priority"]
        if s in config.SECONDARY_STATES: return config.GEO_SCORES["secondary"]
        if s in ("UNK", "", "NAN"): return config.GEO_SCORES["unknown"]
        return config.GEO_SCORES["other"]
    return agencies["state"].map(f).astype(float)


def engagement(agencies: pd.DataFrame, touches: pd.DataFrame, submissions: pd.DataFrame | None, as_of) -> pd.Series:
    """1 - exp(-points / ENGAGEMENT_SATURATION_POINTS), points = sum over engagement touches of
    config.ENGAGEMENT_TOUCH_POINTS[type] * 0.5 ** (age_days / ENGAGEMENT_HALF_LIFE_DAYS).
    Engagement events: opens, clicks, replies, meetings. Sends are NOT engagement, and neither are SUBMISSIONS:
    counting them leaked the validation outcome into the score (audit B-17). `submissions` is accepted only so the
    signature stays stable; it is ignored."""
    as_of = pd.Timestamp(as_of).normalize()
    ev = touches[touches["touch_type"].isin(config.ENGAGEMENT_TOUCH_POINTS)][["agency_id", "touched_at", "touch_type"]]
    out = pd.Series(0.0, index=agencies["agency_id"])
    if len(ev):
        age = (as_of - pd.to_datetime(ev["touched_at"]).dt.normalize()).dt.days.clip(lower=0)
        pts = ev["touch_type"].map(config.ENGAGEMENT_TOUCH_POINTS) * 0.5 ** (age / config.ENGAGEMENT_HALF_LIFE_DAYS)
        tot = pts.groupby(ev["agency_id"]).sum()
        idx = tot.index.intersection(out.index)
        out.loc[idx] = tot.reindex(idx).to_numpy()
    return (1 - np.exp(-out / config.ENGAGEMENT_SATURATION_POINTS)).clip(0, 1)


def assign_tier(*, specialty: float, es: float, eng: float, score: float, is_icp: bool,
                n_complete_subs: int, days_since_last_sub: float | None) -> str:
    """Tier precedence (first match wins):
    1. Reactivation: >= 1 complete submission AND last one >= DORMANCY_DAYS ago.
    2. Active: >= 1 complete submission AND last one < DORMANCY_DAYS ago (an existing customer: expand, do not prospect).
    3. Tier 1 (immediate outbound): ICP AND specialty >= .70 AND E&S activity >= .50 AND engagement >= .40.
    4. Tier 2 (nurture): ICP AND score >= .45.
    5. Tier 3 (monitor): everything else.
    Tiers 1-3 therefore contain PROSPECTS only (no complete submission yet)."""
    th = config.TIER_THRESHOLDS
    if n_complete_subs >= 1 and days_since_last_sub is not None:
        return "Reactivation" if days_since_last_sub >= config.DORMANCY_DAYS else "Active"
    if is_icp and specialty >= th["tier1_specialty_fit"] and es >= th["tier1_es_activity"] and eng >= th["tier1_engagement"]:
        return "Tier 1"
    if is_icp and score >= th["tier2_score"]:
        return "Tier 2"
    return "Tier 3"


def score_agencies(agencies: pd.DataFrame, touches: pd.DataFrame, submissions: pd.DataFrame,
                   as_of=None) -> pd.DataFrame:
    """Components, score, tier and stage for every agency (one row each)."""
    as_of = pd.Timestamp(as_of or config.AS_OF).normalize()
    horizon = as_of + pd.Timedelta(days=1)  # point-in-time: nothing after the as-of date may influence the score
    touches = touches[pd.to_datetime(touches["touched_at"]) < horizon]
    submissions = submissions[pd.to_datetime(submissions["submitted_at"]) < horizon]
    df = agencies[pd.to_datetime(agencies["first_touch_date"]) < horizon].copy().reset_index(drop=True)
    df["specialty_fit"] = specialty_fit(df).to_numpy()
    df["commercial_volume"] = commercial_volume(df).to_numpy()
    df["es_activity"] = es_activity(df).to_numpy()
    df["geographic_priority"] = geographic_priority(df).to_numpy()
    df["engagement"] = engagement(df, touches, submissions, as_of).reindex(df["agency_id"]).to_numpy()
    df["score"] = sum(config.SCORING_WEIGHTS[c] * df[c] for c in COMPONENTS)
    comp = submissions[submissions["is_complete"].astype(bool)].copy()
    comp["d"] = pd.to_datetime(comp["submitted_at"]).dt.normalize()
    last = comp.groupby("agency_id")["d"].max()
    cnt = comp.groupby("agency_id").size()
    df["n_complete_subs"] = cnt.reindex(df["agency_id"]).fillna(0).astype(int).to_numpy()
    last_dt = pd.to_datetime(pd.Series(last.reindex(df["agency_id"]).to_numpy()), errors="coerce")
    df["days_since_last_sub"] = (as_of - last_dt).dt.days.astype(float)
    ev = funnel.derive_stage_events(df.assign(is_icp=df["is_icp"].astype(int)), touches, submissions)
    top = ev.sort_values("stage_order").groupby("agency_id")["stage"].last()
    df["stage"] = pd.Series(top.reindex(df["agency_id"]).to_numpy()).fillna("raw_lead").to_numpy()
    df["tier"] = [assign_tier(specialty=r.specialty_fit, es=r.es_activity, eng=r.engagement, score=r.score,
                              is_icp=bool(r.is_icp), n_complete_subs=r.n_complete_subs,
                              days_since_last_sub=None if pd.isna(r.days_since_last_sub) else float(r.days_since_last_sub))
                  for r in df.itertuples()]
    return df


def reason_text(row) -> str:
    contrib = sorted(((config.SCORING_WEIGHTS[c] * row[c], c) for c in COMPONENTS), reverse=True)[:2]
    parts = ", ".join(f"{COMPONENT_LABEL[c]} {row[c]:.2f}" for _, c in contrib)
    extra = ""
    if row["tier"] in ("Reactivation", "Active"):
        extra = f"; last complete submission {int(row['days_since_last_sub'])} days ago"
    return f"{row['tier']} (score {row['score']:.2f}): top drivers {parts}{extra}"


def channel_for(action: str, source: str) -> str:
    if action == "outbound":
        return "linkedin" if source == "linkedin" else "email"
    return {"onboarding": "call", "reactivation": "email", "expansion": "call", "monitor": "email-nurture", "nurture": "email-nurture"}[action]


def rank_accounts(scored: pd.DataFrame) -> pd.DataFrame:
    df = scored.copy()
    df["action"] = [recommend_action(t, s) for t, s in zip(df["tier"], df["stage"])]
    df["next_action"] = df["action"].map(ACTION_TEXT)
    df["channel"] = [channel_for(a, s) for a, s in zip(df["action"], df["lead_source"])]
    df["score"] = df["score"].round(4)
    for c in COMPONENTS:
        df[c] = df[c].round(4)
    df["reason"] = df.apply(reason_text, axis=1)
    cols = ["agency_id", "name", "score", "tier", "next_action", "owner", "channel", "reason"] + COMPONENTS + \
           ["stage", "action", "lead_source", "specialty_focus", "state", "is_icp", "days_since_last_sub"]
    return df[cols].sort_values(["score", "agency_id"], ascending=[False, True]).reset_index(drop=True)


def holdout_conversion_by_tier(agencies: pd.DataFrame, touches: pd.DataFrame, submissions: pd.DataFrame,
                               as_of=None, horizon_days: int | None = None) -> pd.DataFrame:
    """Out-of-sample tier check. Score PROSPECTS (in the funnel, no complete submission yet) as of
    (as_of - horizon) using only data available then, then count first complete submissions in the following horizon.
    The score never sees the outcome window. On synthetic data this still validates plumbing, not real predictive power,
    because the generator makes conversion depend on fit and engagement."""
    as_of = pd.Timestamp(as_of or config.AS_OF).normalize()
    horizon_days = horizon_days or config.HOLDOUT_DAYS
    cutoff = as_of - pd.Timedelta(days=horizon_days)
    comp = submissions[submissions["is_complete"].astype(bool)].copy()
    comp["d"] = pd.to_datetime(comp["submitted_at"]).dt.normalize()
    already = set(comp.loc[comp["d"] <= cutoff, "agency_id"])
    pool = agencies[(pd.to_datetime(agencies["first_touch_date"]) <= cutoff) & ~agencies["agency_id"].isin(already)]
    scored = score_agencies(pool, touches, submissions, cutoff)
    won = set(comp.loc[(comp["d"] > cutoff) & (comp["d"] <= as_of), "agency_id"])
    scored["converted"] = scored["agency_id"].isin(won)
    g = scored.groupby("tier")["converted"].agg(["sum", "count"]).reindex(["Tier 1", "Tier 2", "Tier 3"]).fillna(0)
    out = pd.DataFrame({"tier": g.index, "prospects": g["count"].astype(int).to_numpy(), "converted": g["sum"].astype(int).to_numpy()})
    out["rate"] = (out["converted"] / out["prospects"].replace(0, np.nan)).where(out["prospects"] >= config.MIN_N)
    out["scored_as_of"] = cutoff.date().isoformat()
    out["window_days"] = horizon_days
    return out


def run_score(root: Path | str | None = None) -> pd.DataFrame:
    import sqlite3
    paths = config.get_paths(root).ensure()
    ag = pd.read_csv(paths.clean / "agencies.csv")
    tc = pd.read_csv(paths.clean / "touches.csv")
    sb = pd.read_csv(paths.clean / "submissions.csv")
    ranked = rank_accounts(score_agencies(ag, tc, sb, config.AS_OF))
    round_df(holdout_conversion_by_tier(ag, tc, sb, config.AS_OF)).to_csv(paths.marts / "tier_holdout.csv", index=False)
    round_df(ranked).to_csv(paths.outputs / "ranked_accounts.csv", index=False)
    round_df(ranked).to_csv(paths.marts / "ranked_accounts.csv", index=False)
    conn = sqlite3.connect(paths.db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM ranked_accounts")
    from . import schema
    cols = schema.column_names("ranked_accounts")
    ranked[cols].to_sql("ranked_accounts", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()
    return ranked
