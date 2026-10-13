"""Cleaning and standardization of the dirty SYNTHETIC raw tables.

Decision rules (also in DECISIONS.md / outputs/data_quality_report.md):

* Duplicates: block on state; compare normalized agency-name cores with difflib ratio >=
  config.DEDUPE_THRESHOLD; union-find clusters; keep the EARLIEST record (first_touch_date, then id);
  remap child rows. Agencies with a missing state are never auto-merged (state is the blocking key).
* Source labels: explicit mapping table (SOURCE_MAP); an unmapped label is an error, never a guess.
* Size: mixed formats parsed to an integer (range -> floor midpoint, "51+" -> 51); missing ->
  IMPUTED with the median of the same specialty focus and FLAGGED (size_imputed=1).
* State: missing -> 'UNK' and FLAGGED (state_missing=1); scoring gives unknown geography 0.
* prior_bind_rate_pct outside [0,100]: value set to NULL and written to quarantine.csv.
* negative quote turnaround with sane timestamps: REPAIRED (recomputed from timestamps).
* quote before submission / bound before quote / bound without quote: row QUARANTINED
  (the true timestamp cannot be known), excluded from clean tables.
* Tiny-n sources are kept but their rates are suppressed in metrics (config.MIN_N).

The cleaner never reads data/raw/injected_defects.json.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd

import config
from . import funnel, schema

STOPWORDS = {"the", "and", "&", "insurance", "ins", "agency", "agcy", "group", "grp", "risk", "advisors",
             "advisor", "services", "svcs", "brokers", "brokerage", "brkrs", "associates", "assoc",
             "partners", "prtnrs", "llc", "inc", "co", "company", "corp"}

MISSING_TOKENS = {"", "n/a", "na", "unknown", "null", "none", "unk", "nan"}

SOURCE_MAP = {  # normalized label -> canonical source (explicit mapping table)
    "linkedin": "linkedin", "li": "linkedin", "linked in": "linkedin", "linkedin outreach": "linkedin",
    "outbound": "outbound", "outbound email": "outbound", "cold email": "outbound",
    "inbound web": "inbound_web", "inbound_web": "inbound_web", "web": "inbound_web",
    "website": "inbound_web", "website inbound": "inbound_web",
    "partner": "partner", "partnership": "partner", "partner channel": "partner",
    "event": "event", "conference": "event", "trade show": "event",
    "referral": "referral", "ref": "referral", "broker referral": "referral",
    "podcast sponsor": "podcast_sponsor", "podcast_sponsor": "podcast_sponsor",
    "state assoc booth": "state_assoc_booth", "state_assoc_booth": "state_assoc_booth",
    "wholesaler alumni": "wholesaler_alumni", "wholesaler_alumni": "wholesaler_alumni",
}
CANONICAL_SOURCES = tuple(sorted(set(SOURCE_MAP.values())))


def core_name(name: str) -> str:
    """Normalized core used for fuzzy matching: lowercase, strip punctuation + generic agency words."""
    toks = re.sub(r"[^a-z0-9& ]", " ", str(name).lower()).split()
    toks = [t for t in toks if t not in STOPWORDS and t != "&"]
    return " ".join(toks)


def _norm_label(x: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(x).lower()).strip()


def canonical_source(label: str) -> str:
    key = _norm_label(label)
    if key not in SOURCE_MAP:
        raise ValueError(f"Unmapped lead source label {label!r}; add it to SOURCE_MAP explicitly.")
    return SOURCE_MAP[key]


def size_bucket(n: int) -> str:
    for lo, hi, lab in ((1, 2, "1-2"), (3, 5, "3-5"), (6, 10, "6-10"), (11, 25, "11-25"), (26, 50, "26-50")):
        if lo <= n <= hi:
            return lab
    return "51+"


def parse_size(x) -> float:
    """Parse mixed size formats to a number; NaN if missing/unparseable."""
    s = str(x).strip().lower()
    if s in MISSING_TOKENS:
        return np.nan
    m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", s)
    if m:
        return float((int(m.group(1)) + int(m.group(2))) // 2)
    m = re.fullmatch(r"(\d+)\s*\+", s)
    if m:
        return float(m.group(1))
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(int(float(m.group(0)))) if m else np.nan


def is_plain_int(x) -> bool:
    return bool(re.fullmatch(r"\d+", str(x).strip()))


# ---------------------------------------------------------------------------------------------
# dedupe
# ---------------------------------------------------------------------------------------------
def dedupe_agencies(ag: pd.DataFrame, threshold: float | None = None) -> pd.DataFrame:
    """Return DataFrame[agency_id, survivor_id, similarity] for every agency (survivor==self if kept)."""
    threshold = config.DEDUPE_THRESHOLD if threshold is None else threshold
    ids = ag["agency_id"].tolist()
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    sim: dict[str, float] = {}
    work = ag.assign(_core=ag["name"].map(core_name))
    for state, blk in work.groupby("state"):
        if str(state).upper() == "UNK":  # state is the blocking key: unresolvable
            continue
        rows = blk[["agency_id", "_core"]].to_numpy().tolist()
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i][1], rows[j][1]
                if not a or not b:
                    continue
                sm = SequenceMatcher(None, a, b)
                if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
                    continue
                r = sm.ratio()
                if r >= threshold:
                    ra, rb = find(rows[i][0]), find(rows[j][0])
                    if ra != rb:
                        parent[rb] = ra
                    sim[rows[j][0]] = max(sim.get(rows[j][0], 0), r)
                    sim[rows[i][0]] = max(sim.get(rows[i][0], 0), r)
    order = work.set_index("agency_id")[["first_touch_date"]]
    clusters: dict[str, list[str]] = {}
    for i in ids:
        clusters.setdefault(find(i), []).append(i)
    surv = {}
    for members in clusters.values():
        best = min(members, key=lambda m: (str(order.at[m, "first_touch_date"]), m))
        for m in members:
            surv[m] = best
    out = pd.DataFrame({"agency_id": ids, "survivor_id": [surv[i] for i in ids]})
    out["similarity"] = out["agency_id"].map(sim).fillna(1.0).round(4)
    return out


# ---------------------------------------------------------------------------------------------
# main cleaning
# ---------------------------------------------------------------------------------------------
@dataclass
class CleanResult:
    agencies: pd.DataFrame
    touches: pd.DataFrame
    submissions: pd.DataFrame
    assignments: pd.DataFrame
    stage_events: pd.DataFrame
    quarantine: pd.DataFrame
    dedupe_map: pd.DataFrame
    stats: dict = field(default_factory=dict)


def _as_str_frame(df: pd.DataFrame) -> pd.DataFrame:
    return df.astype("object").where(df.notna(), "").astype(str)


def clean_tables(raw: dict[str, pd.DataFrame]) -> CleanResult:
    """Pure function: raw (possibly dirty) tables -> clean tables + quarantine + stats."""
    ag_raw = _as_str_frame(raw["agencies"])
    tc = _as_str_frame(raw["touches"])
    sb = _as_str_frame(raw["submissions"])
    asg = _as_str_frame(raw["experiment_assignments"])
    quarantine: list[dict] = []
    stats: dict = {"before": {}, "handled": {}, "after": {}}
    B, H, A = stats["before"], stats["handled"], stats["after"]

    # ---------------- agencies ----------------
    ag = ag_raw.copy()
    ag["name"] = ag["name"].str.replace(r"\s+", " ", regex=True).str.strip()
    # source
    B["inconsistent_source_labels"] = int((~ag["lead_source"].isin(CANONICAL_SOURCES)).sum())
    ag["lead_source"] = ag["lead_source"].map(canonical_source)
    H["inconsistent_source_labels"] = B["inconsistent_source_labels"]
    # state
    st = ag["state"].str.strip()
    miss_state = st.str.lower().isin(MISSING_TOKENS)
    prior_flag = ag["state_missing"].astype(str).isin(["1", "1.0"]) if "state_missing" in ag else False
    B["missing_state"] = int(miss_state.sum())
    ag["state"] = st.str.upper().where(~miss_state, "UNK")
    ag["state_missing"] = (miss_state | prior_flag).astype(int)
    H["missing_state"] = B["missing_state"]
    # size
    B["mixed_size_formats"] = int(sum(1 for x in ag["size_producers"]
                                      if not is_plain_int(x) and str(x).strip().lower() not in MISSING_TOKENS))
    parsed = ag["size_producers"].map(parse_size)
    B["missing_size"] = int(parsed.isna().sum())
    prior_imp = ag["size_imputed"].astype(str).isin(["1", "1.0"]) if "size_imputed" in ag else pd.Series(False, index=ag.index)
    med = parsed.groupby(ag["specialty_focus"]).transform("median")
    overall = parsed.median()
    filled = parsed.fillna(med).fillna(overall).round()
    ag["size_imputed"] = (parsed.isna() | prior_imp).astype(int)
    ag["size_producers"] = filled.astype(int)
    ag["size_bucket"] = ag["size_producers"].map(size_bucket)
    H["mixed_size_formats"] = B["mixed_size_formats"]
    H["missing_size"] = int(parsed.isna().sum())
    # numeric columns
    ag["es_submissions_py"] = pd.to_numeric(ag["es_submissions_py"], errors="coerce").fillna(0).astype(int)
    pbr = pd.to_numeric(ag["prior_bind_rate_pct"], errors="coerce")
    bad = (pbr > 100) | (pbr < 0)
    B["bind_rate_over_100"] = int(bad.sum())
    for aid, v in zip(ag.loc[bad, "agency_id"], pbr[bad]):
        quarantine.append(dict(table="agencies", record_id=aid, issue="bind_rate_out_of_range", action="value_nullified",
                               detail=f"prior_bind_rate_pct={v}"))
    ag["prior_bind_rate_pct"] = pbr.where(~bad)
    H["bind_rate_over_100"] = int(bad.sum())

    # dedupe
    dmap = dedupe_agencies(ag)
    B["duplicate_agencies"] = int((dmap["agency_id"] != dmap["survivor_id"]).sum())
    surv = dict(zip(dmap["agency_id"], dmap["survivor_id"]))
    H["duplicate_agencies"] = B["duplicate_agencies"]
    first_touch_min = ag.groupby(ag["agency_id"].map(surv))["first_touch_date"].min()
    keep = ag[ag["agency_id"] == ag["agency_id"].map(surv)].copy()
    keep["first_touch_date"] = keep["agency_id"].map(first_touch_min)

    # ---------------- children remap ----------------
    tc["agency_id"] = tc["agency_id"].map(surv)
    sb["agency_id"] = sb["agency_id"].map(surv)
    asg["agency_id"] = asg["agency_id"].map(surv)
    asg = asg.drop_duplicates(["experiment_id", "agency_id"], keep="first")

    # ---------------- submissions ----------------
    for c in ("premium", "commission", "quote_turnaround_hours"):
        sb[c] = pd.to_numeric(sb[c], errors="coerce")
    for c in ("submitted_at", "quoted_at", "bound_at"):
        sb[c] = pd.to_datetime(sb[c].replace("", np.nan))
    for f in funnel.FULL_CHECKLIST:
        sb[f] = pd.to_numeric(sb[f], errors="coerce").fillna(0).astype(int)
    sb["is_complete"] = sb[list(funnel.REQUIRED_SUBMISSION_FIELDS)].min(axis=1).astype(int)

    qbs = sb["quoted_at"].notna() & (sb["quoted_at"] < sb["submitted_at"])
    bbq = sb["bound_at"].notna() & sb["quoted_at"].notna() & (sb["bound_at"] < sb["quoted_at"]) & ~qbs
    bwq = sb["bound_at"].notna() & sb["quoted_at"].isna()
    neg = (sb["quote_turnaround_hours"] < 0) & ~qbs
    B["quote_before_submission"], B["bound_before_quote"] = int(qbs.sum()), int(bbq.sum())
    B["negative_turnaround"] = int(neg.sum())
    B["bound_without_quote"] = int(bwq.sum())
    for mask, issue in ((qbs, "quote_before_submission"), (bbq, "bound_before_quote"), (bwq, "bound_without_quote")):
        for sid in sb.loc[mask, "submission_id"]:
            quarantine.append(dict(table="submissions", record_id=sid, issue=issue, action="row_quarantined",
                                   detail="true timestamp unknowable; row excluded from clean tables"))
    for sid in sb.loc[neg, "submission_id"]:
        quarantine.append(dict(table="submissions", record_id=sid, issue="negative_turnaround", action="repaired",
                               detail="recomputed from quoted_at - submitted_at (not excluded)"))
    fix_hours = ((sb["quoted_at"] - sb["submitted_at"]).dt.total_seconds() / 3600).round(1)
    sb.loc[neg, "quote_turnaround_hours"] = fix_hours[neg]
    H["quote_before_submission"], H["bound_before_quote"] = int(qbs.sum()), int(bbq.sum())
    H["negative_turnaround"] = int(neg.sum())
    H["bound_without_quote"] = int(bwq.sum())
    drop = qbs | bbq | bwq
    sb_clean = sb[~drop].copy()
    # outcome consistency (derived field recomputed from timestamps)
    sb_clean["outcome"] = np.select(
        [sb_clean["is_complete"] == 0, sb_clean["bound_at"].notna(), sb_clean["quoted_at"].notna()],
        ["incomplete", "bound", "quoted_not_bound"],
        default=sb_clean["outcome"].where(sb_clean["outcome"].isin(["declined", "pending"]), "pending"))
    for c in ("submitted_at", "quoted_at", "bound_at"):
        sb_clean[c] = sb_clean[c].dt.strftime("%Y-%m-%d %H:%M:%S")
        sb_clean[c] = sb_clean[c].where(sb_clean[c].notna(), None)
    sb_clean = sb_clean.sort_values("submission_id").reset_index(drop=True)

    # ---------------- touches ----------------
    tc = tc.sort_values("touch_id").reset_index(drop=True)

    # ---------------- derived agency fields ----------------
    last = pd.concat([tc[["agency_id", "touched_at"]].rename(columns={"touched_at": "ts"}),
                      sb_clean[["agency_id", "submitted_at"]].rename(columns={"submitted_at": "ts"})])
    la = last.groupby("agency_id")["ts"].max().str[:10]
    keep["last_activity_date"] = keep["agency_id"].map(la).fillna(keep["first_touch_date"])
    keep["is_icp"] = [int(funnel.is_icp(r)) for r in keep.to_dict("records")]
    cols = schema.column_names("agencies")
    keep = keep[cols].sort_values("agency_id").reset_index(drop=True)
    A["duplicate_agencies"] = int(dedupe_agencies(keep)["agency_id"].ne(dedupe_agencies(keep)["survivor_id"]).sum())

    asg = asg[schema.column_names("experiment_assignments")].sort_values("assignment_id").reset_index(drop=True)
    sb_clean = sb_clean[schema.column_names("submissions")]
    tc = tc[schema.column_names("touches")]

    ev = funnel.derive_stage_events(keep, tc, sb_clean)

    A["inconsistent_source_labels"] = int((~keep["lead_source"].isin(CANONICAL_SOURCES)).sum())
    A["mixed_size_formats"] = int((~keep["size_producers"].map(is_plain_int)).sum())
    A["missing_size_unflagged"] = int((keep["size_producers"].isna()).sum())
    A["bind_rate_over_100"] = int((keep["prior_bind_rate_pct"] > 100).sum())
    A["missing_state_unflagged"] = int(((keep["state"] == "UNK") & (keep["state_missing"] == 0)).sum())
    issues = [funnel.validate_submission(r) for r in sb_clean.to_dict("records")]
    A["impossible_submission_values"] = int(sum(1 for i in issues if i))
    A["quote_before_submission"] = A["bound_before_quote"] = A["negative_turnaround"] = A["impossible_submission_values"]
    n_by_src = keep.groupby("lead_source").size()
    stats["tiny_n_sources"] = {k: int(v) for k, v in n_by_src[n_by_src < config.MIN_N].items()}
    stats["rows"] = {
        "agencies": (len(ag_raw), len(keep)), "touches": (len(raw["touches"]), len(tc)),
        "submissions": (len(raw["submissions"]), len(sb_clean)),
        "experiment_assignments": (len(raw["experiment_assignments"]), len(asg))}
    q = pd.DataFrame(quarantine, columns=["table", "record_id", "issue", "action", "detail"])
    q = q.sort_values(["table", "issue", "record_id"]).reset_index(drop=True)
    return CleanResult(keep, tc, sb_clean, asg, ev, q, dmap[dmap.agency_id != dmap.survivor_id].reset_index(drop=True), stats)


def suppress_small_n(df: pd.DataFrame, n_col: str, rate_cols: list[str], min_n: int | None = None) -> pd.DataFrame:
    """Blank (NaN) rate columns whose denominator n_col < min_n and add a `suppressed` flag."""
    min_n = config.MIN_N if min_n is None else min_n
    out = df.copy()
    mask = out[n_col] < min_n
    for c in rate_cols:
        out[c] = out[c].astype(float).where(~mask)
    out["suppressed"] = mask
    return out


# ---------------------------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------------------------
def load_raw(raw_dir: Path) -> dict[str, pd.DataFrame]:
    return {n: pd.read_csv(raw_dir / f"{n}.csv", dtype=str, keep_default_na=False)
            for n in ("agencies", "touches", "submissions", "experiment_assignments")}


def write_db(res: CleanResult, db_path: Path) -> None:
    conn = schema.init_db(db_path)
    for name, df in (("agencies", res.agencies), ("touches", res.touches), ("submissions", res.submissions),
                     ("experiment_assignments", res.assignments)):
        df2 = df.astype(object).where(df.notna(), None)
        df2.to_sql(name, conn, if_exists="append", index=False)
    ev = res.stage_events.copy()
    ev["reached_at"] = pd.to_datetime(ev["reached_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    ev.to_sql("stage_events", conn, if_exists="append", index=False)
    conn.commit()
    bad = conn.execute("PRAGMA foreign_key_check").fetchall()
    if bad:
        raise RuntimeError(f"foreign key violations after load: {bad[:5]}")
    conn.close()


def write_report(res: CleanResult, path: Path, manifest: dict | None = None) -> None:
    b, h, a = res.stats["before"], res.stats["handled"], res.stats["after"]
    action = {
        "duplicate_agencies": "merged into earliest record; child rows remapped",
        "missing_state": "flagged (state='UNK', state_missing=1); geography score 0",
        "missing_size": "imputed (specialty median) + flagged (size_imputed=1)",
        "mixed_size_formats": "parsed to integer (range -> floor midpoint)",
        "inconsistent_source_labels": "mapped via explicit SOURCE_MAP",
        "bind_rate_over_100": "value nullified + logged in quarantine.csv",
        "negative_turnaround": "repaired from timestamps",
        "quote_before_submission": "row quarantined",
        "bound_before_quote": "row quarantined",
    }
    resid = {"duplicate_agencies": a["duplicate_agencies"], "missing_state": a["missing_state_unflagged"],
             "missing_size": a["missing_size_unflagged"], "mixed_size_formats": a["mixed_size_formats"],
             "inconsistent_source_labels": a["inconsistent_source_labels"], "bind_rate_over_100": a["bind_rate_over_100"],
             "negative_turnaround": a["impossible_submission_values"],
             "quote_before_submission": a["impossible_submission_values"],
             "bound_before_quote": a["impossible_submission_values"]}
    lines = ["# Data Quality Report", "",
             "> All data is SYNTHETIC. Counts come from running the cleaner's own detectors on the raw files.", "",
             "## Defects: before / after", "",
             "| Defect | Detected in raw | Handled | Residual unhandled after cleaning | Action |"]
    if manifest:
        lines[-1] += " Injected (ground truth) |"
    lines.append("|---|---|---|---|---|" + ("---|" if manifest else ""))
    for k, act in action.items():
        row = f"| {k} | {b[k]} | {h[k]} | {resid[k]} | {act} |"
        if manifest:
            row += f" {manifest['counts'].get(k, 'n/a')} |"
        lines.append(row)
    lines += ["", "## Row counts (raw -> clean)", "", "| Table | Raw | Clean |", "|---|---|---|"]
    for t, (r0, r1) in res.stats["rows"].items():
        lines.append(f"| {t} | {r0} | {r1} |")
    lines += ["", f"Quarantine file: `data/clean/quarantine.csv` ({len(res.quarantine)} entries, "
                  f"{int((res.quarantine['action'] == 'row_quarantined').sum())} rows removed, "
                  f"{int((res.quarantine['action'] == 'repaired').sum())} repaired in place, "
                  f"{int((res.quarantine['action'] == 'value_nullified').sum())} values nullified).",
              "", "## Tiny-n sources (rates suppressed below n = %d)" % config.MIN_N, ""]
    for s, n in sorted(res.stats["tiny_n_sources"].items()):
        lines.append(f"- `{s}`: n = {n} agencies. Any 100% conversion here is noise, not a finding.")
    lines += ["", "## Deduplication", "",
              f"- Rule: state-blocked, normalized-name-core similarity >= {config.DEDUPE_THRESHOLD} (difflib ratio); earliest record wins.",
              f"- Duplicates merged: {len(res.dedupe_map)}. Agencies with unknown state are never auto-merged.", ""]
    path.write_text("\n".join(lines))


def run_clean(root: Path | str | None = None) -> CleanResult:
    paths = config.get_paths(root).ensure()
    raw = load_raw(paths.raw)
    res = clean_tables(raw)
    for name, df in (("agencies", res.agencies), ("touches", res.touches), ("submissions", res.submissions),
                     ("experiment_assignments", res.assignments)):
        df.to_csv(paths.clean / f"{name}.csv", index=False)
    ev = res.stage_events.copy()
    ev["reached_at"] = pd.to_datetime(ev["reached_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    ev.to_csv(paths.clean / "stage_events.csv", index=False)
    res.quarantine.to_csv(paths.clean / "quarantine.csv", index=False)
    res.dedupe_map.to_csv(paths.clean / "dedupe_map.csv", index=False)
    write_db(res, paths.db)
    manifest = None
    mp = paths.raw / "injected_defects.json"
    if mp.exists():  # report-only: used to show ground truth next to detections, never for decisions
        import json
        manifest = json.loads(mp.read_text())
    write_report(res, paths.outputs / "data_quality_report.md", manifest)
    return res
