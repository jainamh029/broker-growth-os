"""Submission-quality scorer: deterministic weighted checklist. An LLM (if enabled) only helps parse free text."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .. import funnel
from .base import LLMProvider, get_provider

WEIGHTS = {  # sum to 1.0; required-for-funnel items carry the most weight
    "loss_runs": 0.25, "property_details": 0.20, "risk_description": 0.20,
    "financials": 0.15, "prior_carrier": 0.10, "cois": 0.10,
}
FIELD_MAP = {"loss_runs": "has_loss_runs", "cois": "has_cois", "property_details": "has_property_details",
             "prior_carrier": "has_prior_carrier", "risk_description": "has_risk_description", "financials": "has_financials"}
ASK = {
    "loss_runs": "Please send currently valued loss runs (5 years, all carriers) for this account.",
    "cois": "Please send certificates of insurance for any subcontractors/vendors on the risk.",
    "property_details": "Please send property details: construction type, year built, square footage, occupancy, TIV and roof age.",
    "prior_carrier": "Who is the expiring/prior carrier, and what is the expiring premium?",
    "risk_description": "Please add a short description of operations (what the insured does, revenue by class, any unusual exposures).",
    "financials": "Please send recent financial statements or revenue/payroll figures.",
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
assert {FIELD_MAP[k] for k in WEIGHTS} == set(funnel.FULL_CHECKLIST)


class SubmissionQuality(BaseModel):
    score: float = Field(ge=0, le=100)
    missing_items: list[str]
    ask_broker: list[str]
    underwriting_ready: bool
    provider: str
    deterministic_scoring: bool = True
    requires_human_review: bool = True  # the ask list is broker-facing text drafted for a human to send


def score_submission(submission: dict[str, bool] | str, provider: LLMProvider | None = None) -> SubmissionQuality:
    """submission: {item: bool} for the six checklist items, or free text (parsed by the provider)."""
    provider = provider or get_provider()
    present = provider.parse_submission_text(submission) if isinstance(submission, str) else {k: bool(submission.get(k, False)) for k in WEIGHTS}
    present = {k: bool(present.get(k, False)) for k in WEIGHTS}
    score = round(100 * sum(w for k, w in WEIGHTS.items() if present[k]), 1)
    missing = [k for k in WEIGHTS if not present[k]]
    required = {k for k, f in FIELD_MAP.items() if f in funnel.REQUIRED_SUBMISSION_FIELDS}
    return SubmissionQuality(score=score, missing_items=missing, ask_broker=[ASK[k] for k in missing],
                             underwriting_ready=required.isdisjoint(missing), provider=provider.name)
