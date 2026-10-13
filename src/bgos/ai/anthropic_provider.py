"""Optional real-LLM provider. Activates ONLY when ANTHROPIC_API_KEY is set; the model comes from BGOS_LLM_MODEL.

Never used by tests or by `make all`. Output is always re-validated by the pydantic schemas in the capability modules,
and every draft still carries requires_human_review=True. This module cannot send anything: it only reads model text.
"""
from __future__ import annotations

import json
import os

from .base import LLMProvider
from .mock import MockProvider

JSON_ONLY = "Reply with a single JSON object and nothing else."


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    uses_llm = True

    def __init__(self, client=None, model: str | None = None):
        self.model = model or os.environ.get("BGOS_LLM_MODEL")
        if not self.model:
            raise RuntimeError("Set BGOS_LLM_MODEL to the model name to use; no model is hard-coded.")
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("ANTHROPIC_API_KEY is not set.")
            import anthropic  # optional dependency: pip install anthropic
            client = anthropic.Anthropic()
        self.client = client
        self._fallback = MockProvider()

    def _ask(self, system: str, user: str, max_tokens: int = 500) -> str:
        msg = self.client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                          messages=[{"role": "user", "content": user}])
        return "".join(getattr(b, "text", "") for b in msg.content)

    def _ask_json(self, system: str, user: str) -> dict | None:
        try:
            raw = self._ask(system + " " + JSON_ONLY, user)
            return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except Exception:
            return None

    def extract_account_profile(self, text: str) -> dict:
        d = self._ask_json("Extract from an insurance agency profile: lines (list of commercial lines), "
                           "specialty (string or null), producers (int or null), geography (list of 2-letter states).", text)
        base = self._fallback.extract_account_profile(text)
        if not d:
            return base
        return {"lines": d.get("lines") or base["lines"], "specialty": d.get("specialty") or base["specialty"],
                "producers": d.get("producers") or base["producers"], "geography": d.get("geography") or base["geography"]}

    def parse_submission_text(self, text: str) -> dict[str, bool]:
        keys = ["loss_runs", "cois", "property_details", "prior_carrier", "risk_description", "financials"]
        d = self._ask_json("Which of these items are PRESENT in the broker's submission text? Return booleans for keys: "
                           + ", ".join(keys), text)
        base = self._fallback.parse_submission_text(text)
        if not d:
            return base
        return {k: bool(d.get(k, base[k])) for k in keys}

    def write_first_line(self, ctx: dict) -> str:
        try:
            out = self._ask("Write ONE sentence (max 35 words) as a first line of a cold email from a specialty wholesale "
                            "insurance broker to an independent agency. No claims about prices, speed guarantees, or "
                            "customers. Draft only; a human will review before anything is sent.", json.dumps(ctx)).strip()
            return out if out else self._fallback.write_first_line(ctx)
        except Exception:
            return self._fallback.write_first_line(ctx)
