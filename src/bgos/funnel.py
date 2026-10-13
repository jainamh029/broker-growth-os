"""The broker funnel, encoded as code (not prose).

Stage order is strict and nested: an agency counts at stage k only if it also
satisfied every earlier stage. That makes the funnel monotonically
non-increasing by construction. Agencies that produce activity without
satisfying the earlier stages (e.g. a submission from a non-ICP agency) are
reported separately as "out-of-funnel", never silently dropped.

All data in this project is synthetic.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

import config


@dataclass(frozen=True)
class Stage:
    key: str
    name: str
    order: int
    definition: str


STAGES: tuple[Stage, ...] = (
    Stage("raw_lead", "Raw Lead", 1,
          "Agency identified via a public source, referral, or inbound request. Entry date = first touch date."),
    Stage("icp_qualified", "ICP-Qualified Agency", 2,
          "Raw lead that writes commercial lines AND has E&S/specialty/hard-to-place exposure "
          "(E&S appetite high/medium OR a target specialty focus) AND has at least "
          f"{config.ICP_MIN_PRODUCERS} producers. Qualification is dated at first touch."),
    Stage("engaged", "Engaged Broker", 3,
          "ICP-qualified agency that opened or clicked an email, replied, booked a meeting/call, "
          "or submitted. Dated at the earliest such event."),
    Stage("first_submission", "First Submission", 4,
          "Engaged agency's first COMPLETE, underwriting-ready submission (all required checklist "
          "fields present). Incomplete submissions do not count."),
    Stage("quoted", "Quoted", 5,
          "First-submission agency with at least one complete submission that received a quote."),
    Stage("bound", "Bound", 6,
          "Quoted agency with at least one submission that was bound."),
    Stage("repeat_submission", "Repeat Submission", 7,
          f"Bound agency that sent another complete submission within {config.REPEAT_WINDOW_DAYS} days "
          "AFTER its first bind (bind-anchored; see DECISIONS.md D6)."),
)

STAGE_KEYS = [s.key for s in STAGES]
STAGE_BY_KEY = {s.key: s for s in STAGES}
STAGE_ORDER = {s.key: s.order for s in STAGES}

#: Touch types that count as "engagement" (the brief: opened/clicked, replied, booked a call, submitted).
ENGAGEMENT_TOUCH_TYPES = frozenset(
    {"email_open", "email_click", "reply", "linkedin_reply", "meeting_booked", "meeting_held"})
MEETING_TOUCH_TYPES = frozenset({"meeting_booked", "meeting_held"})

#: Fields that make a submission underwriting-ready (the funnel's completeness checklist).
REQUIRED_SUBMISSION_FIELDS = ("has_loss_runs", "has_prior_carrier", "has_risk_description", "has_property_details")
#: Full checklist used by the AI submission-quality scorer (required + recommended).
RECOMMENDED_SUBMISSION_FIELDS = ("has_cois", "has_financials")
FULL_CHECKLIST = REQUIRED_SUBMISSION_FIELDS + RECOMMENDED_SUBMISSION_FIELDS


def is_complete(row) -> bool:
    """True when every required checklist field is present (truthy)."""
    return all(bool(row[f]) for f in REQUIRED_SUBMISSION_FIELDS)


def specialty_weight(focus) -> float:
    return float(config.SPECIALTY_WEIGHTS.get(focus, 0.0))


def is_icp(row) -> bool:
    """ICP rule: commercial lines AND (E&S appetite OR target specialty) AND >= min producers."""
    lines = row["commercial_lines"]
    if lines is None or (isinstance(lines, float) and pd.isna(lines)) or str(lines).strip() == "":
        return False
    size = row["size_producers"]
    if size is None or pd.isna(size) or float(size) < config.ICP_MIN_PRODUCERS:
        return False
    exposure = (row["es_appetite"] in config.ICP_ES_APPETITES
                or specialty_weight(row["specialty_focus"]) >= config.ICP_TARGET_SPECIALTY_MIN)
    return bool(exposure)


def validate_submission(row) -> list[str]:
    """Return violation codes for one submission-like mapping (empty list = valid)."""
    issues: list[str] = []
    sub, quo, bnd = (pd.to_datetime(row.get(k)) if row.get(k) not in (None, "") else pd.NaT
                     for k in ("submitted_at", "quoted_at", "bound_at"))
    if pd.notna(quo) and pd.notna(sub) and quo < sub:
        issues.append("quote_before_submission")
    if pd.notna(bnd) and pd.isna(quo):
        issues.append("bound_without_quote")
    if pd.notna(bnd) and pd.notna(quo) and bnd < quo:
        issues.append("bound_before_quote")
    tat = row.get("quote_turnaround_hours")
    if tat is not None and not pd.isna(tat) and float(tat) < 0:
        issues.append("negative_turnaround")
    return issues


def derive_stage_events(agencies: pd.DataFrame, touches: pd.DataFrame,
                        submissions: pd.DataFrame) -> pd.DataFrame:
    """One row per (agency, stage reached). Nested: stage k requires stage k-1.

    agencies needs: agency_id, first_touch_date, is_icp
    touches needs: agency_id, touched_at, touch_type
    submissions needs: agency_id, submitted_at, quoted_at, bound_at, is_complete
    """
    ag = agencies[["agency_id", "first_touch_date", "is_icp"]].copy()
    ag["first_touch_date"] = pd.to_datetime(ag["first_touch_date"])
    ag = ag.set_index("agency_id")

    t = touches[touches["touch_type"].isin(ENGAGEMENT_TOUCH_TYPES)].copy()
    t["touched_at"] = pd.to_datetime(t["touched_at"])
    first_eng_touch = t.groupby("agency_id")["touched_at"].min()

    s = submissions.copy()
    for c in ("submitted_at", "quoted_at", "bound_at"):
        s[c] = pd.to_datetime(s[c])
    sc = s[s["is_complete"].astype(bool)]
    first_sub = sc.groupby("agency_id")["submitted_at"].min()
    first_quote = sc.groupby("agency_id")["quoted_at"].min()
    first_bind = sc.groupby("agency_id")["bound_at"].min()

    raw_at = ag["first_touch_date"]
    icp_at = raw_at.where(ag["is_icp"].astype(bool))
    eng_at = pd.concat([first_eng_touch.reindex(ag.index), first_sub.reindex(ag.index)], axis=1).min(axis=1)
    eng_at = eng_at.where(icp_at.notna())
    sub_at = first_sub.reindex(ag.index).where(eng_at.notna())
    quo_at = first_quote.reindex(ag.index).where(sub_at.notna())
    bnd_at = first_bind.reindex(ag.index).where(quo_at.notna())

    rep = sc.assign(first_bind_at=first_bind.reindex(sc["agency_id"]).to_numpy())
    rep = rep[(rep["submitted_at"] > rep["first_bind_at"]) &
              (rep["submitted_at"] <= rep["first_bind_at"] + pd.Timedelta(days=config.REPEAT_WINDOW_DAYS))]
    first_rep = rep.groupby("agency_id")["submitted_at"].min()
    rep_at = first_rep.reindex(ag.index).where(bnd_at.notna())

    cols = {"raw_lead": raw_at, "icp_qualified": icp_at, "engaged": eng_at,
            "first_submission": sub_at, "quoted": quo_at, "bound": bnd_at, "repeat_submission": rep_at}
    frames = []
    for st in STAGES:
        ser = cols[st.key].dropna()
        frames.append(pd.DataFrame({"agency_id": ser.index, "stage": st.key,
                                    "stage_order": st.order, "reached_at": ser.values}))
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["stage_order", "agency_id"]).reset_index(drop=True)


def funnel_counts(stage_events: pd.DataFrame) -> pd.Series:
    counts = stage_events.groupby("stage")["agency_id"].nunique()
    return counts.reindex(STAGE_KEYS).fillna(0).astype(int)
