"""Metrics layer: every number the dashboard shows comes from a named sql/*.sql file.

REGISTRY maps metric name -> SQL file. `run_all` executes each file against the clean SQLite
database and writes data/marts/<name>.csv. All data is synthetic.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import config
from .rounding import round_df


@dataclass(frozen=True)
class Metric:
    name: str
    sql_file: str
    description: str
    nullable_cols: tuple[str, ...] = ()  # columns allowed to be NULL (suppressed rates / undefined values)


REGISTRY: dict[str, Metric] = {m.name: m for m in [
    Metric("new_icp_agencies_weekly", "new_icp_agencies_weekly.sql", "New ICP-qualified agencies entering per week"),
    Metric("funnel_counts", "funnel_counts.sql", "Nested funnel counts; observed and cohort-mature step/cumulative conversion",
           ("observed_step_conversion", "mature_window_days", "mature_base", "mature_converted", "mature_step_conversion", "mature_cumulative_conversion")),
    Metric("meeting_funnel", "meeting_funnel.sql", "Meeting diagnostic: engaged -> meeting -> submission",
           ("meeting_to_submission_rate", "engaged_to_meeting_rate", "no_meeting_to_submission_rate")),
    Metric("source_quality", "source_quality.sql", "Source quality by downstream bind/repeat, min-n suppressed",
           ("first_submission_rate", "bind_rate_per_lead", "repeat_rate_of_bound", "commission_per_lead", "observed_bind_rate", "mature_min_base")),
    Metric("time_to_quote", "time_to_quote.sql", "Median hours submission -> quote, overall/line/complexity",
           ("median_hours",)),
    Metric("dormant_reactivation", "dormant_reactivation.sql", "Dormant agencies ranked by prior premium and fit"),
    Metric("pipeline_projection", "pipeline_projection.sql", "Assumption-driven first-bind projection by segment"),
    Metric("cohort_retention", "cohort_retention.sql", "Repeat submission within 30/60/90 days of first submission",
           ("retention_30", "retention_60", "retention_90")),
    Metric("activation_rate", "activation_rate.sql", "Engaged -> first submission within 14 days",
           ("activation_rate",)),
    Metric("owner_performance", "owner_performance.sql", "Owner performance on downstream conversion",
           ("engagement_rate", "activation_rate", "bind_rate_of_submitters", "commission_per_agency")),
    Metric("weekly_growth_review", "weekly_growth_review.sql", "North star, inputs and diagnostics by week",
           ("completeness_rate", "quote_rate", "bind_rate_of_quoted")),
    Metric("topline", "topline.sql", "Monday-morning topline numbers"),
    Metric("experiment_outcomes", "experiment_outcomes.sql", "Per-assignment experiment outcomes"),
    Metric("experiment_a_icp_split", "experiment_a_icp_split.sql", "OBSERVATIONAL: first-submission rate, ICP vs non-ICP, in the A control arm"),
]}


def default_params(**overrides) -> dict:
    p = dict(
        as_of=config.AS_OF.isoformat(), window_start=config.WINDOW_START.isoformat(),
        min_n=config.MIN_N, min_n_weekly=config.MIN_N_WEEKLY, dormancy_days=config.DORMANCY_DAYS,
        open_days=config.PIPELINE_OPEN_DAYS, activation_days=config.ACTIVATION_DAYS,
        window_a=config.A_OUTCOME_DAYS,
        mat_eng=config.STAGE_MATURITY_DAYS["engaged"], mat_fs=config.STAGE_MATURITY_DAYS["first_submission"],
        mat_q=config.STAGE_MATURITY_DAYS["quoted"], mat_b=config.STAGE_MATURITY_DAYS["bound"], mat_r=config.STAGE_MATURITY_DAYS["repeat_submission"],
        window_b=config.B_OUTCOME_DAYS, window_c=config.C_OUTCOME_DAYS)
    p.update(overrides)
    return p


def sql_text(name: str) -> str:
    return (config.get_paths().sql / REGISTRY[name].sql_file).read_text()


NEEDS_SCORES = {"topline", "dormant_reactivation"}  # these read ranked_accounts, which `make score` fills


def _require_scored(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM ranked_accounts").fetchone()[0] == 0:
        raise RuntimeError("ranked_accounts is empty: run `make score` (after `make clean`) before computing this metric. "
                           "Re-running `make clean` rebuilds the database and clears scores.")


def _icp_split_post(df: pd.DataFrame) -> pd.DataFrame:
    from .insights import wilson_ci
    df = df.copy()
    df["rate"] = df["x"] / df["n"]
    ci = [wilson_ci(int(x), int(n)) for x, n in zip(df["x"], df["n"])]
    df["ci_low"], df["ci_high"] = [c[0] for c in ci], [c[1] for c in ci]
    return df


POSTPROCESS = {"experiment_a_icp_split": _icp_split_post}


def run_metric(name: str, conn: sqlite3.Connection, **overrides) -> pd.DataFrame:
    if name in NEEDS_SCORES:
        _require_scored(conn)
    df = pd.read_sql_query(sql_text(name), conn, params=default_params(**overrides))
    if name in POSTPROCESS:
        df = POSTPROCESS[name](df)
    return df.replace([np.inf, -np.inf], np.nan)


def connect(root: Path | str | None = None) -> sqlite3.Connection:
    paths = config.get_paths(root)
    conn = sqlite3.connect(paths.db.resolve().as_uri() + "?mode=ro", uri=True)  # as_uri() percent-encodes #, %, ?
    return conn


def run_all(root: Path | str | None = None) -> dict[str, pd.DataFrame]:
    paths = config.get_paths(root).ensure()
    conn = connect(root)
    out = {}
    try:
        for name in REGISTRY:
            df = run_metric(name, conn)
            round_df(df).to_csv(paths.marts / f"{name}.csv", index=False)
            out[name] = df
    finally:
        conn.close()
    return out


def read_mart(name: str, root: Path | str | None = None) -> pd.DataFrame:
    return pd.read_csv(config.get_paths(root).marts / f"{name}.csv")
