"""Deterministic, rules-based provider. No network, no randomness, no API key."""
from __future__ import annotations

import re
import zlib

from .base import LLMProvider

LINE_PATTERNS = {
    "General Liability": r"general liability|\bgl\b",
    "Commercial Property": r"commercial property|property portfolio|hard-to-place property|\bproperty\b",
    "Commercial Auto": r"commercial auto|fleet|trucking",
    "Umbrella/Excess": r"umbrella|excess liability|\bexcess\b",
    "Professional Liability": r"professional liability|\be&o\b|errors and omissions",
    "Inland Marine": r"inland marine|builders risk|builder's risk",
    "Cyber": r"\bcyber\b",
    "Workers Comp": r"workers'? comp",
}
SPECIALTY_PATTERNS = [  # first match wins
    ("Habitational", r"habitational|apartment|condo|multi-?family"),
    ("Construction", r"construction|contractor|builders risk"),
    ("Transportation", r"trucking|transportation|fleet"),
    ("Hospitality", r"hospitality|restaurant|hotel|\bbars?\b|liquor"),
    ("Real Estate", r"real estate|property manage|landlord"),
    ("Energy", r"\boil\b|energy|oilfield|pipeline"),
    ("Manufacturing", r"manufactur"),
    ("Professional Services", r"professional services|consultan|law firm|accountan"),
]
STATES = {
    "alabama": "AL", "arizona": "AZ", "california": "CA", "colorado": "CO", "florida": "FL", "georgia": "GA",
    "illinois": "IL", "louisiana": "LA", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "missouri": "MO", "new jersey": "NJ", "new york": "NY", "north carolina": "NC", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "tennessee": "TN", "texas": "TX",
    "virginia": "VA", "washington": "WA",
}
CHECKLIST_PATTERNS = {
    "loss_runs": r"loss runs?|loss history|currently valued losses",
    "cois": r"\bcois?\b|certificates? of insurance",
    "property_details": r"square f(?:ee|oo)t|sq\.? ?ft|year built|construction type|\btiv\b|occupancy|roof",
    "prior_carrier": r"prior carrier|expiring carrier|currently (?:with|insured by)|incumbent",
    "risk_description": r"description of operations|risk description|operations include|nature of (?:the )?business|operations:",
    "financials": r"financial statements?|financials|revenue|\bp&l\b|payroll",
}
POST_NEGATION = r"\W*(?:\w+\W+){0,2}?(?:not (?:yet )?(?:available|attached|provided|received)|to follow|pending|unavailable|missing)"
NEGATION = r"(?:no|without|missing|not (?:yet )?(?:available|attached|provided)|waiting on|still need)\W+(?:\w+\W+){0,3}"


def _has(pattern: str, text: str) -> bool:
    for m in re.finditer(pattern, text, re.I):
        before = text[max(0, m.start() - 40):m.start()]
        after = text[m.end():m.end() + 40]
        if re.search(NEGATION + r"$", before, re.I) or re.match(POST_NEGATION, after, re.I):
            continue
        return True
    return False


class MockProvider(LLMProvider):
    name = "mock"
    uses_llm = False

    def extract_account_profile(self, text: str) -> dict:
        low = text.lower()
        lines = [k for k, pat in LINE_PATTERNS.items() if re.search(pat, low)]
        # 'property' alone is weak evidence when a stronger property phrase is absent; keep but never invent lines
        specialty = next((s for s, pat in SPECIALTY_PATTERNS if re.search(pat, low)), None)
        m = re.search(r"(\d+)\s+(?:licensed\s+)?(?:producers|agents|brokers)", low) or re.search(r"team of (\d+)", low)
        producers = int(m.group(1)) if m else None
        geo = sorted({abbr for name, abbr in STATES.items() if re.search(r"\b" + name + r"\b", low)})
        return {"lines": lines, "specialty": specialty, "producers": producers, "geography": geo}

    def parse_submission_text(self, text: str) -> dict[str, bool]:
        return {k: _has(p, text) for k, p in CHECKLIST_PATTERNS.items()}

    def write_first_line(self, ctx: dict) -> str:
        name = ctx.get("agency_name", "your agency")
        spec = (ctx.get("specialty") or "specialty commercial").lower()
        state = ctx.get("state")
        where = f" in {state}" if state and state != "UNK" else ""
        recent = ctx.get("recent_activity")
        if recent:
            return f"Following up on {recent}: when one of your {spec} accounts{where} gets declined by standard markets, I'd like {name} to think of us first."
        variants = [
            f"I noticed {name} places a lot of {spec} business{where}; when a standard market walks away from one, I'd like to be the wholesaler you send it to.",
            f"{name}'s focus on {spec} risks{where} is exactly the kind of book we built our submission process around; happy to take a hard-to-place one for a test drive.",
            f"Quick note for {name}: if you have a {spec} renewal{where} that is hard to place, send it over and I'll tell you within a day whether we can quote it.",
        ]
        return variants[zlib.crc32(str(ctx.get("agency_id", name)).encode()) % len(variants)]
