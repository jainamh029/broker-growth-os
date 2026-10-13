import itertools
import re
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

import config
from bgos import funnel, scoring
from bgos.ai import base, fixtures
from bgos.ai.anthropic_provider import AnthropicProvider
from bgos.ai.email_draft import EmailFirstLine, draft_first_line
from bgos.ai.mock import MockProvider
from bgos.ai.next_best_action import NextBestAction, recommend
from bgos.ai.research import AccountResearch, research_account
from bgos.ai.submission_quality import FIELD_MAP, WEIGHTS, SubmissionQuality, score_submission

SRC = config.ROOT / "src"


@pytest.fixture(autouse=True)
def no_key_no_network(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("BGOS_LLM_MODEL", raising=False)

    def blocked(*a, **k):
        raise RuntimeError("network access attempted in test")
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def test_default_provider_is_mock_without_key():
    assert isinstance(base.get_provider(), MockProvider)


def test_key_without_model_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    assert isinstance(base.get_provider(), MockProvider)
    with pytest.raises(RuntimeError):
        AnthropicProvider()  # no model configured: refuses rather than guessing a model name


def test_research_outputs_validate_and_are_sensible():
    for name, text in fixtures.PROFILES.items():
        r = research_account(name, text)
        assert isinstance(r, AccountResearch)
        AccountResearch.model_validate(r.model_dump())
        assert r.requires_human_review is True and r.provider == "mock"
    ridge = research_account("Ridgeline Risk Advisors", fixtures.PROFILES["Ridgeline Risk Advisors"])
    assert ridge.specialty_focus == "Habitational" and ridge.producer_count == 14
    assert set(ridge.geographic_footprint) == {"TX", "OK", "LA"} and "Umbrella/Excess" in ridge.likely_commercial_lines
    assert "habitational" in ridge.outreach_angle.lower()
    prairie = research_account("Prairie Mutual Agency", fixtures.PROFILES["Prairie Mutual Agency"])
    assert prairie.specialty_focus is None and prairie.confidence < 0.3  # no invention


def test_weights_sum_to_one_and_cover_checklist():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
    assert {FIELD_MAP[k] for k in WEIGHTS} == set(funnel.FULL_CHECKLIST)


def test_scorer_100_for_complete_and_flags_exact_missing():
    q = score_submission(fixtures.SUBMISSIONS["complete"])
    assert q.score == 100 and q.missing_items == [] and q.ask_broker == [] and q.underwriting_ready
    for key, text in fixtures.SUBMISSIONS.items():
        q = score_submission(text)
        SubmissionQuality.model_validate(q.model_dump())
        assert set(q.missing_items) == set(fixtures.EXPECTED_MISSING[key]), key
        assert len(q.ask_broker) == len(q.missing_items)
        assert q.score == pytest.approx(100 * sum(w for k, w in WEIGHTS.items() if k not in q.missing_items))
    assert score_submission(fixtures.SUBMISSIONS["empty"]).score == 0


def test_scorer_structured_input_and_underwriting_ready_matches_funnel():
    full = {k: True for k in WEIGHTS}
    assert score_submission(full).score == 100
    for k in WEIGHTS:
        q = score_submission({**full, k: False})
        assert q.missing_items == [k]
        required = FIELD_MAP[k] in funnel.REQUIRED_SUBMISSION_FIELDS
        assert q.underwriting_ready == (not required)
        assert q.score == pytest.approx(100 - 100 * WEIGHTS[k])


def test_scorer_is_deterministic():
    a = [score_submission(t).model_dump() for t in fixtures.SUBMISSIONS.values()]
    b = [score_submission(t).model_dump() for t in fixtures.SUBMISSIONS.values()]
    assert a == b


NBA_CASES = [
    ("Tier 1", "icp_qualified", "outbound"), ("Tier 1", "engaged", "onboarding"), ("Tier 1", "first_submission", "expansion"),
    ("Tier 1", "bound", "expansion"), ("Tier 2", "raw_lead", "outbound"), ("Tier 2", "engaged", "onboarding"),
    ("Tier 2", "quoted", "expansion"), ("Reactivation", "bound", "reactivation"), ("Reactivation", "first_submission", "reactivation"),
    ("Tier 3", "raw_lead", "monitor"), ("Tier 3", "engaged", "monitor"),
]


@pytest.mark.parametrize("tier,stage,expected", NBA_CASES)
def test_nba_consistent_with_tier_and_stage(tier, stage, expected):
    n = recommend("AG-1", tier, stage)
    NextBestAction.model_validate(n.model_dump())
    assert n.action == expected and tier in n.reason and n.requires_human_review


def test_nba_full_grid_consistent_with_scoring_table():
    for tier, stage in itertools.product(scoring.TIERS, funnel.STAGE_KEYS):
        assert recommend("x", tier, stage).action == scoring.recommend_action(tier, stage)
    with pytest.raises(ValueError):
        recommend("x", "Tier 9", "bound")


def test_drafts_always_require_review():
    ag = {"agency_id": "AG-0042", "name": "Ridgeline Insurance Agency", "specialty_focus": "Habitational", "state": "TX"}
    for recent in (None, "your reply on 2026-09-20"):
        d = draft_first_line(ag, recent)
        EmailFirstLine.model_validate(d.model_dump())
        assert d.requires_human_review is True and d.status == "draft" and len(d.first_line) > 20
        assert "habitational" in d.first_line.lower()
    assert "your reply on 2026-09-20" in draft_first_line(ag, "your reply on 2026-09-20").first_line
    assert draft_first_line(ag).first_line == draft_first_line(ag).first_line  # deterministic
    with pytest.raises(ValidationError):
        EmailFirstLine(agency_id="x", first_line="y", personalization={}, provider="mock", requires_human_review=False)


def test_no_send_capability_anywhere_in_src():
    banned = [r"smtplib", r"requests\.post", r"import requests", r"\bsendmail\b", r"def\s+send\w*\(", r"send_email", r"sendgrid",
              r"mailgun", r"\.send_message\(", r"urllib\.request", r"http\.client", r"imaplib", r"twilio"]
    offenders = []
    for f in SRC.rglob("*.py"):
        text = f.read_text()
        for pat in banned:
            if re.search(pat, text):
                offenders.append((f.name, pat))
    assert not offenders, offenders


def test_no_hardcoded_model_name_in_src():
    for f in SRC.rglob("*.py"):
        text = f.read_text().lower()
        assert not re.search(r"claude-[a-z0-9]+(-[a-z0-9]+)+", text), f.name
        assert not re.search(r"\bgpt-\d", text), f.name


def test_anthropic_provider_with_fake_client_is_validated_and_drafts_only(monkeypatch):
    class Msg:  # minimal fake of the SDK response
        def __init__(self, text): self.content = [type("B", (), {"text": text})()]

    class FakeMessages:
        def create(self, **kw):
            assert kw["model"] == "test-model-from-env"
            sys_prompt = kw["system"]
            if "Which of these items" in sys_prompt:
                return Msg('{"loss_runs": true, "cois": false, "property_details": true, "prior_carrier": true, "risk_description": true, "financials": false}')
            if "Extract from" in sys_prompt:
                return Msg('{"lines": ["Cyber"], "specialty": "Hospitality", "producers": 9, "geography": ["FL"]}')
            return Msg("Saw your hospitality book in Florida; send me a hard-to-place one.")

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setenv("BGOS_LLM_MODEL", "test-model-from-env")
    p = AnthropicProvider(client=FakeClient())
    r = research_account("Fake Agency", "irrelevant", p)
    assert r.specialty_focus == "Hospitality" and r.producer_count == 9 and r.provider == "anthropic"
    q = score_submission("free text", p)
    assert set(q.missing_items) == {"cois", "financials"} and q.deterministic_scoring  # LLM parses, rules score
    d = draft_first_line({"agency_id": "AG-1", "name": "Fake"}, provider=p)
    assert d.requires_human_review is True and d.provider == "anthropic"


def test_demo_runs_offline_and_writes_file(gen_result, scored):
    from bgos.ai import demo
    text = demo.run_demo(gen_result["root"])
    out = (gen_result["root"] / "outputs" / "ai_demo.md").read_text()
    assert out == text and "SYNTHETIC" in out and "requires_human_review" in out
    assert "Account research" in out and "Submission-quality" in out and "Next-best-action" in out and "DRAFTS" in out
