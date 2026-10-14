"""Single source of configuration for Broker Growth OS.

Everything tunable lives here: the global seed, the as-of date, the 12-month
window, scoring weights, tier thresholds, dormancy rule, owners, and the ICP
definition. All data in this project is SYNTHETIC.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- determinism -----------------------------------------------------------
SEED = 42  # one global seed; same seed => byte-identical outputs

# --- time ------------------------------------------------------------------
AS_OF = date(2026, 9, 30)
WINDOW_START = date(2025, 10, 1)
WINDOW_END = date(2026, 9, 30)

# --- generator volumes -----------------------------------------------------
N_TRUE_AGENCIES = 3000
DUPLICATE_RATE = 0.05
MISSING_STATE_RATE = 0.04
MISSING_SIZE_RATE = 0.06

# --- ICP definition (see funnel.py) ----------------------------------------
ICP_MIN_PRODUCERS = 3
ICP_ES_APPETITES = ("high", "medium")  # E&S appetite that counts as hard-to-place exposure
SPECIALTY_WEIGHTS = {  # how well a specialty focus matches hard-to-place wholesale appetite
    "Habitational": 1.00,
    "Construction": 0.95,
    "Transportation": 0.85,
    "Hospitality": 0.80,
    "Real Estate": 0.75,
    "Energy": 0.70,
    "Manufacturing": 0.55,
    "Professional Services": 0.40,
}
ICP_TARGET_SPECIALTY_MIN = 0.70  # specialty weight at/above this counts as specialty exposure

# --- geography -------------------------------------------------------------
PRIORITY_STATES = ["CA", "TX", "FL", "NY", "IL"]
SECONDARY_STATES = ["WA", "GA", "NJ", "AZ", "CO", "PA", "NC"]
STATE_WEIGHTS = {  # generator sampling weights (not normalized)
    "CA": 14, "TX": 12, "FL": 11, "NY": 9, "IL": 6, "WA": 4, "GA": 5, "NJ": 4,
    "AZ": 3, "CO": 3, "PA": 4, "NC": 3, "OH": 4, "MI": 3, "MA": 3, "VA": 2,
    "TN": 2, "MN": 2, "MO": 2, "OR": 2,
}
GEO_SCORES = {"priority": 1.0, "secondary": 0.6, "other": 0.3, "unknown": 0.0}

# --- scoring ---------------------------------------------------------------
SCORING_WEIGHTS = {
    "specialty_fit": 0.30,
    "commercial_volume": 0.25,
    "es_activity": 0.20,
    "engagement": 0.15,
    "geographic_priority": 0.10,
}
TIER_THRESHOLDS = {
    "tier1_specialty_fit": 0.70,
    "tier1_es_activity": 0.50,
    "tier1_engagement": 0.20,
    "tier2_score": 0.45,
}
ENGAGEMENT_TOUCH_POINTS = {  # points per engagement event (before recency decay)
    "email_open": 0.25, "email_click": 0.5, "reply": 1.0, "linkedin_reply": 1.0,
    "meeting_booked": 1.5, "meeting_held": 2.0,  # submissions are deliberately NOT here (outcome leakage)
}
ENGAGEMENT_HALF_LIFE_DAYS = 45.0
ENGAGEMENT_SATURATION_POINTS = 3.0  # engagement = 1 - exp(-points / this)
VOLUME_PRODUCER_CAP = 50
VOLUME_LINES_CAP = 5
ES_SUBMISSIONS_CAP = 60

# --- lifecycle rules -------------------------------------------------------
DORMANCY_DAYS = 60
REPEAT_WINDOW_DAYS = 90  # repeat-after-first-bind window used by the funnel stage
COHORT_WINDOWS = (30, 60, 90)  # first-submission-anchored retention windows
ACTIVATION_DAYS = 14

# --- metric hygiene --------------------------------------------------------
MIN_N = 20  # rates with fewer than MIN_N units in the denominator are suppressed

# --- people ----------------------------------------------------------------
OWNERS = ["Maya R.", "Devon K.", "Priya S.", "Luis M.", "Hannah T.", "Omar B."]

# --- experiments -----------------------------------------------------------
EXPERIMENT_ALPHA = 0.05
REACTIVATION_T0 = date(2026, 7, 31)  # experiment C assignment date


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def raw(self) -> Path: return self.root / "data" / "raw"
    @property
    def clean(self) -> Path: return self.root / "data" / "clean"
    @property
    def marts(self) -> Path: return self.root / "data" / "marts"
    @property
    def outputs(self) -> Path: return self.root / "outputs"
    @property
    def logs(self) -> Path: return self.root / "logs"
    @property
    def db(self) -> Path: return self.root / "data" / "clean" / "bgos.sqlite"
    @property
    def sql(self) -> Path: return ROOT / "sql"

    def ensure(self) -> "Paths":
        for p in (self.raw, self.clean, self.marts, self.outputs, self.logs):
            p.mkdir(parents=True, exist_ok=True)
        return self


def get_paths(root: Path | str | None = None) -> Paths:
    """Resolve the output root. BGOS_ROOT env var lets tests/scripts redirect all I/O."""
    return Paths(Path(root or os.environ.get("BGOS_ROOT") or ROOT))

# --- cleaning --------------------------------------------------------------
DEDUPE_THRESHOLD = 0.85  # difflib ratio on normalized agency-name cores, within the same state

# --- scoring detail --------------------------------------------------------
HARD_TO_PLACE_LINES = ("Umbrella/Excess", "Professional Liability", "Inland Marine", "Cyber")
HARD_LINES_CAP = 3
ES_APPETITE_SCORES = {"high": 1.0, "medium": 0.6, "low": 0.25, "none": 0.0}

# --- pipeline projection ---------------------------------------------------
PIPELINE_OPEN_DAYS = 90  # an agency is "open pipeline" if its last activity is within this many days of the as-of date

# --- experiment windows ----------------------------------------------------
A_OUTCOME_DAYS = 60   # A: first complete submission within 60d of first touch
B_OUTCOME_DAYS = 14   # B: complete submission within 14d of engagement
C_OUTCOME_DAYS = 45   # C: complete submission within 45d after reactivation date
MIN_N_WEEKLY = 10     # min denominator for weekly diagnostic rates

# --- out-of-sample tier check ----------------------------------------------
HOLDOUT_DAYS = 90  # score prospects at (as-of minus this), then measure first submissions in the following window

# --- cohort maturity (audit B-18) -------------------------------------------
# A conversion step is measured only on agencies that reached the PREVIOUS stage at least this many days before the
# as-of date, so recent leads that simply have not had time to convert do not drag rates down. Windows are set from the
# observed lag distribution (about the 95th percentile or more); tests verify they cover it.
STAGE_MATURITY_DAYS = {"engaged": 14, "first_submission": 60, "quoted": 60, "bound": 180, "repeat_submission": 90}
