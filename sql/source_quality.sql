-- Source quality by DOWNSTREAM outcomes, measured on MATURE cohorts (audit B-18).
-- Each step rate (ICP -> engaged -> first submission -> quoted -> bound -> repeat) uses only agencies that reached the previous
-- stage at least :mat_* days before :as_of; bind_rate_per_lead is the product of the mature step rates, so recent leads that
-- have not had time to convert do not understate a source. observed_bind_rate (all leads, immature included) is shown for reference.
-- Rates are suppressed (NULL, suppressed = 1) when any needed step has a mature base below :min_n.
WITH st AS (
    SELECT a.agency_id, a.lead_source AS g,
           MAX(CASE WHEN se.stage_order = 2 THEN se.reached_at END) AS t2,
           MAX(CASE WHEN se.stage_order = 3 THEN se.reached_at END) AS t3,
           MAX(CASE WHEN se.stage_order = 4 THEN se.reached_at END) AS t4,
           MAX(CASE WHEN se.stage_order = 5 THEN se.reached_at END) AS t5,
           MAX(CASE WHEN se.stage_order = 6 THEN se.reached_at END) AS t6,
           MAX(CASE WHEN se.stage_order = 7 THEN se.reached_at END) AS t7
    FROM agencies a LEFT JOIN stage_events se ON se.agency_id = a.agency_id GROUP BY a.agency_id
),
agg AS (
    SELECT g, COUNT(*) AS leads, COUNT(t2) AS icp_agencies, COUNT(t3) AS engaged_agencies, COUNT(t4) AS first_submissions,
           COUNT(t5) AS quoted_agencies, COUNT(t6) AS bound_agencies, COUNT(t7) AS repeat_agencies,
           SUM(CASE WHEN t2 <= datetime(:as_of || ' 23:59:59', '-' || :mat_eng || ' days') THEN 1 ELSE 0 END) AS b3,
           SUM(CASE WHEN t2 <= datetime(:as_of || ' 23:59:59', '-' || :mat_eng || ' days') AND t3 IS NOT NULL THEN 1 ELSE 0 END) AS c3,
           SUM(CASE WHEN t3 <= datetime(:as_of || ' 23:59:59', '-' || :mat_fs || ' days') THEN 1 ELSE 0 END) AS b4,
           SUM(CASE WHEN t3 <= datetime(:as_of || ' 23:59:59', '-' || :mat_fs || ' days') AND t4 IS NOT NULL THEN 1 ELSE 0 END) AS c4,
           SUM(CASE WHEN t4 <= datetime(:as_of || ' 23:59:59', '-' || :mat_q || ' days') THEN 1 ELSE 0 END) AS b5,
           SUM(CASE WHEN t4 <= datetime(:as_of || ' 23:59:59', '-' || :mat_q || ' days') AND t5 IS NOT NULL THEN 1 ELSE 0 END) AS c5,
           SUM(CASE WHEN t5 <= datetime(:as_of || ' 23:59:59', '-' || :mat_b || ' days') THEN 1 ELSE 0 END) AS b6,
           SUM(CASE WHEN t5 <= datetime(:as_of || ' 23:59:59', '-' || :mat_b || ' days') AND t6 IS NOT NULL THEN 1 ELSE 0 END) AS c6,
           SUM(CASE WHEN t6 <= datetime(:as_of || ' 23:59:59', '-' || :mat_r || ' days') THEN 1 ELSE 0 END) AS b7,
           SUM(CASE WHEN t6 <= datetime(:as_of || ' 23:59:59', '-' || :mat_r || ' days') AND t7 IS NOT NULL THEN 1 ELSE 0 END) AS c7
    FROM st GROUP BY g
),
comm AS (
    SELECT a.lead_source AS g, COALESCE(SUM(s.commission), 0) AS commission
    FROM agencies a LEFT JOIN submissions s ON s.agency_id = a.agency_id AND s.bound_at IS NOT NULL GROUP BY a.lead_source
),
calc AS (
    SELECT g.*, c.commission,
           CASE WHEN g.b3 < :min_n OR g.b4 < :min_n THEN NULL
                ELSE 1.0 * g.icp_agencies / g.leads * g.c3 / g.b3 * g.c4 / g.b4 END AS fs_rate,
           CASE WHEN g.b3 < :min_n OR g.b4 < :min_n OR g.b5 < :min_n OR g.b6 < :min_n THEN NULL
                ELSE 1.0 * g.icp_agencies / g.leads * g.c3 / g.b3 * g.c4 / g.b4 * g.c5 / g.b5 * g.c6 / g.b6 END AS bind_rate,
           CASE WHEN g.b7 < :min_n THEN NULL ELSE 1.0 * g.c7 / g.b7 END AS rep_rate
    FROM agg g JOIN comm c ON c.g = g.g
)
SELECT g AS lead_source, leads, icp_agencies, engaged_agencies, first_submissions, bound_agencies, repeat_agencies,
       ROUND(fs_rate, 4) AS first_submission_rate, ROUND(bind_rate, 4) AS bind_rate_per_lead,
       ROUND(rep_rate, 4) AS repeat_rate_of_bound,
       CASE WHEN bind_rate IS NULL OR bound_agencies = 0 THEN NULL ELSE ROUND(bind_rate * commission / bound_agencies, 2) END AS commission_per_lead,
       CASE WHEN leads < :min_n THEN NULL ELSE ROUND(1.0 * bound_agencies / leads, 4) END AS observed_bind_rate,
       ROUND(commission, 2) AS total_commission,
       MIN(b3, b4, b5, b6) AS mature_min_base,
       CASE WHEN bind_rate IS NULL THEN 1 ELSE 0 END AS suppressed
FROM calc ORDER BY leads DESC, lead_source;
