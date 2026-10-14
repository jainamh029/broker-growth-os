"""Next-best-action: outbound / onboarding / reactivation / expansion (+ monitor), from tier and funnel stage."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .. import funnel, scoring

Action = Literal["outbound", "onboarding", "reactivation", "expansion", "monitor", "nurture"]

WHY = {
    "outbound": "No engagement yet but the account fits the ICP: start the ICP-targeted sequence.",
    "onboarding": "Engaged but has not sent a complete submission: remove friction with the submission-ready checklist.",
    "reactivation": "Previously submitted, then silent for the dormancy window: win back with a market update.",
    "expansion": "Already submitting: widen the relationship into adjacent lines of business.",
    "nurture": "Good fit but not engaged yet: keep warm with the low-touch nurture sequence and re-score when they engage.",
    "monitor": "Low fit or low priority: no outreach now; re-score in 30 days.",
}


class NextBestAction(BaseModel):
    agency_id: str
    tier: str
    stage: str
    action: Action
    reason: str
    requires_human_review: bool = True


def recommend(agency_id: str, tier: str, stage: str) -> NextBestAction:
    if tier not in scoring.TIERS:
        raise ValueError(f"unknown tier {tier!r}")
    if stage not in funnel.STAGE_BY_KEY:
        raise ValueError(f"unknown stage {stage!r}")
    action = scoring.recommend_action(tier, stage)  # single rule table shared with ranked_accounts.csv
    return NextBestAction(agency_id=agency_id, tier=tier, stage=stage, action=action,
                          reason=f"{tier} at stage '{funnel.STAGE_BY_KEY[stage].name}': {WHY[action]}")
