-- Assumption-driven projection of first-bind revenue from OPEN pipeline, by segment (= specialty focus).
-- Assumptions (documented in README/DECISIONS): (1) an agency is open if its highest stage is ICP-qualified, engaged,
-- first submission or quoted AND its last activity is within :open_days of :as_of; (2) it converts to a bind with the
-- observed probability P(bound | reached stage) of its segment (overall rate when the segment has < :min_n agencies at that stage);
-- (3) revenue per bound agency = observed average first-bound commission (overall average when segment bound < :min_n);
-- (4) repeat revenue is excluded (conservative). Stage rates are measured on all agencies, including still-open ones.
WITH reach AS (
    SELECT a.specialty_focus AS segment,
           SUM(CASE WHEN se.stage_order = 2 THEN 1 ELSE 0 END) AS r2,
           SUM(CASE WHEN se.stage_order = 3 THEN 1 ELSE 0 END) AS r3,
           SUM(CASE WHEN se.stage_order = 4 THEN 1 ELSE 0 END) AS r4,
           SUM(CASE WHEN se.stage_order = 5 THEN 1 ELSE 0 END) AS r5,
           SUM(CASE WHEN se.stage_order = 6 THEN 1 ELSE 0 END) AS r6
    FROM agencies a JOIN stage_events se ON se.agency_id = a.agency_id GROUP BY a.specialty_focus
),
overall AS (
    SELECT SUM(r2) AS r2, SUM(r3) AS r3, SUM(r4) AS r4, SUM(r5) AS r5, SUM(r6) AS r6 FROM reach
),
top_stage_cte AS (
    SELECT a.agency_id, a.specialty_focus AS segment, a.last_activity_date, MAX(se.stage_order) AS top_stage
    FROM agencies a JOIN stage_events se ON se.agency_id = a.agency_id GROUP BY a.agency_id
),
open_pipe AS (
    SELECT segment,
           SUM(CASE WHEN top_stage = 2 THEN 1 ELSE 0 END) AS open_icp,
           SUM(CASE WHEN top_stage = 3 THEN 1 ELSE 0 END) AS open_engaged,
           SUM(CASE WHEN top_stage = 4 THEN 1 ELSE 0 END) AS open_first_submission,
           SUM(CASE WHEN top_stage = 5 THEN 1 ELSE 0 END) AS open_quoted
    FROM top_stage_cte
    WHERE top_stage BETWEEN 2 AND 5
      AND julianday(date(:as_of)) - julianday(date(last_activity_date)) <= :open_days
    GROUP BY segment
),
first_bind AS (
    SELECT a.specialty_focus AS segment, s.agency_id, s.commission, s.premium,
           ROW_NUMBER() OVER (PARTITION BY s.agency_id ORDER BY s.bound_at) AS rn
    FROM submissions s JOIN agencies a ON a.agency_id = s.agency_id
    WHERE s.is_complete = 1 AND s.bound_at IS NOT NULL
),
econ AS (
    SELECT segment, COUNT(*) AS n_bound, AVG(commission) AS avg_commission, AVG(premium) AS avg_premium
    FROM first_bind WHERE rn = 1 GROUP BY segment
),
econ_all AS (SELECT AVG(commission) AS avg_commission, AVG(premium) AS avg_premium FROM first_bind WHERE rn = 1),
rates AS (
    SELECT r.segment,
           CASE WHEN r.r2 < :min_n THEN 1.0 * o.r6 / o.r2 ELSE 1.0 * r.r6 / r.r2 END AS p_bind_from_icp,
           CASE WHEN r.r3 < :min_n THEN 1.0 * o.r6 / o.r3 ELSE 1.0 * r.r6 / r.r3 END AS p_bind_from_engaged,
           CASE WHEN r.r4 < :min_n THEN 1.0 * o.r6 / o.r4 ELSE 1.0 * r.r6 / r.r4 END AS p_bind_from_first_submission,
           CASE WHEN r.r5 < :min_n THEN 1.0 * o.r6 / o.r5 ELSE 1.0 * r.r6 / r.r5 END AS p_bind_from_quoted,
           CASE WHEN r.r6 < :min_n THEN 1 ELSE 0 END AS used_overall_economics
    FROM reach r, overall o
)
SELECT r.segment,
       COALESCE(op.open_icp, 0) AS open_icp, COALESCE(op.open_engaged, 0) AS open_engaged,
       COALESCE(op.open_first_submission, 0) AS open_first_submission, COALESCE(op.open_quoted, 0) AS open_quoted,
       ROUND(r.p_bind_from_icp, 4) AS p_bind_from_icp, ROUND(r.p_bind_from_engaged, 4) AS p_bind_from_engaged,
       ROUND(r.p_bind_from_first_submission, 4) AS p_bind_from_first_submission, ROUND(r.p_bind_from_quoted, 4) AS p_bind_from_quoted,
       ROUND(COALESCE(op.open_icp, 0) * r.p_bind_from_icp + COALESCE(op.open_engaged, 0) * r.p_bind_from_engaged
             + COALESCE(op.open_first_submission, 0) * r.p_bind_from_first_submission
             + COALESCE(op.open_quoted, 0) * r.p_bind_from_quoted, 2) AS expected_new_bound_agencies,
       ROUND(CASE WHEN r.used_overall_economics = 1 THEN ea.avg_commission ELSE e.avg_commission END, 2) AS avg_first_bind_commission,
       ROUND(CASE WHEN r.used_overall_economics = 1 THEN ea.avg_premium ELSE e.avg_premium END, 2) AS avg_first_bind_premium,
       ROUND((COALESCE(op.open_icp, 0) * r.p_bind_from_icp + COALESCE(op.open_engaged, 0) * r.p_bind_from_engaged
              + COALESCE(op.open_first_submission, 0) * r.p_bind_from_first_submission
              + COALESCE(op.open_quoted, 0) * r.p_bind_from_quoted)
             * CASE WHEN r.used_overall_economics = 1 THEN ea.avg_commission ELSE e.avg_commission END, 2) AS projected_commission,
       ROUND((COALESCE(op.open_icp, 0) * r.p_bind_from_icp + COALESCE(op.open_engaged, 0) * r.p_bind_from_engaged
              + COALESCE(op.open_first_submission, 0) * r.p_bind_from_first_submission
              + COALESCE(op.open_quoted, 0) * r.p_bind_from_quoted)
             * CASE WHEN r.used_overall_economics = 1 THEN ea.avg_premium ELSE e.avg_premium END, 2) AS projected_premium,
       r.used_overall_economics
FROM rates r
LEFT JOIN open_pipe op ON op.segment = r.segment
LEFT JOIN econ e ON e.segment = r.segment
CROSS JOIN econ_all ea
ORDER BY projected_commission DESC, r.segment;
