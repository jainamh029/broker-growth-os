"""`make ai-demo`: write outputs/ai_demo.md with sample outputs from every AI capability (mock provider by default)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import config
from . import fixtures
from .base import get_provider
from .email_draft import draft_first_line
from .next_best_action import recommend
from .research import research_account
from .submission_quality import score_submission

PHRASE = {"reply": "your reply on {d}", "meeting_held": "our call on {d}", "meeting_booked": "the meeting you booked on {d}",
          "email_click": "your click-through on {d}", "linkedin_reply": "your LinkedIn reply on {d}"}


def recent_activity_phrase(touches: pd.DataFrame, agency_id: str) -> str | None:
    t = touches[(touches.agency_id == agency_id) & touches.touch_type.isin(PHRASE)].sort_values("touched_at")
    if t.empty:
        return None
    r = t.iloc[-1]
    return PHRASE[r.touch_type].format(d=str(r.touched_at)[:10])


def run_demo(root: Path | str | None = None) -> str:
    paths = config.get_paths(root).ensure()
    prov = get_provider()
    L = ["# AI Operating Layer Demo", "",
         "> **SYNTHETIC DATA. HUMAN-IN-THE-LOOP PROTOTYPE.** Nothing here is sent to anyone: every draft carries "
         "`requires_human_review = True`, and the codebase has no send function. "
         f"Provider: `{prov.name}` (deterministic rules; no network, no API key).", "", "## 1. Account research (from supplied profile text)", ""]
    for name, text in fixtures.PROFILES.items():
        r = research_account(name, text, prov)
        L += [f"**{name}**", "", f"- Lines: {', '.join(r.likely_commercial_lines) or 'none found'}",
              f"- Specialty: {r.specialty_focus or 'unknown'}; producers: {r.producer_count or 'unknown'}; footprint: {', '.join(r.geographic_footprint) or 'unknown'}",
              f"- Outreach angle: {r.outreach_angle}", f"- Confidence: {r.confidence}", ""]
    L += ["## 2. Submission-quality scorer (deterministic weighted checklist)", ""]
    for key, text in fixtures.SUBMISSIONS.items():
        q = score_submission(text, prov)
        L += [f"**{key}**: score {q.score:g}/100, underwriting-ready: {q.underwriting_ready}",
              f"- Missing: {', '.join(q.missing_items) or 'nothing'}"]
        L += [f"- Ask the broker: {a}" for a in q.ask_broker] + [""]
    ranked_path, touches_path = paths.outputs / "ranked_accounts.csv", paths.clean / "touches.csv"
    if ranked_path.exists():
        ranked = pd.read_csv(ranked_path)
        touches = pd.read_csv(touches_path) if touches_path.exists() else pd.DataFrame(columns=["agency_id", "touch_type", "touched_at"])
        L += ["## 3. Next-best-action (from the ranked synthetic accounts)", "", "| Agency | Tier | Stage | Action | Why |", "|---|---|---|---|---|"]
        for tier in ("Tier 1", "Tier 2", "Reactivation", "Tier 3"):
            for r in ranked[ranked.tier == tier].head(2).itertuples():
                n = recommend(r.agency_id, r.tier, r.stage)
                L.append(f"| {r.name} | {n.tier} | {n.stage} | {n.action} | {n.reason} |")
        L += ["", "## 4. Email first-line drafts (DRAFTS; human review required)", ""]
        for r in ranked[ranked.tier == "Tier 1"].head(3).itertuples():
            d = draft_first_line(r._asdict(), recent_activity_phrase(touches, r.agency_id), prov)
            L += [f"- **{r.name}** [{d.status}, requires_human_review={d.requires_human_review}]: {d.first_line}"]
    else:
        L += ["## 3-4. Next-best-action and drafts", "", "Run `make score` first to use the ranked synthetic accounts."]
    text = "\n".join(L) + "\n"
    (paths.outputs / "ai_demo.md").write_text(text)
    return text
