-- Monday-morning topline: trailing 7 days vs the prior 7 days ending at :as_of, plus stock numbers.
SELECT
  (SELECT COUNT(*) FROM agencies) AS agencies,
  (SELECT COUNT(*) FROM stage_events WHERE stage = 'icp_qualified') AS icp_agencies,
  (SELECT COUNT(*) FROM stage_events WHERE stage = 'engaged') AS engaged_agencies,
  (SELECT COUNT(*) FROM stage_events WHERE stage = 'first_submission') AS activated_agencies,
  (SELECT COUNT(*) FROM stage_events WHERE stage = 'bound') AS bound_agencies,
  (SELECT COUNT(*) FROM stage_events WHERE stage = 'icp_qualified'
      AND date(reached_at) > date(:as_of, '-7 days') AND date(reached_at) <= date(:as_of)) AS new_icp_7d,
  (SELECT COUNT(*) FROM stage_events WHERE stage = 'icp_qualified'
      AND date(reached_at) > date(:as_of, '-14 days') AND date(reached_at) <= date(:as_of, '-7 days')) AS new_icp_prev_7d,
  (SELECT COUNT(*) FROM stage_events WHERE stage = 'first_submission'
      AND date(reached_at) > date(:as_of, '-7 days') AND date(reached_at) <= date(:as_of)) AS new_activations_7d,
  (SELECT COUNT(*) FROM submissions WHERE is_complete = 1
      AND date(submitted_at) > date(:as_of, '-7 days') AND date(submitted_at) <= date(:as_of)) AS complete_submissions_7d,
  (SELECT COUNT(*) FROM submissions WHERE is_complete = 1
      AND date(submitted_at) > date(:as_of, '-14 days') AND date(submitted_at) <= date(:as_of, '-7 days')) AS complete_submissions_prev_7d,
  (SELECT COUNT(DISTINCT s.agency_id) FROM submissions s JOIN agencies a ON a.agency_id = s.agency_id
      WHERE s.is_complete = 1 AND a.is_icp = 1
      AND julianday(date(:as_of)) - julianday(date(s.submitted_at)) < :dormancy_days) AS active_agencies_60d,
  (SELECT COUNT(*) FROM ranked_accounts WHERE tier = 'Reactivation') AS dormant_agencies,
  (SELECT COALESCE(ROUND(SUM(commission), 2), 0) FROM submissions
      WHERE bound_at IS NOT NULL AND julianday(date(:as_of)) - julianday(date(bound_at)) < 90) AS commission_last_90d,
  (SELECT COALESCE(ROUND(SUM(premium), 2), 0) FROM submissions
      WHERE bound_at IS NOT NULL AND julianday(date(:as_of)) - julianday(date(bound_at)) < 90) AS bound_premium_last_90d;
