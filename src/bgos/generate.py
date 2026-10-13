"""Dirty SYNTHETIC data generator.

Everything here is invented. The generator plants ground-truth effects so tests can verify
the pipeline recovers them (plumbing tests, not findings):

* Experiment A: ICP-targeted outbound, true relative lift +30% on first-submission rate.
* Experiment B: submission-ready onboarding, true relative lift +15% on 14-day submission rate.
* Experiment C: reactivation outreach, true effect = 0 (planted null).
* referral = low volume / highest quality; linkedin = high volume / lowest quality.

It then injects realistic defects and writes every injected defect to
data/raw/injected_defects.json. The cleaning stage never reads that manifest.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit

import config
from . import funnel

# ----------------------------------------------------------------------------------------------
# vocabulary
# ----------------------------------------------------------------------------------------------
SURNAMES = """Hargrove Bellwether Summit Cedar Ironwood Lakeshore Pinnacle Redwood Sterling Westbrook Ashford
Blackwell Calloway Dunmore Eastgate Fairbanks Galloway Hawthorne Ingram Jarrett Kensington Larkspur Montclair
Northcott Oakmont Prescott Quimby Rutledge Stanhope Thornton Underhill Vanderbilt Whitaker Yarborough Zimmerman
Abernathy Barrington Chandler Dellwood Ellsworth Fitzgerald Granger Holloway Ironside Jamison Kingsley Lockwood
Mercer Nightingale Osborne Pemberton Radcliffe Sinclair Tennyson Upton Valmont Wakefield Alderman Brightwater
Crawford Davenport Emerson Forsyth Gladstone Harcourt Irving Kimball Langford Montgomery Newcastle Overton
Pritchard Quarles Remington Salisbury Trowbridge Ulrich Vickers Winslow Ainsley Brookfield Carrington Dunhill
Easton Fenwick Garrison Hartwell Isley Jennings Kirkland Lindell Madison Norwood Orchard Parkside Ridgeway
Stonebridge Tidewater Unity Vista Windermere Bayview Canyon Delmar Evergreen Foxglove Glenwood Highland
Islander Juniper Keystone Lighthouse Meadowbrook Northstar Olympic Prairie Quarry Riverbend Sandstone Timberline
Union Valley Willow Yellowstone Zephyr Anchor Beacon Compass Driftwood Harbor Landmark Mariner Paramount""".split()

DESCRIPTORS = ["Insurance Agency", "Insurance Group", "Risk Advisors", "Insurance Services",
               "Insurance Brokers", "Insurance Associates", "Risk Partners", "Agency"]
SUFFIXES = ["", "", " LLC", " Inc.", ", Inc.", " Co."]
ABBREV = {"Insurance": "Ins.", "Agency": "Agcy", "Group": "Grp", "Associates": "Assoc.",
          "Services": "Svcs", "Brokers": "Brkrs", "Advisors": "Advisors", "Partners": "Prtnrs"}

LINES = ["General Liability", "Commercial Property", "Commercial Auto", "Umbrella/Excess",
         "Professional Liability", "Inland Marine", "Cyber", "Workers Comp"]
SPECIALTIES = list(config.SPECIALTY_WEIGHTS)
SPECIALTY_P = np.array([0.14, 0.16, 0.10, 0.12, 0.10, 0.06, 0.14, 0.18])  # order of SPECIALTY_WEIGHTS keys
assert len(SPECIALTY_P) == len(SPECIALTIES) and abs(SPECIALTY_P.sum() - 1) < 1e-9

SOURCE_WEIGHTS = {"linkedin": 0.30, "outbound": 0.25, "inbound_web": 0.15, "partner": 0.12,
                  "event": 0.10, "referral": 0.08}
TINY_SOURCES = {"podcast_sponsor": 3, "state_assoc_booth": 4, "wholesaler_alumni": 5}
CANONICAL_SOURCES = tuple(SOURCE_WEIGHTS) + tuple(TINY_SOURCES)

SOURCE_LABEL_VARIANTS = {
    "linkedin": ["LinkedIn", "LI", "Linked In", "LinkedIn Outreach", " linkedin "],
    "outbound": ["outbound-email", "Outbound", "cold email", "outbound_email", "OUTBOUND"],
    "inbound_web": ["Inbound Web", "web", "website", "inbound-web", "Website Inbound"],
    "partner": ["Partner", "partnership", "Partner Channel", "PARTNER"],
    "event": ["Event", "conference", "trade show", "Trade Show"],
    "referral": ["Referral", "referral ", "ref", "Broker Referral", "REFERRAL"],
    "podcast_sponsor": ["Podcast Sponsor", "podcast-sponsor"],
    "state_assoc_booth": ["State Assoc Booth", "state assoc. booth"],
    "wholesaler_alumni": ["Wholesaler Alumni", "wholesaler-alumni"],
}

# source effects on log-odds of each stage (referral best quality, linkedin worst)
SRC_ENG = {"referral": 1.0, "partner": 0.5, "inbound_web": 0.4, "event": 0.1, "outbound": 0.0,
           "linkedin": -0.5, "podcast_sponsor": 0.0, "state_assoc_booth": 0.0, "wholesaler_alumni": 0.0}
SRC_SUB = {"referral": 1.3, "partner": 0.4, "inbound_web": 0.3, "event": 0.0, "outbound": 0.0,
           "linkedin": -0.6, "podcast_sponsor": 0.0, "state_assoc_booth": 0.0, "wholesaler_alumni": 0.0}
SRC_BIND = {"referral": 0.5, "partner": 0.2, "inbound_web": 0.1, "event": 0.0, "outbound": 0.0,
            "linkedin": -0.4, "podcast_sponsor": 0.0, "state_assoc_booth": 0.0, "wholesaler_alumni": 0.0}
OWNER_EFFECT = [0.30, 0.10, 0.0, 0.0, -0.10, -0.30]  # per config.OWNERS index (logit shift)

# calibration intercepts (tuned so the funnel tapers realistically and experiments are powered)
INT_ENG = 0.90
INT_SUB = -0.55
INT_BIND = -1.90
NONICP_ENG_P = 0.12
P_DECLINE = {"low": 0.12, "medium": 0.18, "high": 0.28}
TAT_MEDIAN_H = {"low": 20.0, "medium": 42.0, "high": 90.0}
PREM_MULT = {"low": 1.0, "medium": 1.3, "high": 1.8}
COMPLEXITY_P = [0.40, 0.40, 0.20]
Q14_BASE = 0.55  # P(first complete submission within 14d of engagement | will submit)
A_TRUE_LIFT = 0.30
B_TRUE_LIFT = 0.15
C_TRUE_LIFT = 0.0
REPEAT_RATE_PER_DAY = 0.022
REVIVE_RATE_PER_DAY = 0.0020
P_STICKY = 0.45  # agencies that never go dormant by choice
ACTIVE_MEAN_DAYS = 65.0
P_FIRST_INCOMPLETE = 0.22

START = datetime.combine(config.WINDOW_START, datetime.min.time())
END = datetime.combine(config.WINDOW_END, datetime.max.time()).replace(microsecond=0)
FMT = "%Y-%m-%d %H:%M:%S"


def _ts(d: datetime) -> str:
    return d.strftime(FMT)


def _rand_time(rng, day: datetime) -> datetime:
    return day.replace(hour=int(rng.integers(8, 18)), minute=int(rng.integers(0, 60)), second=0, microsecond=0)


# ----------------------------------------------------------------------------------------------
# names
# ----------------------------------------------------------------------------------------------
from .clean import STOPWORDS, core_name  # noqa: E402,F401


def _similar(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def _make_names(rng, states: list[str]) -> list[str]:
    names, cores_by_state = [], {}
    for st in states:
        for _ in range(500):
            a, b = rng.choice(SURNAMES, 2, replace=False)
            joiner = " & " if rng.random() < 0.5 else " "
            core = f"{a}{joiner}{b}"
            if rng.random() < 0.18:
                core = str(a)
            ncore = core_name(core)
            if all(_similar(ncore, o) < 0.78 for o in cores_by_state.get(st, [])):
                break
        cores_by_state.setdefault(st, []).append(ncore)
        names.append(f"{core} {rng.choice(DESCRIPTORS)}{rng.choice(SUFFIXES)}")
    return names


def _name_variant(rng, name: str) -> str:
    core = core_name(name)
    kind = int(rng.integers(0, 5))
    if kind == 4 and len(core.replace(" ", "")) < 9:
        kind = int(rng.integers(0, 4))
    if kind == 0:  # abbreviations + dropped suffix
        out = name.replace(",", "")
        for k, v in ABBREV.items():
            out = out.replace(k, v)
        for s in (" LLC", " Inc.", " Co."):
            out = out.replace(s, "")
        return out if out != name else name.upper() + " "
    if kind == 1:
        return name.upper()
    if kind == 2:
        base = name
        for d in DESCRIPTORS:
            base = base.replace(d, "")
        for s in (", Inc.", " Inc.", " LLC", " Co."):
            base = base.replace(s, "")
        return base.strip() + " " + str(rng.choice(["LLC", "Agency", "& Co"]))
    if kind == 3:
        return "The " + name.replace("Insurance Agency", "Insurance Services").replace("Agency", "Group")
    # typo in the first token of the core (delete/duplicate/substitute one inner letter)
    first = name.split()[0]
    if len(first) >= 7:
        i = int(rng.integers(2, len(first) - 2))
        op = int(rng.integers(0, 3))
        new = first[:i] + first[i + 1:] if op == 0 else (first[:i] + first[i] + first[i:] if op == 1 else
                                                         first[:i] + "x" + first[i + 1:])
        return name.replace(first, new, 1)
    return name.upper()


# ----------------------------------------------------------------------------------------------
# core simulation
# ----------------------------------------------------------------------------------------------
def _size_bucket_label(n: int) -> str:
    for lo, hi, lab in ((1, 2, "1-2"), (3, 5, "3-5"), (6, 10, "6-10"), (11, 25, "11-25"), (26, 50, "26-50")):
        if lo <= n <= hi:
            return lab
    return "51+"


def _true_agencies(rng, n: int) -> pd.DataFrame:
    ids = [f"AG-{i:04d}" for i in range(1, n + 1)]
    states = list(config.STATE_WEIGHTS)
    sp = np.array([config.STATE_WEIGHTS[s] for s in states], float)
    state = rng.choice(states, n, p=sp / sp.sum())
    names = _make_names(rng, list(state))
    # hard negatives: identical names in different states (state blocking must not merge them)
    for _ in range(8):
        i, j = rng.choice(n, 2, replace=False)
        if state[i] != state[j]:
            names[i] = names[j]
    size = np.clip(np.round(np.exp(rng.normal(1.9, 0.8, n))), 1, 150).astype(int)
    spec_idx = rng.choice(len(SPECIALTIES), n, p=SPECIALTY_P)
    specialty = np.array(SPECIALTIES)[spec_idx]
    w = np.array([config.SPECIALTY_WEIGHTS[s] for s in specialty])
    es = []
    for wi in w:
        p = np.array([0.10 + 0.28 * wi, 0.30, 0.35 - 0.15 * wi, 0.25 - 0.13 * wi])
        p = np.clip(p, 0.02, None)
        es.append(rng.choice(["high", "medium", "low", "none"], p=p / p.sum()))
    es = np.array(es)
    es_base = pd.Series(es).map({"high": 9.0, "medium": 4.0, "low": 1.2, "none": 0.0}).to_numpy()
    es_sub = np.minimum(rng.poisson(es_base * np.sqrt(size)), 80)
    lines = []
    for _ in range(n):
        k = int(rng.choice([1, 2, 3, 4, 5], p=[0.15, 0.30, 0.30, 0.15, 0.10]))
        lines.append("|".join(rng.choice(LINES, k, replace=False)))
    src = rng.choice(list(SOURCE_WEIGHTS), n, p=list(SOURCE_WEIGHTS.values()))
    # first-touch dates: mild growth in weekly intake
    days = (config.WINDOW_END - config.WINDOW_START).days + 1
    dw = np.linspace(1.0, 1.25, days)
    ft = rng.choice(days, n, p=dw / dw.sum())
    owner_idx = rng.integers(0, len(config.OWNERS), n)
    df = pd.DataFrame({
        "agency_id": ids, "name": names, "state": state, "size_producers": size,
        "commercial_lines": lines, "specialty_focus": specialty, "es_appetite": es,
        "es_submissions_py": es_sub,
        "prior_bind_rate_pct": np.round(np.clip(rng.normal(22, 8, n), 3, 50), 1),
        "lead_source": src, "first_touch_day": ft,
        "owner": np.array(config.OWNERS)[owner_idx], "owner_idx": owner_idx,
    })
    # tiny-n anomalous sources: carve out of ICP-qualified agencies that enter early enough to finish
    df["is_icp"] = [funnel.is_icp(r) for r in df.to_dict("records")]
    pool = df[(df.is_icp) & (df.first_touch_day < 200)].index.to_numpy()
    chosen = rng.choice(pool, sum(TINY_SOURCES.values()), replace=False)
    pos = 0
    df["forced_win"] = False
    for s, k in TINY_SOURCES.items():
        idx = chosen[pos:pos + k]
        pos += k
        df.loc[idx, "lead_source"] = s
        df.loc[idx, "forced_win"] = True
    df["first_touch_date"] = [config.WINDOW_START + timedelta(days=int(d)) for d in df.first_touch_day]
    return df


def _zfit(df: pd.DataFrame) -> np.ndarray:
    w = df.specialty_focus.map(config.SPECIALTY_WEIGHTS).to_numpy()
    vol = np.minimum(1, np.log1p(df.size_producers) / np.log1p(config.VOLUME_PRODUCER_CAP))
    esn = np.minimum(1, df.es_submissions_py / config.ES_SUBMISSIONS_CAP) * 0.5 + \
        df.es_appetite.map({"high": 1, "medium": 0.6, "low": 0.25, "none": 0}).to_numpy() * 0.5
    geo = df.state.map(lambda s: 1.0 if s in config.PRIORITY_STATES else 0.6 if s in config.SECONDARY_STATES else 0.3).to_numpy()
    raw = 0.35 * w + 0.25 * vol + 0.25 * esn + 0.15 * geo
    return (raw - raw.mean()) / raw.std()


def _simulate(rng, ag: pd.DataFrame, a_arm, b_arm):
    touches, subs, b_assign = [], [], []
    z = _zfit(ag)
    n_sub = 0
    for k, r in enumerate(ag.itertuples(index=False)):
        aid, owner = r.agency_id, r.owner
        ft = datetime.combine(r.first_touch_date, datetime.min.time())
        src = r.lead_source
        oeff = OWNER_EFFECT[r.owner_idx]
        icp = bool(r.is_icp)
        inbound = src == "inbound_web"

        def touch(when, channel, ttype, direction="outbound"):
            if when <= END:
                touches.append((aid, _ts(when), channel, ttype, direction, owner))

        # -- engagement ------------------------------------------------------------------------
        if icp:
            p_eng = expit(INT_ENG + 1.1 * z[k] + SRC_ENG[src] + oeff)
        else:
            p_eng = NONICP_ENG_P
        if r.forced_win:
            p_eng = 1.0
        eng = rng.random() < p_eng
        eng_lag = 0 if inbound else int(rng.integers(0, 11))
        q = float(np.clip(rng.beta(2, 3) + 0.08 * z[k], 0.02, 1.0))
        engaged_at = _rand_time(rng, ft + timedelta(days=eng_lag)) if eng else None
        if eng and engaged_at > END:  # engagement would fall after the as-of date: not observable
            eng, engaged_at = False, None

        # -- outbound volume (sent touches: NOT featured as success metrics) ---------------------
        t0 = _rand_time(rng, ft)
        if inbound:
            touch(t0, "web", "inbound_form", "inbound")
        else:
            touch(t0, "email", "email_sent")
        for off in np.sort(rng.integers(1, 36, int(rng.integers(1, 6)))):
            touch(_rand_time(rng, ft + timedelta(days=int(off))), "email", "email_sent")
        if src == "linkedin":
            touch(_rand_time(rng, ft), "linkedin", "linkedin_connect_sent")
            if rng.random() < 0.35:
                touch(_rand_time(rng, ft + timedelta(days=int(rng.integers(2, 7)))), "linkedin", "linkedin_connect_accepted", "inbound")
            for _ in range(int(rng.integers(0, 3))):
                touch(_rand_time(rng, ft + timedelta(days=int(rng.integers(3, 25)))), "linkedin", "linkedin_message_sent")
        if src in ("outbound", "event") or rng.random() < 0.15:
            for _ in range(int(rng.integers(0, 4))):
                touch(_rand_time(rng, ft + timedelta(days=int(rng.integers(1, 30)))), "call", "call_attempt")
            if rng.random() < 0.2:
                touch(_rand_time(rng, ft + timedelta(days=int(rng.integers(1, 30)))), "call", "call_connected", "inbound")

        had_reply = had_meeting = False
        if eng:
            ea = engaged_at
            first_type = str(rng.choice(["email_open", "email_click", "reply", "meeting_booked"], p=[0.5, 0.15, 0.25, 0.10]))
            if first_type in ("reply", "meeting_booked"):
                had_reply = True
            had_meeting = first_type == "meeting_booked"
            touch(ea, "email" if first_type != "meeting_booked" else "meeting", first_type, "inbound")
            for _ in range(int(rng.poisson(1.2 + 1.6 * q))):
                touch(ea + timedelta(days=int(rng.integers(0, 25)), hours=int(rng.integers(0, 6))), "email", "email_open", "inbound")
            for _ in range(int(rng.poisson(0.7 * q))):
                touch(ea + timedelta(days=int(rng.integers(0, 25)), hours=int(rng.integers(0, 6))), "email", "email_click", "inbound")
            if rng.random() < 0.3 + 0.4 * q:
                had_reply = True
                touch(ea + timedelta(days=int(rng.integers(0, 15)), hours=2), "email", "reply", "inbound")
            if rng.random() < 0.18 + 0.4 * q:
                had_meeting = True
                mb = ea + timedelta(days=int(rng.integers(0, 14)), hours=1)
                touch(mb, "meeting", "meeting_booked", "inbound")
                if rng.random() < 0.8:
                    touch(mb + timedelta(days=int(rng.integers(1, 8))), "meeting", "meeting_held", "inbound")

        # -- first complete submission ------------------------------------------------------------
        first_sub_at = None
        will_submit = False
        if eng and icp:
            logit = INT_SUB + 0.9 * z[k] + SRC_SUB[src] + 0.5 * had_reply + 0.7 * had_meeting + 0.8 * (q - 0.4) + oeff
            p_sub = float(expit(logit))
            if a_arm[k] == "treatment":
                p_sub = min(0.97, p_sub * (1 + A_TRUE_LIFT))
            will_submit = bool(rng.random() < p_sub) or bool(r.forced_win)
            q14 = Q14_BASE * (1 + B_TRUE_LIFT) if b_arm[k] == "treatment" else Q14_BASE
            if r.forced_win:
                lag = int(rng.integers(1, 15))
            elif rng.random() < q14:
                lag = int(rng.integers(1, 15))
            else:
                lag = int(rng.integers(15, 61))
            if will_submit:
                first_sub_at = _rand_time(rng, engaged_at + timedelta(days=lag))
                if first_sub_at > END:
                    first_sub_at = None
        if eng and icp:
            b_assign.append((aid, b_arm[k], engaged_at.date()))

        # -- submission timeline: active/dormant/revive cycles ---------------------------------------
        complete_times: list[tuple[datetime, bool]] = []  # (when, is_first)
        if first_sub_at is not None:
            complete_times.append((first_sub_at, True))
            lam = REPEAT_RATE_PER_DAY * np.exp(0.5 * z[k] + 0.6 * SRC_BIND[src] + 0.3 * oeff)
            t = first_sub_at
            sticky = rng.random() < P_STICKY or r.forced_win
            active_until = None if sticky else t + timedelta(days=float(rng.exponential(ACTIVE_MEAN_DAYS)))
            while True:
                t = t + timedelta(days=float(rng.exponential(1 / lam)))
                if t > END:
                    break
                if active_until is not None and t > active_until:
                    # dormant: revive after exponential gap
                    t = active_until + timedelta(days=float(rng.exponential(1 / REVIVE_RATE_PER_DAY)))
                    if t > END:
                        break
                    active_until = t + timedelta(days=float(rng.exponential(ACTIVE_MEAN_DAYS)))
                    complete_times.append((t.replace(hour=int(rng.integers(8, 18)), minute=int(rng.integers(0, 60)), second=0, microsecond=0), False))
                    continue
                complete_times.append((t.replace(hour=int(rng.integers(8, 18)), minute=int(rng.integers(0, 60)), second=0, microsecond=0), False))

        lines = r.commercial_lines.split("|")
        bound_before = False

        def new_sub(when, complete, first):
            nonlocal n_sub, bound_before
            n_sub += 1
            cx = str(rng.choice(["low", "medium", "high"], p=COMPLEXITY_P))
            row = dict(agency_id=aid, submitted_at=when, line_of_business=str(rng.choice(lines)), risk_complexity=cx)
            req = list(funnel.REQUIRED_SUBMISSION_FIELDS)
            if complete:
                for f in req:
                    row[f] = 1
            else:
                missing = rng.choice(req, int(rng.integers(1, 3)), replace=False)
                for f in req:
                    row[f] = 0 if f in missing else 1
            row["has_cois"] = int(rng.random() < 0.7)
            row["has_financials"] = int(rng.random() < 0.6)
            row["is_complete"] = int(complete)
            row.update(quoted_at=None, bound_at=None, quote_turnaround_hours=None, outcome="incomplete",
                       premium=None, commission=None)
            if not complete:
                return row
            if rng.random() < P_DECLINE[cx] and not r.forced_win:
                row["outcome"] = "declined"
                return row
            hours = max(1.0, float(rng.lognormal(np.log(TAT_MEDIAN_H[cx]), 0.5)))
            quoted_at = when + timedelta(hours=hours)
            if quoted_at > END:
                row["outcome"] = "pending"
                return row
            row["quoted_at"] = quoted_at
            row["quote_turnaround_hours"] = round(hours, 1)
            prem = float(np.clip(rng.lognormal(np.log(14000), 0.8) * PREM_MULT[cx], 2000, 400000))
            row["premium"] = round(prem, 0)
            row["outcome"] = "quoted_not_bound"
            pb = float(expit(INT_BIND + 0.6 * z[k] + SRC_BIND[src] + 0.4 * oeff - 0.3 * (cx == "high") + (0.4 if bound_before else 0)))
            if r.forced_win and first:
                pb = 1.0
            if rng.random() < pb:
                bound_at = quoted_at + timedelta(days=float(rng.uniform(1, 14)))
                if bound_at <= END:
                    row["bound_at"] = bound_at.replace(microsecond=0)
                    row["outcome"] = "bound"
                    row["commission"] = round(prem * float(rng.uniform(0.10, 0.15)), 0)
                    bound_before = True
            return row

        # optional incomplete attempt before the first complete submission
        if first_sub_at is not None and rng.random() < P_FIRST_INCOMPLETE:
            when = max(engaged_at, first_sub_at - timedelta(days=int(rng.integers(2, 9))))
            if when < first_sub_at:
                subs.append(new_sub(when, False, False))
        elif eng and icp and first_sub_at is None and not will_submit and rng.random() < 0.06:
            when = _rand_time(rng, engaged_at + timedelta(days=int(rng.integers(2, 30))))
            if when <= END:
                subs.append(new_sub(when, False, False))
        for when, first in complete_times:
            subs.append(new_sub(when, True, first))
            # some repeat submissions arrive incomplete as well
            if not first and rng.random() < 0.10:
                w2 = when - timedelta(days=int(rng.integers(1, 4)))
                subs.append(new_sub(w2, False, False))
    return touches, subs, b_assign


def _frames(touches, subs):
    t = pd.DataFrame(touches, columns=["agency_id", "touched_at", "channel", "touch_type", "direction", "owner"])
    for row in subs:  # format timestamps before building the frame (avoids NaT coercion)
        for c in ("submitted_at", "quoted_at", "bound_at"):
            row[c] = _ts(row[c]) if isinstance(row[c], datetime) else None
    return t, pd.DataFrame(subs)


def _blocked_arms(rng, strata: np.ndarray) -> np.ndarray:
    """Stratified (blocked) 50/50 randomization: within each stratum arms alternate after a random shuffle."""
    arms = np.empty(len(strata), dtype=object)
    for key in sorted(set(strata)):
        idx = np.where(strata == key)[0]
        idx = rng.permutation(idx)
        first = int(rng.integers(0, 2))
        for j, i in enumerate(idx):
            arms[i] = "treatment" if (j + first) % 2 == 0 else "control"
    return arms.astype(str)


def generate(root: Path | str | None = None, seed: int | None = None, n_agencies: int | None = None,
             write: bool = True) -> dict:
    """Generate dirty raw CSVs + manifest. Returns in-memory frames, incl. pre-defect truth (tests only)."""
    paths = config.get_paths(root).ensure()
    seed = config.SEED if seed is None else seed
    n = n_agencies or config.N_TRUE_AGENCIES
    rng = np.random.default_rng(seed)

    ag = _true_agencies(rng, n)
    strata = (ag.lead_source.astype(str) + "|" + ag.is_icp.astype(str) + "|"
              + pd.qcut(_zfit(ag), 3, labels=False).astype(str)).to_numpy()
    a_arm = _blocked_arms(rng, strata)
    b_arm = _blocked_arms(rng, strata)
    ag["outreach_sequence"] = np.where(a_arm == "treatment", "ICP-Targeted v2", "Standard v1")
    touches, subs, b_assign = _simulate(rng, ag, a_arm, b_arm)
    t, s = _frames(touches, subs)

    # ---- experiment assignments (A: everyone at first touch; B: engaged ICP at engagement; C: dormant at T0)
    ass = [("A", aid, arm, d.isoformat()) for aid, arm, d in zip(ag.agency_id, a_arm, ag.first_touch_date)]
    ass += [("B", aid, arm, d.isoformat()) for aid, arm, d in b_assign]
    sc = s[s.is_complete == 1].copy()
    sc["d"] = pd.to_datetime(sc.submitted_at)
    t0 = pd.Timestamp(config.REACTIVATION_T0)
    last_before = sc[sc.d <= t0].groupby("agency_id")["d"].max()
    elig = last_before[last_before <= t0 - pd.Timedelta(days=config.DORMANCY_DAYS)].index.tolist()
    c_arms = np.where(rng.permutation(len(elig)) % 2 == 0, "treatment", "control")
    own = ag.set_index("agency_id")["owner"]
    extra = []
    for aid, arm in zip(elig, c_arms):
        ass.append(("C", aid, str(arm), config.REACTIVATION_T0.isoformat()))
        if arm == "treatment":  # reactivation outreach touches (no causal effect by design)
            base = datetime.combine(config.REACTIVATION_T0, datetime.min.time())
            for off in (0, 7, 14):
                extra.append((aid, _ts(_rand_time(rng, base + timedelta(days=off))), "email", "email_sent", "outbound", own[aid]))
            if rng.random() < 0.35:
                extra.append((aid, _ts(_rand_time(rng, base + timedelta(days=int(rng.integers(1, 20))))), "email", "email_open", "inbound", own[aid]))
    if extra:
        t = pd.concat([t, pd.DataFrame(extra, columns=t.columns)], ignore_index=True)
    ass = pd.DataFrame(ass, columns=["experiment_id", "agency_id", "arm", "assigned_at"])
    ass = ass.sort_values(["experiment_id", "agency_id"]).reset_index(drop=True)
    ass.insert(0, "assignment_id", [f"AS-{i:05d}" for i in range(1, len(ass) + 1)])

    # last activity (touches + submissions)
    last = pd.concat([t[["agency_id", "touched_at"]].rename(columns={"touched_at": "ts"}),
                      s[["agency_id", "submitted_at"]].rename(columns={"submitted_at": "ts"})])
    la = last.groupby("agency_id")["ts"].max().str[:10]
    ag["last_activity_date"] = ag.agency_id.map(la)

    truth = dict(agencies=ag.copy(), touches=t.copy(), submissions=s.copy(), assignments=ass.copy(),
                 a_arm=a_arm, b_arm=b_arm)

    # ---- duplicates --------------------------------------------------------------------------------
    manifest: dict = {"seed": seed, "n_true_agencies": n, "counts": {}, "details": {}}
    cand = ag[(ag.first_touch_date <= config.AS_OF - timedelta(days=100)) & (~ag.forced_win)].agency_id.to_numpy()
    n_dup = int(round(config.DUPLICATE_RATE * n))
    dup_src = rng.choice(cand, n_dup, replace=False)
    dup_rows, dup_map = [], {}
    t = t.copy()
    s = s.copy()
    for i, src_id in enumerate(sorted(dup_src)):
        o = ag[ag.agency_id == src_id].iloc[0]
        did = f"AG-{n + 1 + i:04d}"
        dup_map[did] = src_id
        row = o.to_dict()
        row["agency_id"] = did
        row["name"] = _name_variant(rng, o["name"])
        if rng.random() < 0.3:
            row["lead_source"] = str(rng.choice(list(SOURCE_WEIGHTS)))
        row["first_touch_date"] = o["first_touch_date"] + timedelta(days=int(rng.integers(7, 60)))
        dup_rows.append(row)
        # move ~25% of later children to the duplicate id
        dft = pd.Timestamp(row["first_touch_date"])
        tm = (t.agency_id == src_id) & (pd.to_datetime(t.touched_at) >= dft) & (rng.random(len(t)) < 0.25)
        t.loc[tm, "agency_id"] = did
        sm = (s.agency_id == src_id) & (pd.to_datetime(s.submitted_at) >= dft) & (rng.random(len(s)) < 0.25)
        s.loc[sm, "agency_id"] = did
    raw_ag = pd.concat([ag, pd.DataFrame(dup_rows)], ignore_index=True)
    dup_involved = set(dup_map) | set(dup_map.values())
    manifest["counts"]["duplicate_agencies"] = len(dup_map)
    manifest["details"]["duplicates"] = {k: dup_map[k] for k in sorted(dup_map)}

    # ---- agency-level defects ---------------------------------------------------------------------
    m = len(raw_ag)
    clean_pool = np.array([i for i in range(m) if raw_ag.agency_id[i] not in dup_involved])
    pick = lambda frac, pool: sorted(rng.choice(pool, int(round(frac * m)), replace=False).tolist())
    miss_state_idx = pick(config.MISSING_STATE_RATE, clean_pool)
    left = np.array(sorted(set(clean_pool.tolist()) - set(miss_state_idx)))
    miss_size_idx = pick(config.MISSING_SIZE_RATE, left)

    out = pd.DataFrame({
        "agency_id": raw_ag.agency_id, "name": raw_ag.name, "state": raw_ag.state,
        "size_producers": raw_ag.size_producers.astype(str), "commercial_lines": raw_ag.commercial_lines,
        "specialty_focus": raw_ag.specialty_focus, "es_appetite": raw_ag.es_appetite,
        "es_submissions_py": raw_ag.es_submissions_py, "prior_bind_rate_pct": raw_ag.prior_bind_rate_pct.astype(object),
        "lead_source": raw_ag.lead_source, "first_touch_date": raw_ag.first_touch_date.map(lambda d: d.isoformat()),
        "last_activity_date": raw_ag.last_activity_date, "owner": raw_ag.owner,
        "outreach_sequence": raw_ag.outreach_sequence,
    })
    blank_states = ["", "N/A", "unknown"]
    out.loc[miss_state_idx, "state"] = [blank_states[int(x)] for x in rng.integers(0, 3, len(miss_state_idx))]
    out.loc[miss_size_idx, "size_producers"] = ["" if x < 0.7 else "n/a" for x in rng.random(len(miss_size_idx))]
    manifest["counts"]["missing_state"] = len(miss_state_idx)
    manifest["counts"]["missing_size"] = len(miss_size_idx)
    manifest["details"]["missing_state_ids"] = out.loc[miss_state_idx, "agency_id"].tolist()
    manifest["details"]["missing_size_ids"] = out.loc[miss_size_idx, "agency_id"].tolist()

    # mixed size formats (range strings, text, float strings)
    fmt_pool = [i for i in range(m) if i not in set(miss_size_idx)]
    fmt_idx = sorted(rng.choice(fmt_pool, int(0.30 * m), replace=False).tolist())
    nfmt = 0
    for i in fmt_idx:
        v = int(raw_ag.size_producers[i])
        kind = rng.random()
        if kind < 0.6:
            out.at[i, "size_producers"] = _size_bucket_label(v)
        elif kind < 0.8:
            out.at[i, "size_producers"] = f"{v} producers"
        else:
            out.at[i, "size_producers"] = f"{v}.0"
        nfmt += 1
    manifest["counts"]["mixed_size_formats"] = nfmt
    manifest["details"]["mixed_size_ids"] = out.loc[fmt_idx, "agency_id"].tolist()

    # inconsistent source labels
    lab_idx = sorted(rng.choice(m, int(0.30 * m), replace=False).tolist())
    nlab = 0
    for i in lab_idx:
        canon = out.at[i, "lead_source"]
        label = str(rng.choice(SOURCE_LABEL_VARIANTS[canon]))
        assert label != canon
        out.at[i, "lead_source"] = label
        nlab += 1
    manifest["counts"]["inconsistent_source_labels"] = nlab
    # a tiny share also arrives with canonical-looking case/whitespace noise: already covered by variants

    # impossible: prior bind rate > 100
    br_pool = [i for i in range(m)]
    br_idx = sorted(rng.choice(br_pool, 6, replace=False).tolist())
    for i in br_idx:
        out.at[i, "prior_bind_rate_pct"] = round(float(rng.uniform(105, 160)), 1)
    manifest["counts"]["bind_rate_over_100"] = len(br_idx)
    manifest["details"]["bind_rate_over_100_ids"] = out.loc[br_idx, "agency_id"].tolist()

    # impossible: submission timestamp / turnaround defects
    safe = s.submitted_at >= _ts(START + timedelta(days=5))  # keep injected timestamps inside the window
    quoted = s.index[s.quoted_at.notna() & safe & (s.is_complete == 1)].to_numpy()
    bound = s.index[s.bound_at.notna() & safe].to_numpy()
    q_bs = sorted(rng.choice(quoted, 5, replace=False).tolist())
    b_bq = sorted(rng.choice([i for i in bound if i not in q_bs], 4, replace=False).tolist())
    neg = sorted(rng.choice([i for i in quoted if i not in q_bs and i not in b_bq], 8, replace=False).tolist())
    s = s.copy()
    for i in q_bs:
        sub_at = datetime.strptime(s.at[i, "submitted_at"], FMT)
        hrs = float(rng.uniform(1, 48))
        s.at[i, "quoted_at"] = _ts(sub_at - timedelta(hours=hrs))
        s.at[i, "quote_turnaround_hours"] = round(-hrs, 1)
        s.at[i, "bound_at"] = None
    for i in b_bq:
        q_at = datetime.strptime(s.at[i, "quoted_at"], FMT)
        s.at[i, "bound_at"] = _ts(q_at - timedelta(hours=float(rng.uniform(1, 72))))
    for i in neg:
        s.at[i, "quote_turnaround_hours"] = -abs(float(s.at[i, "quote_turnaround_hours"]))
    manifest["counts"]["quote_before_submission"] = len(q_bs)
    manifest["counts"]["bound_before_quote"] = len(b_bq)
    manifest["counts"]["negative_turnaround"] = len(neg)
    # NOTE: submission ids are assigned below; store positional keys and resolve after sorting
    s_flags = {"quote_before_submission": q_bs, "bound_before_quote": b_bq, "negative_turnaround": neg}

    # ---- stable ids + ordering ----------------------------------------------------------------------
    s = s.sort_values(["submitted_at", "agency_id", "line_of_business"]).reset_index()
    idmap = {int(old): f"SB-{i + 1:05d}" for i, old in enumerate(s["index"])}
    s.insert(0, "submission_id", [idmap[int(o)] for o in s["index"]])
    s = s.drop(columns="index")
    for k, v in s_flags.items():
        manifest["details"][k + "_ids"] = sorted(idmap[i] for i in v)
    t = t.sort_values(["touched_at", "agency_id", "touch_type"]).reset_index(drop=True)
    t.insert(0, "touch_id", [f"TC-{i + 1:06d}" for i in range(len(t))])

    tiny = {src: out.loc[out.agency_id.isin(ag[ag.lead_source == src].agency_id), "agency_id"].tolist()
            for src in TINY_SOURCES}
    manifest["counts"]["tiny_n_sources"] = len(TINY_SOURCES)
    manifest["counts"]["tiny_n_source_agencies"] = sum(len(v) for v in tiny.values())
    manifest["details"]["tiny_n_sources"] = tiny
    manifest["n_agency_rows"] = len(out)
    manifest["ground_truth"] = {
        "experiment_A": {"description": "ICP-targeted outbound vs standard outbound", "metric": "first complete submission within 60d of first touch",
                         "true_relative_lift": A_TRUE_LIFT},
        "experiment_B": {"description": "submission-ready onboarding vs standard onboarding", "metric": "complete submission within 14d of engagement",
                         "true_relative_lift": B_TRUE_LIFT},
        "experiment_C": {"description": "reactivation outreach vs no-outreach holdout", "metric": "complete submission within 45d of T0",
                         "true_relative_lift": C_TRUE_LIFT},
        "source_quality": {"highest_quality_low_volume": "referral", "high_volume_low_quality": "linkedin"},
        "note": "SYNTHETIC. Planted effects are plumbing tests, not findings.",
    }

    raw = dict(agencies=out, touches=t, submissions=s, experiment_assignments=ass)
    if write:
        for name, df in raw.items():
            df.to_csv(paths.raw / f"{name}.csv", index=False)
        (paths.raw / "injected_defects.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n")
    return dict(raw=raw, manifest=manifest, truth=truth)
