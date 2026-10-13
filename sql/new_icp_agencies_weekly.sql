-- New ICP-qualified agencies entering the funnel per week (Monday-start weeks).
-- Params: :window_start, :as_of
WITH RECURSIVE weeks(week_start) AS (
    SELECT date(:window_start, 'weekday 0', '-6 days')
    UNION ALL
    SELECT date(week_start, '+7 days') FROM weeks WHERE date(week_start, '+7 days') <= date(:as_of)
),
icp AS (
    SELECT date(reached_at, 'weekday 0', '-6 days') AS week_start, COUNT(*) AS n
    FROM stage_events WHERE stage = 'icp_qualified' GROUP BY 1
)
SELECT w.week_start,
       COALESCE(i.n, 0) AS new_icp_agencies,
       CASE WHEN date(w.week_start, '+6 days') > date(:as_of) THEN 1 ELSE 0 END AS is_partial_week
FROM weeks w LEFT JOIN icp i ON i.week_start = w.week_start
ORDER BY w.week_start;
