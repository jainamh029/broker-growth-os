-- Weekly growth review (Monday-start weeks).
-- NORTH STAR: qualified submissions = complete submissions from ICP agencies that are NEW (first complete submission)
--             or ACTIVE (previous complete submission less than :dormancy_days earlier).
-- Submissions that arrive after >= :dormancy_days of silence are counted separately as reactivated_submissions.
-- INPUTS: new_icp_agencies, new_engaged_agencies, new_activations (first complete submissions).
-- DIAGNOSTICS: completeness_rate, quote_rate, bind_rate (only for weeks old enough to have outcomes), reactivated_submissions.
WITH RECURSIVE weeks(week_start) AS (
    SELECT date(:window_start, 'weekday 0', '-6 days')
    UNION ALL
    SELECT date(week_start, '+7 days') FROM weeks WHERE date(week_start, '+7 days') <= date(:as_of)
),
cs AS (
    SELECT s.submission_id, s.agency_id, s.submitted_at, s.quoted_at, s.bound_at, a.is_icp,
           LAG(s.submitted_at) OVER (PARTITION BY s.agency_id ORDER BY s.submitted_at, s.submission_id) AS prev_at
    FROM submissions s JOIN agencies a ON a.agency_id = s.agency_id WHERE s.is_complete = 1
),
cw AS (
    SELECT date(submitted_at, 'weekday 0', '-6 days') AS week_start,
           SUM(CASE WHEN is_icp = 1 AND (prev_at IS NULL OR julianday(submitted_at) - julianday(prev_at) < :dormancy_days) THEN 1 ELSE 0 END) AS qualified_submissions,
           SUM(CASE WHEN is_icp = 1 AND prev_at IS NOT NULL AND julianday(submitted_at) - julianday(prev_at) >= :dormancy_days THEN 1 ELSE 0 END) AS reactivated_submissions,
           COUNT(*) AS complete_submissions,
           SUM(CASE WHEN quoted_at IS NOT NULL THEN 1 ELSE 0 END) AS quoted,
           SUM(CASE WHEN bound_at IS NOT NULL THEN 1 ELSE 0 END) AS bound
    FROM cs GROUP BY 1
),
aw AS (
    SELECT date(submitted_at, 'weekday 0', '-6 days') AS week_start, COUNT(*) AS all_submissions
    FROM submissions GROUP BY 1
),
ev AS (
    SELECT date(reached_at, 'weekday 0', '-6 days') AS week_start,
           SUM(CASE WHEN stage = 'icp_qualified' THEN 1 ELSE 0 END) AS new_icp_agencies,
           SUM(CASE WHEN stage = 'engaged' THEN 1 ELSE 0 END) AS new_engaged_agencies,
           SUM(CASE WHEN stage = 'first_submission' THEN 1 ELSE 0 END) AS new_activations
    FROM stage_events GROUP BY 1
)
SELECT w.week_start,
       CASE WHEN date(w.week_start, '+6 days') > date(:as_of) THEN 1 ELSE 0 END AS is_partial_week,
       COALESCE(cw.qualified_submissions, 0) AS qualified_submissions,
       COALESCE(ev.new_icp_agencies, 0) AS new_icp_agencies,
       COALESCE(ev.new_engaged_agencies, 0) AS new_engaged_agencies,
       COALESCE(ev.new_activations, 0) AS new_activations,
       COALESCE(cw.reactivated_submissions, 0) AS reactivated_submissions,
       COALESCE(aw.all_submissions, 0) AS all_submissions,
       COALESCE(cw.complete_submissions, 0) AS complete_submissions,
       CASE WHEN COALESCE(aw.all_submissions, 0) < :min_n_weekly THEN NULL
            ELSE ROUND(1.0 * cw.complete_submissions / aw.all_submissions, 4) END AS completeness_rate,
       CASE WHEN date(w.week_start, '+21 days') > date(:as_of) OR COALESCE(cw.complete_submissions, 0) < :min_n_weekly THEN NULL
            ELSE ROUND(1.0 * cw.quoted / cw.complete_submissions, 4) END AS quote_rate,
       CASE WHEN date(w.week_start, '+35 days') > date(:as_of) OR COALESCE(cw.quoted, 0) < :min_n_weekly THEN NULL
            ELSE ROUND(1.0 * cw.bound / cw.quoted, 4) END AS bind_rate_of_quoted
FROM weeks w
LEFT JOIN cw ON cw.week_start = w.week_start
LEFT JOIN aw ON aw.week_start = w.week_start
LEFT JOIN ev ON ev.week_start = w.week_start
ORDER BY w.week_start;
