"""Account research from SUPPLIED profile text (no live scraping)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import LLMProvider, get_provider

ANGLE_BY_SPECIALTY = {
    "Habitational": "habitational and apartment risks that standard markets decline",
    "Construction": "contractor and builders-risk accounts that need specialty capacity",
    "Transportation": "trucking and fleet risks with hard-to-place loss history",
    "Hospitality": "restaurants, bars and hotels with liquor and habitability exposures",
    "Real Estate": "real estate and property-management portfolios",
    "Energy": "energy and oilfield services exposures",
    "Manufacturing": "manufacturing risks with unusual property or product exposures",
    "Professional Services": "professional-liability accounts outside standard appetite",
}


class AccountResearch(BaseModel):
    agency_name: str
    likely_commercial_lines: list[str]
    specialty_focus: str | None
    producer_count: int | None
    geographic_footprint: list[str]
    outreach_angle: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = "supplied_profile_text"
    provider: str
    requires_human_review: bool = True


def research_account(agency_name: str, profile_text: str, provider: LLMProvider | None = None) -> AccountResearch:
    provider = provider or get_provider()
    d = provider.extract_account_profile(profile_text)
    found = sum(1 for v in (d["lines"], d["specialty"], d["producers"], d["geography"]) if v)
    angle = (f"Lead with {ANGLE_BY_SPECIALTY[d['specialty']]}" if d["specialty"] in ANGLE_BY_SPECIALTY
             else "Not enough evidence of a specialty; ask what they struggle to place before pitching")
    if d["geography"]:
        angle += f" across {', '.join(d['geography'])}"
    return AccountResearch(
        agency_name=agency_name, likely_commercial_lines=list(d["lines"]), specialty_focus=d["specialty"],
        producer_count=d["producers"], geographic_footprint=list(d["geography"]), outreach_angle=angle,
        confidence=round(min(1.0, 0.1 + 0.225 * found), 3), provider=provider.name)
