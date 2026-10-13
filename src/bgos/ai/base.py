"""Provider interface for the AI operating layer.

HUMAN-IN-THE-LOOP PROTOTYPE: nothing in this package sends email or contacts anyone. Every
broker-facing draft carries requires_human_review=True. The default provider is a deterministic
rules-based mock, so everything runs with no API key and no network.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Capabilities a provider must supply. All return plain dicts/strings; callers validate with pydantic."""

    name: str = "abstract"
    uses_llm: bool = False

    @abstractmethod
    def extract_account_profile(self, text: str) -> dict:
        """Return keys: lines (list[str]), specialty (str|None), producers (int|None), geography (list[str])."""

    @abstractmethod
    def parse_submission_text(self, text: str) -> dict[str, bool]:
        """Return the six checklist booleans found in free text (loss_runs, cois, property_details, prior_carrier, risk_description, financials)."""

    @abstractmethod
    def write_first_line(self, ctx: dict) -> str:
        """Return a one-sentence personalized email opener (a DRAFT for human review)."""


def get_provider(prefer_llm: bool = True) -> LLMProvider:
    """Mock by default. The real provider activates only if ANTHROPIC_API_KEY is set (and BGOS_LLM_MODEL names a model)."""
    from .mock import MockProvider
    if prefer_llm and os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("BGOS_LLM_MODEL"):
        try:
            from .anthropic_provider import AnthropicProvider
            return AnthropicProvider()
        except Exception:  # SDK missing or misconfigured: fall back to the deterministic mock
            return MockProvider()
    return MockProvider()
