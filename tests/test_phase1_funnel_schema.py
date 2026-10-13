import sqlite3

import pandas as pd
import pytest

from bgos import funnel, schema


def test_stage_order_strict_and_defined():
    orders = [s.order for s in funnel.STAGES]
    assert orders == list(range(1, 8))
    assert [s.name for s in funnel.STAGES] == [
        "Raw Lead", "ICP-Qualified Agency", "Engaged Broker", "First Submission",
        "Quoted", "Bound", "Repeat Submission"]
    assert len({s.key for s in funnel.STAGES}) == 7
    for s in funnel.STAGES:
        assert len(s.definition) > 30


def test_schema_creates_cleanly_and_fk_on():
    conn = schema.init_db(":memory:") if False else schema.connect(":memory:")
    schema.create_schema(conn)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    names = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert {"agencies", "touches", "submissions", "experiment_assignments", "stage_events"} <= names


def _conn():
    conn = schema.connect(":memory:")
    schema.create_schema(conn)
    conn.execute("insert into agencies(agency_id,name,first_touch_date) values('AG-1','A','2025-10-02')")
    return conn


def test_foreign_key_enforced():
    conn = _conn()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("insert into touches(touch_id,agency_id,touched_at) values('T1','NOPE','2025-10-03')")


def test_bound_before_quoted_rejected_and_flagged():
    conn = _conn()
    row = dict(submission_id="S1", agency_id="AG-1", submitted_at="2025-10-05 09:00:00",
               quoted_at="2025-10-07 09:00:00", bound_at="2025-10-06 09:00:00")
    assert "bound_before_quote" in funnel.validate_submission(row)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("insert into submissions(submission_id,agency_id,submitted_at,quoted_at,bound_at) "
                     "values(:submission_id,:agency_id,:submitted_at,:quoted_at,:bound_at)", row)


def test_quote_before_submission_and_negative_turnaround():
    assert funnel.validate_submission(dict(submitted_at="2025-10-05", quoted_at="2025-10-04")) == ["quote_before_submission"]
    assert funnel.validate_submission(dict(submitted_at="2025-10-05", quote_turnaround_hours=-3)) == ["negative_turnaround"]
    assert funnel.validate_submission(dict(submitted_at="2025-10-05", quoted_at="2025-10-06", bound_at="2025-10-08")) == []
    conn = _conn()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("insert into submissions(submission_id,agency_id,submitted_at,quoted_at) "
                     "values('S2','AG-1','2025-10-05 09:00:00','2025-10-04 09:00:00')")


def test_every_table_and_column_documented_and_matches_db():
    conn = schema.connect(":memory:")
    schema.create_schema(conn)
    for table, meta in schema.TABLES.items():
        assert meta["description"].strip()
        db_cols = [r[1] for r in conn.execute(f"pragma table_info({table})")]
        assert db_cols == [c[0] for c in meta["columns"]]
        for name, _t, desc, _c in meta["columns"]:
            assert desc.strip(), f"{table}.{name} undocumented"


def test_is_complete_and_is_icp():
    full = {f: 1 for f in funnel.REQUIRED_SUBMISSION_FIELDS}
    assert funnel.is_complete(full)
    full["has_loss_runs"] = 0
    assert not funnel.is_complete(full)
    base = dict(commercial_lines="General Liability|Property", size_producers=5,
                es_appetite="high", specialty_focus="Professional Services")
    assert funnel.is_icp(base)
    assert not funnel.is_icp({**base, "size_producers": 2})
    assert not funnel.is_icp({**base, "commercial_lines": ""})
    assert not funnel.is_icp({**base, "es_appetite": "low"})  # weak specialty + low E&S
    assert funnel.is_icp({**base, "es_appetite": "low", "specialty_focus": "Habitational"})
    assert not funnel.is_icp({**base, "size_producers": None})


def _frames():
    ag = pd.DataFrame({
        "agency_id": ["A", "B", "C", "D"],
        "first_touch_date": ["2025-10-01"] * 4,
        "is_icp": [1, 1, 0, 1]})
    tou = pd.DataFrame({"agency_id": ["A", "B", "C"], "touched_at": ["2025-10-05"] * 3,
                        "touch_type": ["email_open", "email_sent", "reply"]})
    cols = ["agency_id", "submitted_at", "quoted_at", "bound_at", "is_complete"]
    sub = pd.DataFrame([
        ["A", "2025-10-10", "2025-10-12", "2025-10-15", 1],
        ["A", "2025-11-01", "2025-11-03", None, 1],       # repeat within 90d of bind
        ["C", "2025-10-10", "2025-10-12", "2025-10-15", 1],  # non-ICP: out of funnel
        ["D", "2025-10-10", None, None, 0],               # incomplete, never engaged
    ], columns=cols)
    return ag, tou, sub


def test_derive_stage_events_nested():
    ag, tou, sub = _frames()
    ev = funnel.derive_stage_events(ag, tou, sub)
    counts = funnel.funnel_counts(ev)
    assert counts.to_dict() == {"raw_lead": 4, "icp_qualified": 3, "engaged": 1,
                                "first_submission": 1, "quoted": 1, "bound": 1, "repeat_submission": 1}
    assert (counts.diff().dropna() <= 0).all()
    assert "C" not in set(ev[ev.stage == "engaged"].agency_id)


def test_repeat_requires_window():
    ag, tou, sub = _frames()
    sub.loc[1, "submitted_at"] = "2026-03-01"  # > 90 days after bind
    ev = funnel.derive_stage_events(ag, tou, sub)
    assert funnel.funnel_counts(ev)["repeat_submission"] == 0
