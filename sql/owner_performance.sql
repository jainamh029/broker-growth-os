-- Growth owner performance on downstream conversion, each step on MATURE cohorts (audit B-18). Suppressed when the mature base < :min_n.
WITH st AS (
    SELECT a.agency_id, a.owner,
           MAX(CASE WHEN se.stage_order = 2 THEN se.reached_at END) AS t2,
           MAX(CASE WHEN se.stage_order = 3 THEN se.reached_at END) AS t3,
           MAX(CASE WHEN se.stage_order = 4 THEN se.reached_at END) AS t4,
           MAX(CASE WHEN se.stage_order = 6 THEN se.reached_at END) AS t6
    FROM agencies a LEFT JOIN stage_events se ON se.agency_id = a.agency_id GROUP BY a.agency_id
),
r AS (
    SELECT owner, COUNT(*) AS agencies, COUNT(t2) AS icp_agencies, COUNT(t3) AS engaged_agencies, COUNT(t4) AS first_submissions, COUNT(t6) AS bound_agencies,
           SUM(CASE WHEN t2 <= datetime(:as_of || ' 23:59:59', '-' || :mat_eng || ' days') THEN 1 ELSE 0 END) AS b_eng,
           SUM(CASE WHEN t2 <= datetime(:as_of || ' 23:59:59', '-' || :mat_eng || ' days') AND t3 IS NOT NULL THEN 1 ELSE 0 END) AS c_eng,
           SUM(CASE WHEN t3 <= datetime(:as_of || ' 23:59:59', '-' || :mat_fs || ' days') THEN 1 ELSE 0 END) AS b_act,
           SUM(CASE WHEN t3 <= datetime(:as_of || ' 23:59:59', '-' || :mat_fs || ' days') AND t4 IS NOT NULL THEN 1 ELSE 0 END) AS c_act,
           SUM(CASE WHEN t4 <= datetime(:as_of || ' 23:59:59', '-' || (:mat_q + :mat_b) || ' days') THEN 1 ELSE 0 END) AS b_bind,
           SUM(CASE WHEN t4 <= datetime(:as_of || ' 23:59:59', '-' || (:mat_q + :mat_b) || ' days') AND t6 IS NOT NULL THEN 1 ELSE 0 END) AS c_bind
    FROM st GROUP BY owner
),
c AS (
    SELECT a.owner, COALESCE(SUM(s.commission), 0) AS commission
    FROM agencies a LEFT JOIN submissions s ON s.agency_id = a.agency_id AND s.bound_at IS NOT NULL GROUP BY a.owner
)
SELECT r.owner, r.agencies, r.icp_agencies, r.engaged_agencies, r.first_submissions, r.bound_agencies,
       CASE WHEN r.b_eng < :min_n THEN NULL ELSE ROUND(1.0 * r.c_eng / r.b_eng, 4) END AS engagement_rate,
       CASE WHEN r.b_act < :min_n THEN NULL ELSE ROUND(1.0 * r.c_act / r.b_act, 4) END AS activation_rate,
       CASE WHEN r.b_bind < :min_n THEN NULL ELSE ROUND(1.0 * r.c_bind / r.b_bind, 4) END AS bind_rate_of_submitters,
       CASE WHEN r.agencies < :min_n THEN NULL ELSE ROUND(1.0 * c.commission / r.agencies, 2) END AS commission_per_agency,
       ROUND(c.commission, 2) AS total_commission
FROM r JOIN c ON c.owner = r.owner ORDER BY r.owner;
