"""SQLite schema + column-level metadata (single source for DDL and the data dictionary).

Foreign keys are ON. Timestamp-order CHECK constraints reject impossible submissions
at the database layer; funnel.validate_submission() flags them earlier in the pipeline.
All data in this project is synthetic.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .funnel import validate_submission  # noqa: F401  (re-exported for convenience)

# table -> {"description", "columns": [(name, sqltype, description, constraint)], "constraints": [...]}
TABLES: dict[str, dict] = {
    "agencies": {
        "description": "One row per (deduplicated) independent insurance agency / brokerage. Synthetic.",
        "columns": [
            ("agency_id", "TEXT", "Primary key, e.g. AG-0001.", "PRIMARY KEY"),
            ("name", "TEXT", "Agency name as recorded (cleaned: whitespace-normalized).", "NOT NULL"),
            ("state", "TEXT", "Two-letter HQ state; 'UNK' when missing in source (flagged by state_missing).", ""),
            ("size_producers", "INTEGER", "Number of producers (numeric after normalization; imputed when missing).", ""),
            ("size_bucket", "TEXT", "Producer-count bucket: 1-2, 3-5, 6-10, 11-25, 26-50, 51+.", ""),
            ("commercial_lines", "TEXT", "Pipe-separated commercial lines the agency writes.", ""),
            ("specialty_focus", "TEXT", "Primary specialty/industry focus.", ""),
            ("es_appetite", "TEXT", "Excess & surplus appetite: high, medium, low, none.", ""),
            ("es_submissions_py", "INTEGER", "Prior-year E&S submissions the agency placed (vendor enrichment).", ""),
            ("prior_bind_rate_pct", "REAL", "Self-reported bind rate (%) with other wholesalers; NULL if invalid or unknown.", ""),
            ("lead_source", "TEXT", "Canonical lead source (outbound, referral, inbound_web, linkedin, event, partner, ...).", ""),
            ("first_touch_date", "TEXT", "Date the agency entered the funnel (ISO date).", "NOT NULL"),
            ("last_activity_date", "TEXT", "Most recent touch or submission date (ISO date).", ""),
            ("owner", "TEXT", "Growth owner (rep) responsible for the account.", ""),
            ("outreach_sequence", "TEXT", "Outreach sequence the agency was enrolled in.", ""),
            ("size_imputed", "INTEGER", "1 if size_producers was imputed (missing in source).", "DEFAULT 0"),
            ("state_missing", "INTEGER", "1 if state was missing in source.", "DEFAULT 0"),
            ("is_icp", "INTEGER", "1 if the agency meets the ICP definition (funnel.is_icp).", "DEFAULT 0"),
        ],
    },
    "touches": {
        "description": "Every outreach/engagement touch: calls, emails, replies, meetings, LinkedIn.",
        "columns": [
            ("touch_id", "TEXT", "Primary key.", "PRIMARY KEY"),
            ("agency_id", "TEXT", "FK to agencies.", "NOT NULL REFERENCES agencies(agency_id)"),
            ("touched_at", "TEXT", "Timestamp of the touch (ISO).", "NOT NULL"),
            ("channel", "TEXT", "email, call, linkedin, meeting, event.", ""),
            ("touch_type", "TEXT", "email_sent, email_open, email_click, reply, call_attempt, call_connected, "
                                    "meeting_booked, meeting_held, linkedin_connect_sent, linkedin_connect_accepted, "
                                    "linkedin_message_sent, linkedin_reply, inbound_form.", ""),
            ("direction", "TEXT", "outbound (we reached out) or inbound (they did).", ""),
            ("owner", "TEXT", "Rep who owned the touch.", ""),
        ],
    },
    "submissions": {
        "description": "Broker submissions to the wholesaler, with quote/bind outcome and economics.",
        "columns": [
            ("submission_id", "TEXT", "Primary key.", "PRIMARY KEY"),
            ("agency_id", "TEXT", "FK to agencies.", "NOT NULL REFERENCES agencies(agency_id)"),
            ("submitted_at", "TEXT", "When the submission arrived (ISO timestamp).", "NOT NULL"),
            ("line_of_business", "TEXT", "Line of business of the risk.", ""),
            ("risk_complexity", "TEXT", "low, medium, high.", ""),
            ("has_loss_runs", "INTEGER", "Completeness: loss runs attached (required).", "DEFAULT 0"),
            ("has_prior_carrier", "INTEGER", "Completeness: prior carrier stated (required).", "DEFAULT 0"),
            ("has_risk_description", "INTEGER", "Completeness: risk description provided (required).", "DEFAULT 0"),
            ("has_property_details", "INTEGER", "Completeness: property/exposure details provided (required).", "DEFAULT 0"),
            ("has_cois", "INTEGER", "Completeness: certificates of insurance (recommended).", "DEFAULT 0"),
            ("has_financials", "INTEGER", "Completeness: financials provided (recommended).", "DEFAULT 0"),
            ("is_complete", "INTEGER", "1 when every REQUIRED checklist field is present (underwriting-ready).", "DEFAULT 0"),
            ("quoted_at", "TEXT", "When a quote was issued; NULL if not quoted (yet).", ""),
            ("bound_at", "TEXT", "When the quote was bound; NULL if not bound.", ""),
            ("quote_turnaround_hours", "REAL", "Hours from submitted_at to quoted_at.", ""),
            ("outcome", "TEXT", "incomplete, declined, quoted_not_bound, bound, pending.", ""),
            ("premium", "REAL", "Quoted premium in USD (NULL if not quoted).", ""),
            ("commission", "REAL", "Commission earned in USD on bound business (NULL unless bound).", ""),
        ],
        "constraints": [
            "CHECK (quoted_at IS NULL OR quoted_at >= submitted_at)",
            "CHECK (bound_at IS NULL OR (quoted_at IS NOT NULL AND bound_at >= quoted_at))",
            "CHECK (quote_turnaround_hours IS NULL OR quote_turnaround_hours >= 0)",
        ],
    },
    "experiment_assignments": {
        "description": "Randomized arm assignment per experiment (A, B, C).",
        "columns": [
            ("assignment_id", "TEXT", "Primary key.", "PRIMARY KEY"),
            ("experiment_id", "TEXT", "A (ICP-targeted outbound), B (submission-ready onboarding), C (reactivation).", "NOT NULL"),
            ("agency_id", "TEXT", "FK to agencies.", "NOT NULL REFERENCES agencies(agency_id)"),
            ("arm", "TEXT", "control or treatment.", "NOT NULL CHECK (arm IN ('control','treatment'))"),
            ("assigned_at", "TEXT", "Assignment date (ISO date); outcome windows start here.", "NOT NULL"),
        ],
        "constraints": ["UNIQUE (experiment_id, agency_id)"],
    },
    "stage_events": {
        "description": "Derived: first time each agency reached each funnel stage (nested, see funnel.py).",
        "columns": [
            ("agency_id", "TEXT", "FK to agencies.", "NOT NULL REFERENCES agencies(agency_id)"),
            ("stage", "TEXT", "Funnel stage key (funnel.STAGES).", "NOT NULL"),
            ("stage_order", "INTEGER", "1..7 position of the stage.", "NOT NULL"),
            ("reached_at", "TEXT", "Timestamp the stage was first reached (ISO).", "NOT NULL"),
        ],
        "constraints": ["PRIMARY KEY (agency_id, stage)"],
    },
    "ranked_accounts": {
        "description": "Derived: Broker Fit Score, tier and next action per agency (see scoring.py).",
        "columns": [
            ("agency_id", "TEXT", "FK to agencies.", "PRIMARY KEY REFERENCES agencies(agency_id)"),
            ("name", "TEXT", "Agency name.", ""),
            ("score", "REAL", "Broker Fit Score in [0,1] (weighted sum of five components).", ""),
            ("specialty_fit", "REAL", "Component in [0,1]: fit of specialty focus + hard-to-place lines.", ""),
            ("commercial_volume", "REAL", "Component in [0,1]: producer count and commercial line breadth.", ""),
            ("es_activity", "REAL", "Component in [0,1]: E&S appetite and prior-year E&S submissions.", ""),
            ("engagement", "REAL", "Component in [0,1]: recency-decayed engagement events.", ""),
            ("geographic_priority", "REAL", "Component in [0,1]: priority-state score.", ""),
            ("tier", "TEXT", "Reactivation, Active (existing customer), Tier 1, Tier 2 or Tier 3 (prospect tiers); precedence in DECISIONS.md D18/D38.", ""),
            ("next_action", "TEXT", "Recommended next step.", ""),
            ("owner", "TEXT", "Account owner.", ""),
            ("channel", "TEXT", "Recommended outreach channel.", ""),
            ("reason", "TEXT", "Human-readable reason naming the top two score components.", ""),
        ],
    },
}


def ddl() -> list[str]:
    stmts = []
    for table, meta in TABLES.items():
        parts = [f"{n} {t} {c}".strip() for n, t, _d, c in meta["columns"]] + list(meta.get("constraints", []))
        stmts.append(f"CREATE TABLE {table} (\n  " + ",\n  ".join(parts) + "\n)")
    stmts.append("CREATE INDEX idx_touches_agency ON touches(agency_id)")
    stmts.append("CREATE INDEX idx_submissions_agency ON submissions(agency_id)")
    stmts.append("CREATE INDEX idx_assign_exp ON experiment_assignments(experiment_id)")
    return stmts


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    for stmt in ddl():
        conn.execute(stmt)
    conn.commit()


def init_db(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    create_schema(conn)
    return conn


def column_names(table: str) -> list[str]:
    return [c[0] for c in TABLES[table]["columns"]]
