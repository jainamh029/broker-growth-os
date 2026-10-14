-- Nested funnel. `agencies` = observed counts. The conversion columns come in two flavours:
--   observed_*  : all agencies, including leads too recent to have converted (UNDERSTATES conversion)
--   mature_*    : each step measured only on agencies that reached the previous stage at least N days ago
--                 (window per step = :mat_* params, set from the observed lag distribution); cumulative = product of
--                 the mature step rates. Suppressed (NULL) when a step's mature base is below :min_n.
WITH st AS (
    SELECT a.agency_id,
           MAX(CASE WHEN se.stage_order = 2 THEN se.reached_at END) AS t2,
           MAX(CASE WHEN se.stage_order = 3 THEN se.reached_at END) AS t3,
           MAX(CASE WHEN se.stage_order = 4 THEN se.reached_at END) AS t4,
           MAX(CASE WHEN se.stage_order = 5 THEN se.reached_at END) AS t5,
           MAX(CASE WHEN se.stage_order = 6 THEN se.reached_at END) AS t6,
           MAX(CASE WHEN se.stage_order = 7 THEN se.reached_at END) AS t7
    FROM agencies a LEFT JOIN stage_events se ON se.agency_id = a.agency_id GROUP BY a.agency_id
),
c AS (
    SELECT stage, stage_order, COUNT(DISTINCT agency_id) AS agencies FROM stage_events GROUP BY stage, stage_order
),
steps(stage_order, win, base, conv) AS (
    SELECT 2, 0, COUNT(*), COUNT(t2) FROM st
    UNION ALL SELECT 3, :mat_eng, SUM(CASE WHEN t2 <= datetime(:as_of || ' 23:59:59', '-' || :mat_eng || ' days') THEN 1 ELSE 0 END),
                      SUM(CASE WHEN t2 <= datetime(:as_of || ' 23:59:59', '-' || :mat_eng || ' days') AND t3 IS NOT NULL THEN 1 ELSE 0 END) FROM st
    UNION ALL SELECT 4, :mat_fs, SUM(CASE WHEN t3 <= datetime(:as_of || ' 23:59:59', '-' || :mat_fs || ' days') THEN 1 ELSE 0 END),
                      SUM(CASE WHEN t3 <= datetime(:as_of || ' 23:59:59', '-' || :mat_fs || ' days') AND t4 IS NOT NULL THEN 1 ELSE 0 END) FROM st
    UNION ALL SELECT 5, :mat_q, SUM(CASE WHEN t4 <= datetime(:as_of || ' 23:59:59', '-' || :mat_q || ' days') THEN 1 ELSE 0 END),
                      SUM(CASE WHEN t4 <= datetime(:as_of || ' 23:59:59', '-' || :mat_q || ' days') AND t5 IS NOT NULL THEN 1 ELSE 0 END) FROM st
    UNION ALL SELECT 6, :mat_b, SUM(CASE WHEN t5 <= datetime(:as_of || ' 23:59:59', '-' || :mat_b || ' days') THEN 1 ELSE 0 END),
                      SUM(CASE WHEN t5 <= datetime(:as_of || ' 23:59:59', '-' || :mat_b || ' days') AND t6 IS NOT NULL THEN 1 ELSE 0 END) FROM st
    UNION ALL SELECT 7, :mat_r, SUM(CASE WHEN t6 <= datetime(:as_of || ' 23:59:59', '-' || :mat_r || ' days') THEN 1 ELSE 0 END),
                      SUM(CASE WHEN t6 <= datetime(:as_of || ' 23:59:59', '-' || :mat_r || ' days') AND t7 IS NOT NULL THEN 1 ELSE 0 END) FROM st
),
rates AS (
    SELECT stage_order, win, base, conv,
           CASE WHEN base < :min_n THEN NULL ELSE 1.0 * conv / base END AS step_rate FROM steps
),
cum(stage_order, cum_rate) AS (
    SELECT 1, 1.0
    UNION ALL SELECT r.stage_order, cum.cum_rate * r.step_rate FROM rates r JOIN cum ON cum.stage_order = r.stage_order - 1
)
SELECT c.stage, c.stage_order, c.agencies,
       ROUND(1.0 * c.agencies / NULLIF(LAG(c.agencies) OVER (ORDER BY c.stage_order), 0), 4) AS observed_step_conversion,
       ROUND(1.0 * c.agencies / NULLIF(FIRST_VALUE(c.agencies) OVER (ORDER BY c.stage_order), 0), 4) AS observed_cumulative_conversion,
       r.win AS mature_window_days, r.base AS mature_base, r.conv AS mature_converted,
       ROUND(r.step_rate, 4) AS mature_step_conversion, ROUND(cum.cum_rate, 4) AS mature_cumulative_conversion
FROM c LEFT JOIN rates r ON r.stage_order = c.stage_order LEFT JOIN cum ON cum.stage_order = c.stage_order
ORDER BY c.stage_order;
