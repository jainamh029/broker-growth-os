# Data Dictionary

> Synthetic data. Demonstrates the method, not Hedge's actual performance. Generated from `src/bgos/schema.py` by `make docs`; do not edit by hand.

## Funnel stages

| # | Stage | Definition |
|---|---|---|
| 1 | Raw Lead | Agency identified via a public source, referral, or inbound request. Entry date = first touch date. |
| 2 | ICP-Qualified Agency | Raw lead that writes commercial lines AND has E&S/specialty/hard-to-place exposure (E&S appetite high/medium OR a target specialty focus) AND has at least 3 producers. Qualification is dated at first touch. |
| 3 | Engaged Broker | ICP-qualified agency that opened or clicked an email, replied, booked a meeting/call, or submitted. Dated at the earliest such event. |
| 4 | First Submission | Engaged agency's first COMPLETE, underwriting-ready submission (all required checklist fields present). Incomplete submissions do not count. |
| 5 | Quoted | First-submission agency with at least one complete submission that received a quote. |
| 6 | Bound | Quoted agency with at least one submission that was bound. |
| 7 | Repeat Submission | Bound agency that sent another complete submission within 90 days AFTER its first bind (bind-anchored; see DECISIONS.md D6). |

## Tables (SQLite, foreign keys on)

### `agencies`

One row per (deduplicated) independent insurance agency / brokerage. Synthetic.

| Column | Type | Description | Constraints |
|---|---|---|---|
| `agency_id` | TEXT | Primary key, e.g. AG-0001. | PRIMARY KEY |
| `name` | TEXT | Agency name as recorded (cleaned: whitespace-normalized). | NOT NULL |
| `state` | TEXT | Two-letter HQ state; 'UNK' when missing in source (flagged by state_missing). |  |
| `size_producers` | INTEGER | Number of producers (numeric after normalization; imputed when missing). |  |
| `size_bucket` | TEXT | Producer-count bucket: 1-2, 3-5, 6-10, 11-25, 26-50, 51+. |  |
| `commercial_lines` | TEXT | Pipe-separated commercial lines the agency writes. |  |
| `specialty_focus` | TEXT | Primary specialty/industry focus. |  |
| `es_appetite` | TEXT | Excess & surplus appetite: high, medium, low, none. |  |
| `es_submissions_py` | INTEGER | Prior-year E&S submissions the agency placed (vendor enrichment). |  |
| `prior_bind_rate_pct` | REAL | Self-reported bind rate (%) with other wholesalers; NULL if invalid or unknown. |  |
| `lead_source` | TEXT | Canonical lead source (outbound, referral, inbound_web, linkedin, event, partner, ...). |  |
| `first_touch_date` | TEXT | Date the agency entered the funnel (ISO date). | NOT NULL |
| `last_activity_date` | TEXT | Most recent touch or submission date (ISO date). |  |
| `owner` | TEXT | Growth owner (rep) responsible for the account. |  |
| `outreach_sequence` | TEXT | Outreach sequence the agency was enrolled in. |  |
| `size_imputed` | INTEGER | 1 if size_producers was imputed (missing in source). | DEFAULT 0 |
| `state_missing` | INTEGER | 1 if state was missing in source. | DEFAULT 0 |
| `is_icp` | INTEGER | 1 if the agency meets the ICP definition (funnel.is_icp). | DEFAULT 0 |

### `touches`

Every outreach/engagement touch: calls, emails, replies, meetings, LinkedIn.

| Column | Type | Description | Constraints |
|---|---|---|---|
| `touch_id` | TEXT | Primary key. | PRIMARY KEY |
| `agency_id` | TEXT | FK to agencies. | NOT NULL REFERENCES agencies(agency_id) |
| `touched_at` | TEXT | Timestamp of the touch (ISO). | NOT NULL |
| `channel` | TEXT | email, call, linkedin, meeting, event. |  |
| `touch_type` | TEXT | email_sent, email_open, email_click, reply, call_attempt, call_connected, meeting_booked, meeting_held, linkedin_connect_sent, linkedin_connect_accepted, linkedin_message_sent, linkedin_reply, inbound_form. |  |
| `direction` | TEXT | outbound (we reached out) or inbound (they did). |  |
| `owner` | TEXT | Rep who owned the touch. |  |

### `submissions`

Broker submissions to the wholesaler, with quote/bind outcome and economics.

| Column | Type | Description | Constraints |
|---|---|---|---|
| `submission_id` | TEXT | Primary key. | PRIMARY KEY |
| `agency_id` | TEXT | FK to agencies. | NOT NULL REFERENCES agencies(agency_id) |
| `submitted_at` | TEXT | When the submission arrived (ISO timestamp). | NOT NULL |
| `line_of_business` | TEXT | Line of business of the risk. |  |
| `risk_complexity` | TEXT | low, medium, high. |  |
| `has_loss_runs` | INTEGER | Completeness: loss runs attached (required). | DEFAULT 0 |
| `has_prior_carrier` | INTEGER | Completeness: prior carrier stated (required). | DEFAULT 0 |
| `has_risk_description` | INTEGER | Completeness: risk description provided (required). | DEFAULT 0 |
| `has_property_details` | INTEGER | Completeness: property/exposure details provided (required). | DEFAULT 0 |
| `has_cois` | INTEGER | Completeness: certificates of insurance (recommended). | DEFAULT 0 |
| `has_financials` | INTEGER | Completeness: financials provided (recommended). | DEFAULT 0 |
| `is_complete` | INTEGER | 1 when every REQUIRED checklist field is present (underwriting-ready). | DEFAULT 0 |
| `quoted_at` | TEXT | When a quote was issued; NULL if not quoted (yet). |  |
| `bound_at` | TEXT | When the quote was bound; NULL if not bound. |  |
| `quote_turnaround_hours` | REAL | Hours from submitted_at to quoted_at. |  |
| `outcome` | TEXT | incomplete, declined, quoted_not_bound, bound, pending. |  |
| `premium` | REAL | Quoted premium in USD (NULL if not quoted). |  |
| `commission` | REAL | Commission earned in USD on bound business (NULL unless bound). |  |
| _table constraint_ | | `CHECK (quoted_at IS NULL OR quoted_at >= submitted_at)` | |
| _table constraint_ | | `CHECK (bound_at IS NULL OR (quoted_at IS NOT NULL AND bound_at >= quoted_at))` | |
| _table constraint_ | | `CHECK (quote_turnaround_hours IS NULL OR quote_turnaround_hours >= 0)` | |

### `experiment_assignments`

Randomized arm assignment per experiment (A, B, C).

| Column | Type | Description | Constraints |
|---|---|---|---|
| `assignment_id` | TEXT | Primary key. | PRIMARY KEY |
| `experiment_id` | TEXT | A (ICP-targeted outbound), B (submission-ready onboarding), C (reactivation). | NOT NULL |
| `agency_id` | TEXT | FK to agencies. | NOT NULL REFERENCES agencies(agency_id) |
| `arm` | TEXT | control or treatment. | NOT NULL CHECK (arm IN ('control','treatment')) |
| `assigned_at` | TEXT | Assignment date (ISO date); outcome windows start here. | NOT NULL |
| _table constraint_ | | `UNIQUE (experiment_id, agency_id)` | |

### `stage_events`

Derived: first time each agency reached each funnel stage (nested, see funnel.py).

| Column | Type | Description | Constraints |
|---|---|---|---|
| `agency_id` | TEXT | FK to agencies. | NOT NULL REFERENCES agencies(agency_id) |
| `stage` | TEXT | Funnel stage key (funnel.STAGES). | NOT NULL |
| `stage_order` | INTEGER | 1..7 position of the stage. | NOT NULL |
| `reached_at` | TEXT | Timestamp the stage was first reached (ISO). | NOT NULL |
| _table constraint_ | | `PRIMARY KEY (agency_id, stage)` | |

### `ranked_accounts`

Derived: Broker Fit Score, tier and next action per agency (see scoring.py).

| Column | Type | Description | Constraints |
|---|---|---|---|
| `agency_id` | TEXT | FK to agencies. | PRIMARY KEY REFERENCES agencies(agency_id) |
| `name` | TEXT | Agency name. |  |
| `score` | REAL | Broker Fit Score in [0,1] (weighted sum of five components). |  |
| `specialty_fit` | REAL | Component in [0,1]: fit of specialty focus + hard-to-place lines. |  |
| `commercial_volume` | REAL | Component in [0,1]: producer count and commercial line breadth. |  |
| `es_activity` | REAL | Component in [0,1]: E&S appetite and prior-year E&S submissions. |  |
| `engagement` | REAL | Component in [0,1]: recency-decayed engagement events. |  |
| `geographic_priority` | REAL | Component in [0,1]: priority-state score. |  |
| `tier` | TEXT | Reactivation, Tier 1, Tier 2, or Tier 3 (precedence in DECISIONS.md D8). |  |
| `next_action` | TEXT | Recommended next step. |  |
| `owner` | TEXT | Account owner. |  |
| `channel` | TEXT | Recommended outreach channel. |  |
| `reason` | TEXT | Human-readable reason naming the top two score components. |  |

## Metric marts (`data/marts/*.csv`, one per SQL file in `sql/`)

| Mart | SQL file | Description |
|---|---|---|
| `new_icp_agencies_weekly` | `sql/new_icp_agencies_weekly.sql` | New ICP-qualified agencies entering per week |
| `funnel_counts` | `sql/funnel_counts.sql` | Nested funnel counts, step and cumulative conversion |
| `meeting_funnel` | `sql/meeting_funnel.sql` | Meeting diagnostic: engaged -> meeting -> submission |
| `source_quality` | `sql/source_quality.sql` | Source quality by downstream bind/repeat, min-n suppressed |
| `time_to_quote` | `sql/time_to_quote.sql` | Median hours submission -> quote, overall/line/complexity |
| `dormant_reactivation` | `sql/dormant_reactivation.sql` | Dormant agencies ranked by prior premium and fit |
| `pipeline_projection` | `sql/pipeline_projection.sql` | Assumption-driven first-bind projection by segment |
| `cohort_retention` | `sql/cohort_retention.sql` | Repeat submission within 30/60/90 days of first submission |
| `activation_rate` | `sql/activation_rate.sql` | Engaged -> first submission within 14 days |
| `owner_performance` | `sql/owner_performance.sql` | Owner performance on downstream conversion |
| `weekly_growth_review` | `sql/weekly_growth_review.sql` | North star, inputs and diagnostics by week |
| `topline` | `sql/topline.sql` | Monday-morning topline numbers |
| `experiment_outcomes` | `sql/experiment_outcomes.sql` | Per-assignment experiment outcomes |

## Raw files and injected defects

`data/raw/*.csv` mirror the tables above but are deliberately dirty. `data/raw/injected_defects.json` lists every injected defect (counts by type, affected ids, and the planted experiment effects). The cleaning stage never reads it.

| Defect type | Cleaning rule |
|---|---|
| duplicate_agencies | state-blocked fuzzy name match, earliest record wins, children remapped |
| missing_state / missing_size | flagged (`state_missing`, `size_imputed`); size imputed with specialty median |
| mixed_size_formats | parsed to integer (range -> floor midpoint) |
| inconsistent_source_labels | explicit mapping table to canonical sources |
| bind_rate_over_100 | value nullified, logged in quarantine.csv |
| negative_turnaround | repaired from timestamps |
| quote_before_submission / bound_before_quote | row quarantined |
| tiny-n sources | kept; rates suppressed when n < 20 |
