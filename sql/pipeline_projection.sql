-- Assumption-driven projection of first-bind revenue from OPEN pipeline, by segment (= specialty focus).
-- Assumptions (documented in README/DECISIONS): (1) an agency is open (PENDING) if its highest stage is ICP-qualified, engaged,
-- first submission or quoted AND it reached that stage within the maturity window of the NEXT step (:mat_*), i.e. its outcome
-- is still genuinely pending; agencies older than the window are treated as lost, not as live pipeline; (2) it converts to a bind with the product of
-- the remaining MATURE step rates of its segment (each step measured only on agencies old enough to have converted, audit B-18;
-- the overall mature rate is used for any step where the segment's mature base is below :min_n); (3) revenue per bound agency =
-- observed average first-bound commission (overall average when the segment has fewer than :min_n bound agencies);
-- (4) repeat revenue is excluded (conservative).
WITH st AS (
    SELECT a.agency_id, a.specialty_focus AS segment, a.last_activity_date,
           MAX(CASE WHEN se.stage_order = 2 THEN se.reached_at END) AS t2,
           MAX(CASE WHEN se.stage_order = 3 THEN se.reached_at END) AS t3,
           MAX(CASE WHEN se.stage_order = 4 THEN se.reached_at END) AS t4,
           MAX(CASE WHEN se.stage_order = 5 THEN se.reached_at END) AS t5,
           MAX(CASE WHEN se.stage_order = 6 THEN se.reached_at END) AS t6,
           COALESCE(MAX(se.stage_order), 1) AS top_stage
    FROM agencies a LEFT JOIN stage_events se ON se.agency_id = a.agency_id GROUP BY a.agency_id
),
seg AS (
    SELECT segment,
           SUM(CASE WHEN t2 <= datetime(:as_of || ' 23:59:59', '-' || :mat_eng || ' days') THEN 1 ELSE 0 END) AS b3,
           SUM(CASE WHEN t2 <= datetime(:as_of || ' 23:59:59', '-' || :mat_eng || ' days') AND t3 IS NOT NULL THEN 1 ELSE 0 END) AS c3,
           SUM(CASE WHEN t3 <= datetime(:as_of || ' 23:59:59', '-' || :mat_fs || ' days') THEN 1 ELSE 0 END) AS b4,
           SUM(CASE WHEN t3 <= datetime(:as_of || ' 23:59:59', '-' || :mat_fs || ' days') AND t4 IS NOT NULL THEN 1 ELSE 0 END) AS c4,
           SUM(CASE WHEN t4 <= datetime(:as_of || ' 23:59:59', '-' || :mat_q || ' days') THEN 1 ELSE 0 END) AS b5,
           SUM(CASE WHEN t4 <= datetime(:as_of || ' 23:59:59', '-' || :mat_q || ' days') AND t5 IS NOT NULL THEN 1 ELSE 0 END) AS c5,
           SUM(CASE WHEN t5 <= datetime(:as_of || ' 23:59:59', '-' || :mat_b || ' days') THEN 1 ELSE 0 END) AS b6,
           SUM(CASE WHEN t5 <= datetime(:as_of || ' 23:59:59', '-' || :mat_b || ' days') AND t6 IS NOT NULL THEN 1 ELSE 0 END) AS c6,
           COUNT(t6) AS n_bound
    FROM st GROUP BY segment
),
ov AS (
    SELECT SUM(b3) AS b3, SUM(c3) AS c3, SUM(b4) AS b4, SUM(c4) AS c4, SUM(b5) AS b5, SUM(c5) AS c5, SUM(b6) AS b6, SUM(c6) AS c6 FROM seg
),
rates AS (
    SELECT s.segment,
           CASE WHEN s.b3 < :min_n THEN 1.0 * o.c3 / o.b3 ELSE 1.0 * s.c3 / s.b3 END AS r3,
           CASE WHEN s.b4 < :min_n THEN 1.0 * o.c4 / o.b4 ELSE 1.0 * s.c4 / s.b4 END AS r4,
           CASE WHEN s.b5 < :min_n THEN 1.0 * o.c5 / o.b5 ELSE 1.0 * s.c5 / s.b5 END AS r5,
           CASE WHEN s.b6 < :min_n THEN 1.0 * o.c6 / o.b6 ELSE 1.0 * s.c6 / s.b6 END AS r6,
           CASE WHEN s.n_bound < :min_n THEN 1 ELSE 0 END AS used_overall_economics
    FROM seg s, ov o
),
open_pipe AS (
    SELECT segment,
           SUM(CASE WHEN top_stage = 2 THEN 1 ELSE 0 END) AS open_icp,
           SUM(CASE WHEN top_stage = 3 THEN 1 ELSE 0 END) AS open_engaged,
           SUM(CASE WHEN top_stage = 4 THEN 1 ELSE 0 END) AS open_first_submission,
           SUM(CASE WHEN top_stage = 5 THEN 1 ELSE 0 END) AS open_quoted
    FROM st
    WHERE top_stage BETWEEN 2 AND 5
      AND (CASE top_stage WHEN 2 THEN t2 WHEN 3 THEN t3 WHEN 4 THEN t4 ELSE t5 END)
          > datetime(:as_of || ' 23:59:59', '-' || (CASE top_stage WHEN 2 THEN :mat_eng WHEN 3 THEN :mat_fs WHEN 4 THEN :mat_q ELSE :mat_b END) || ' days')
    GROUP BY segment
),
first_bind AS (
    SELECT a.specialty_focus AS segment, s.agency_id, s.commission, s.premium,
           ROW_NUMBER() OVER (PARTITION BY s.agency_id ORDER BY s.bound_at) AS rn
    FROM submissions s JOIN agencies a ON a.agency_id = s.agency_id
    WHERE s.is_complete = 1 AND s.bound_at IS NOT NULL
),
econ AS (SELECT segment, AVG(commission) AS avg_commission, AVG(premium) AS avg_premium FROM first_bind WHERE rn = 1 GROUP BY segment),
econ_all AS (SELECT AVG(commission) AS avg_commission, AVG(premium) AS avg_premium FROM first_bind WHERE rn = 1),
proj AS (
    SELECT r.segment,
           COALESCE(op.open_icp, 0) AS open_icp, COALESCE(op.open_engaged, 0) AS open_engaged,
           COALESCE(op.open_first_submission, 0) AS open_first_submission, COALESCE(op.open_quoted, 0) AS open_quoted,
           r.r3 * r.r4 * r.r5 * r.r6 AS p_icp, r.r4 * r.r5 * r.r6 AS p_eng, r.r5 * r.r6 AS p_fs, r.r6 AS p_q,
           r.used_overall_economics,
           CASE WHEN r.used_overall_economics = 1 THEN ea.avg_commission ELSE e.avg_commission END AS avg_c,
           CASE WHEN r.used_overall_economics = 1 THEN ea.avg_premium ELSE e.avg_premium END AS avg_p
    FROM rates r LEFT JOIN open_pipe op ON op.segment = r.segment LEFT JOIN econ e ON e.segment = r.segment CROSS JOIN econ_all ea
)
SELECT segment, open_icp, open_engaged, open_first_submission, open_quoted,
       ROUND(p_icp, 4) AS p_bind_from_icp, ROUND(p_eng, 4) AS p_bind_from_engaged, ROUND(p_fs, 4) AS p_bind_from_first_submission, ROUND(p_q, 4) AS p_bind_from_quoted,
       ROUND(open_icp * p_icp + open_engaged * p_eng + open_first_submission * p_fs + open_quoted * p_q, 2) AS expected_new_bound_agencies,
       ROUND(avg_c, 2) AS avg_first_bind_commission, ROUND(avg_p, 2) AS avg_first_bind_premium,
       ROUND((open_icp * p_icp + open_engaged * p_eng + open_first_submission * p_fs + open_quoted * p_q) * avg_c, 2) AS projected_commission,
       ROUND((open_icp * p_icp + open_engaged * p_eng + open_first_submission * p_fs + open_quoted * p_q) * avg_p, 2) AS projected_premium,
       used_overall_economics
FROM proj ORDER BY projected_commission DESC, segment;
