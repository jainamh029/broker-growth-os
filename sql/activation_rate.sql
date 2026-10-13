-- Activation: share of engaged ICP agencies whose first complete submission arrives within :activation_days of engagement.
-- Cohort = month of engagement; only MATURE agencies (full window observed before :as_of) are counted. Suppressed when mature n < :min_n.
WITH e AS (SELECT agency_id, reached_at AS engaged_at FROM stage_events WHERE stage = 'engaged'),
f AS (SELECT agency_id, reached_at AS fs_at FROM stage_events WHERE stage = 'first_submission'),
pa AS (
    SELECT e.agency_id, substr(e.engaged_at, 1, 7) AS cohort,
           julianday(date(:as_of) || ' 23:59:59') - julianday(e.engaged_at) AS age_days,
           julianday(f.fs_at) - julianday(e.engaged_at) AS gap_days
    FROM e LEFT JOIN f ON f.agency_id = e.agency_id
),
cohorts AS (SELECT cohort, age_days, gap_days FROM pa UNION ALL SELECT 'ALL', age_days, gap_days FROM pa)
SELECT cohort, COUNT(*) AS engaged_agencies,
       SUM(CASE WHEN age_days >= :activation_days THEN 1 ELSE 0 END) AS mature_agencies,
       SUM(CASE WHEN age_days >= :activation_days AND gap_days <= :activation_days THEN 1 ELSE 0 END) AS activated_agencies,
       CASE WHEN SUM(CASE WHEN age_days >= :activation_days THEN 1 ELSE 0 END) < :min_n THEN NULL
            ELSE ROUND(1.0 * SUM(CASE WHEN age_days >= :activation_days AND gap_days <= :activation_days THEN 1 ELSE 0 END)
                       / SUM(CASE WHEN age_days >= :activation_days THEN 1 ELSE 0 END), 4) END AS activation_rate
FROM cohorts GROUP BY cohort ORDER BY CASE WHEN cohort = 'ALL' THEN 1 ELSE 0 END, cohort;
