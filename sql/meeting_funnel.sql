-- Meeting diagnostic (not a strict funnel stage): ICP-qualified agencies that booked/held a meeting.
WITH icp AS (SELECT agency_id FROM stage_events WHERE stage = 'icp_qualified'),
eng AS (SELECT agency_id FROM stage_events WHERE stage = 'engaged'),
mtg AS (SELECT DISTINCT t.agency_id FROM touches t JOIN icp USING (agency_id)
        WHERE t.touch_type IN ('meeting_booked', 'meeting_held')),
fs AS (SELECT agency_id FROM stage_events WHERE stage = 'first_submission'),
bd AS (SELECT agency_id FROM stage_events WHERE stage = 'bound')
SELECT (SELECT COUNT(*) FROM icp) AS icp_agencies,
       (SELECT COUNT(*) FROM eng) AS engaged_agencies,
       (SELECT COUNT(*) FROM mtg) AS meeting_agencies,
       (SELECT COUNT(*) FROM mtg WHERE agency_id IN (SELECT agency_id FROM fs)) AS meeting_then_submitted,
       (SELECT COUNT(*) FROM mtg WHERE agency_id IN (SELECT agency_id FROM bd)) AS meeting_then_bound,
       CASE WHEN (SELECT COUNT(*) FROM mtg) < :min_n THEN NULL
            ELSE ROUND(1.0 * (SELECT COUNT(*) FROM mtg WHERE agency_id IN (SELECT agency_id FROM fs)) / (SELECT COUNT(*) FROM mtg), 4) END AS meeting_to_submission_rate,
       CASE WHEN (SELECT COUNT(*) FROM eng) < :min_n THEN NULL
            ELSE ROUND(1.0 * (SELECT COUNT(*) FROM mtg WHERE agency_id IN (SELECT agency_id FROM eng)) / (SELECT COUNT(*) FROM eng), 4) END AS engaged_to_meeting_rate,
       CASE WHEN (SELECT COUNT(*) FROM eng WHERE agency_id NOT IN (SELECT agency_id FROM mtg)) < :min_n THEN NULL
            ELSE ROUND(1.0 * (SELECT COUNT(*) FROM eng WHERE agency_id NOT IN (SELECT agency_id FROM mtg) AND agency_id IN (SELECT agency_id FROM fs))
                       / (SELECT COUNT(*) FROM eng WHERE agency_id NOT IN (SELECT agency_id FROM mtg)), 4) END AS no_meeting_to_submission_rate;
