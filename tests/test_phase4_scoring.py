import re

import numpy as np
import pandas as pd
import pytest

import config
from bgos import clean, funnel, scoring

AS_OF = pd.Timestamp(config.AS_OF)


def mk_agency(aid="A1", **kw):
    base = dict(agency_id=aid, name="Test Agency", state="CA", size_producers=12,
                commercial_lines="General Liability|Umbrella/Excess|Professional Liability|Cyber",
                specialty_focus="Habitational", es_appetite="high", es_submissions_py=40,
                lead_source="outbound", owner="Maya R.", is_icp=1, first_touch_date="2026-01-01")
    base.update(kw)
    return base


def touches(aid, rows):
    return pd.DataFrame([dict(agency_id=aid, touched_at=(AS_OF - pd.Timedelta(days=d)).strftime("%Y-%m-%d 10:00:00"),
                              touch_type=t) for d, t in rows], columns=["agency_id", "touched_at", "touch_type"])


EMPTY_T = pd.DataFrame(columns=["agency_id", "touched_at", "touch_type"])


def subs(aid, days_ago_list, complete=1):
    rows = []
    for i, d in enumerate(days_ago_list):
        when = (AS_OF - pd.Timedelta(days=d)).strftime("%Y-%m-%d 10:00:00")
        rows.append(dict(submission_id=f"S-{aid}-{i}", agency_id=aid, submitted_at=when, quoted_at=None,
                         bound_at=None, is_complete=complete))
    return pd.DataFrame(rows, columns=["submission_id", "agency_id", "submitted_at", "quoted_at", "bound_at", "is_complete"])


EMPTY_S = subs("x", [])


def score_one(agency, t=EMPTY_T, s=EMPTY_S):
    return scoring.score_agencies(pd.DataFrame([agency]), t, s, AS_OF).iloc[0]


def test_weights_sum_to_one_and_names():
    assert sum(config.SCORING_WEIGHTS.values()) == pytest.approx(1.0)
    assert config.SCORING_WEIGHTS == {"specialty_fit": 0.30, "commercial_volume": 0.25, "es_activity": 0.20,
                                      "engagement": 0.15, "geographic_priority": 0.10}
    assert set(config.ENGAGEMENT_TOUCH_POINTS) == set(funnel.ENGAGEMENT_TOUCH_TYPES)  # audit B-17: submissions are NOT engagement


def test_component_formulas_hand_computed():
    r = score_one(mk_agency(specialty_focus="Habitational", commercial_lines="Cyber|Umbrella/Excess|Professional Liability",
                            size_producers=50, es_appetite="medium", es_submissions_py=30, state="TX"))
    assert r.specialty_fit == pytest.approx(0.6 * 1.0 + 0.4 * 1.0)
    assert r.commercial_volume == pytest.approx(0.6 * 1.0 + 0.4 * 3 / 5)
    assert r.es_activity == pytest.approx(0.5 * 0.6 + 0.5 * 0.5)
    assert r.geographic_priority == 1.0
    assert r.engagement == 0.0
    expected = 0.30 * r.specialty_fit + 0.25 * r.commercial_volume + 0.20 * r.es_activity + 0.10 * 1.0
    assert r.score == pytest.approx(expected)
    assert score_one(mk_agency(state="UNK")).geographic_priority == 0.0
    assert score_one(mk_agency(state="OH")).geographic_priority == 0.3
    assert score_one(mk_agency(state="WA")).geographic_priority == 0.6


def test_engagement_decays_and_saturates():
    fresh = score_one(mk_agency(), touches("A1", [(1, "reply")]))
    old = score_one(mk_agency(), touches("A1", [(180, "reply")]))
    many = score_one(mk_agency(), touches("A1", [(1, "meeting_held")] * 30))
    sends = score_one(mk_agency(), touches("A1", [(1, "email_sent")] * 30))
    assert fresh.engagement > old.engagement > 0
    assert fresh.engagement == pytest.approx(1 - np.exp(-0.5 ** (1 / 45) * 1.0 / 3.0))
    assert 0.99 < many.engagement <= 1.0
    assert sends.engagement == 0.0  # sends are vanity, not engagement


# ---- tier rules, hand-built agencies -------------------------------------------------------------
def test_tier_reactivation_precedence_and_boundary():
    hot = touches("A1", [(2, "reply"), (3, "meeting_held")])
    r60 = score_one(mk_agency(), hot, subs("A1", [60]))
    r59 = score_one(mk_agency(), hot, subs("A1", [59]))
    assert r60.tier == "Reactivation"  # >= 60 days, checked before Tier 1 even with high fit and engagement
    assert r59.tier != "Reactivation"
    assert score_one(mk_agency(), EMPTY_T, subs("A1", [200], complete=0)).tier != "Reactivation"  # incomplete only


def test_tier1_requires_all_three_conditions():
    hot = touches("A1", [(2, "reply"), (3, "meeting_held"), (4, "email_click")])
    assert score_one(mk_agency(), hot).tier == "Tier 1"
    assert score_one(mk_agency(specialty_focus="Professional Services", commercial_lines="General Liability"), hot).tier != "Tier 1"
    assert score_one(mk_agency(es_appetite="none", es_submissions_py=0), hot).tier != "Tier 1"
    assert score_one(mk_agency(), EMPTY_T).tier != "Tier 1"  # no engagement
    assert score_one(mk_agency(is_icp=0), hot).tier == "Tier 3"


def test_tier2_and_tier3():
    r = score_one(mk_agency(), EMPTY_T)  # strong fit, no engagement
    assert r.score >= config.TIER_THRESHOLDS["tier2_score"] and r.tier == "Tier 2"
    weak = score_one(mk_agency(specialty_focus="Professional Services", commercial_lines="Workers Comp", size_producers=3,
                               es_appetite="low", es_submissions_py=1, state="OH"))
    assert weak.tier == "Tier 3"
    assert score_one(mk_agency(is_icp=0)).tier == "Tier 3"


def test_actions_follow_tier_and_stage():
    assert scoring.recommend_action("Reactivation", "bound") == "reactivation"
    assert scoring.recommend_action("Tier 3", "raw_lead") == "monitor"
    assert scoring.recommend_action("Tier 1", "icp_qualified") == "outbound"
    assert scoring.recommend_action("Tier 1", "engaged") == "onboarding"
    assert scoring.recommend_action("Tier 2", "quoted") == "expansion"
    assert scoring.recommend_action("Tier 2", "raw_lead") == "nurture"  # Tier 2 = nurture (audit B-20)
    assert scoring.recommend_action("Tier 2", "icp_qualified") == "nurture"
    assert scoring.recommend_action("Active", "repeat_submission") == "expansion"
    assert scoring.recommend_action("Active", "first_submission") == "expansion"


# ---- pipeline-level checks on generated data -----------------------------------------------------
@pytest.fixture(scope="module")
def ranked(gen_result, clean_result):
    from bgos import scoring as sc
    return sc.run_score(gen_result["root"])


def test_every_agency_exactly_one_tier(ranked, clean_result):
    assert len(ranked) == len(clean_result.agencies) and ranked.agency_id.is_unique
    assert set(ranked.tier) <= set(scoring.TIERS)
    assert set(ranked.tier) == set(scoring.TIERS)  # all four tiers occur on this data


def test_ranges_and_sorting(ranked):
    for c in scoring.COMPONENTS + ["score"]:
        assert ranked[c].between(0, 1).all(), c
    assert ranked.score.is_monotonic_decreasing


def test_no_null_fields(ranked):
    for c in ["next_action", "owner", "channel", "reason", "tier", "score", "name"]:
        assert ranked[c].notna().all() and (ranked[c].astype(str).str.len() > 0).all(), c


def test_reason_references_real_component_values(ranked):
    for r in ranked.head(300).to_dict("records"):
        contrib = sorted(((config.SCORING_WEIGHTS[c] * r[c], c) for c in scoring.COMPONENTS), reverse=True)[:2]
        for _, c in contrib:
            assert f"{scoring.COMPONENT_LABEL[c]} {r[c]:.2f}" in r["reason"], (r["reason"], c, r[c])
        assert f"score {r['score']:.2f}" in r["reason"]


def test_tiers_1_to_3_are_prospects_only(ranked, clean_result):
    """Audit B-17: the top of the ranking used to be existing customers. Customers are Active or Reactivation."""
    sb = clean_result.submissions
    customers = set(sb[sb.is_complete == 1].agency_id)
    prospect = ranked[ranked.tier.isin(["Tier 1", "Tier 2", "Tier 3"])]
    assert not set(prospect.agency_id) & customers
    assert set(ranked[ranked.tier.isin(["Active", "Reactivation"])].agency_id) == customers
    assert ranked[ranked.tier == "Tier 1"].stage.isin(["raw_lead", "icp_qualified", "engaged"]).all()


def test_engagement_never_uses_submissions():
    base = mk_agency()
    hot = touches("A1", [(3, "reply")])
    without = score_one(base, hot, EMPTY_S)
    with_sub = score_one(base, hot, subs("A1", [5, 10, 20]))
    assert with_sub.engagement == without.engagement
    # submissions alone give an agency zero engagement
    assert score_one(base, EMPTY_T, subs("A1", [5, 10, 20])).engagement == 0.0


def test_scores_are_point_in_time():
    """Nothing dated after the as-of date may influence a score (needed for the out-of-sample check)."""
    cutoff = AS_OF - pd.Timedelta(days=90)
    base = mk_agency()
    early = touches("A1", [(100, "reply")])
    future = touches("A1", [(100, "reply"), (10, "meeting_held"), (5, "email_click")])
    a = scoring.score_agencies(pd.DataFrame([base]), early, EMPTY_S, cutoff).iloc[0]
    b = scoring.score_agencies(pd.DataFrame([base]), future, subs("A1", [20]), cutoff).iloc[0]
    assert a.engagement == b.engagement and a.score == b.score and a.tier == b.tier and b.n_complete_subs == 0


def test_out_of_sample_tier_check_orders_tiers(clean_result):
    h = scoring.holdout_conversion_by_tier(clean_result.agencies, clean_result.touches, clean_result.submissions)
    assert list(h.tier) == ["Tier 1", "Tier 2", "Tier 3"] and (h.prospects > 0).all()
    assert h.scored_as_of.iloc[0] == (AS_OF - pd.Timedelta(days=config.HOLDOUT_DAYS)).date().isoformat()
    rate = (h.converted / h.prospects)
    assert rate.iloc[0] > rate.iloc[1] > rate.iloc[2], h.to_dict("records")
    assert h.loc[h.prospects < config.MIN_N, "rate"].isna().all() and h.loc[h.prospects >= config.MIN_N, "rate"].notna().all()


def test_out_of_sample_check_is_independent_of_the_outcome_window(clean_result):
    """Deleting every touch and submission after the cutoff must not change who is in which tier."""
    cutoff = AS_OF - pd.Timedelta(days=config.HOLDOUT_DAYS)
    ag, tc, sb = clean_result.agencies, clean_result.touches, clean_result.submissions
    full = scoring.score_agencies(ag, tc, sb, cutoff).set_index("agency_id")
    tc2 = tc[pd.to_datetime(tc.touched_at) <= cutoff + pd.Timedelta(days=1)]
    sb2 = sb[pd.to_datetime(sb.submitted_at) <= cutoff + pd.Timedelta(days=1)]
    cut = scoring.score_agencies(ag, tc2, sb2, cutoff).set_index("agency_id")
    pd.testing.assert_series_equal(full.tier, cut.tier)
    pd.testing.assert_series_equal(full.score, cut.score)


def test_written_outputs(gen_result, ranked):
    out = pd.read_csv(gen_result["root"] / "outputs" / "ranked_accounts.csv")
    assert list(out.columns[:8]) == ["agency_id", "name", "score", "tier", "next_action", "owner", "channel", "reason"]
    assert len(out) == len(ranked)
    import sqlite3
    conn = sqlite3.connect(gen_result["root"] / "data" / "clean" / "bgos.sqlite")
    assert conn.execute("select count(*) from ranked_accounts").fetchone()[0] == len(ranked)


def test_dormancy_matches_definition(ranked, clean_result):
    sb = clean_result.submissions
    comp = sb[sb.is_complete == 1]
    last = pd.to_datetime(comp.groupby("agency_id").submitted_at.max()).dt.normalize()
    days = (AS_OF - last).dt.days
    expect = set(days[days >= config.DORMANCY_DAYS].index)
    assert set(ranked[ranked.tier == "Reactivation"].agency_id) == expect
