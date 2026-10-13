"""Email FIRST-LINE drafter. Produces DRAFT text only. There is no send function anywhere in this codebase."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .base import LLMProvider, get_provider


class EmailFirstLine(BaseModel):
    agency_id: str
    first_line: str
    personalization: dict
    provider: str
    status: Literal["draft"] = "draft"
    requires_human_review: Literal[True] = True  # cannot be set to False


def draft_first_line(agency: dict, recent_activity: str | None = None, provider: LLMProvider | None = None) -> EmailFirstLine:
    provider = provider or get_provider()
    ctx = {"agency_id": agency["agency_id"], "agency_name": agency.get("name", "your agency"),
           "specialty": agency.get("specialty_focus"), "state": agency.get("state"), "recent_activity": recent_activity}
    line = provider.write_first_line(ctx).strip()
    return EmailFirstLine(agency_id=agency["agency_id"], first_line=line, personalization=ctx, provider=provider.name)
