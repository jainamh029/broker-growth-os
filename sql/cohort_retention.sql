-- Cohort retention: share of first-submission agencies that send ANOTHER complete submission within 30/60/90 days.
-- Cohort = month of first complete submission. Only MATURE agencies (a full window observed before :as_of) are in each denominator.
-- Rates suppressed (NULL) when mature n < :min_n.
WITH fs AS (SELECT agency_id, reached_at AS fs_at FROM stage_events WHERE stage = 'first_submission'),
nxt AS (
    SELECT f.agency_id, MIN(s.submitted_at) AS next_at
    FROM fs f JOIN submissions s ON s.agency_id = f.agency_id AND s.is_complete = 1 AND s.submitted_at > f.fs_at
    GROUP BY f.agency_id
),
pa AS (
    SELECT f.agency_id, substr(f.fs_at, 1, 7) AS cohort,
           julianday(date(:as_of) || ' 23:59:59') - julianday(f.fs_at) AS age_days,
           julianday(n.next_at) - julianday(f.fs_at) AS gap_days
    FROM fs f LEFT JOIN nxt n ON n.agency_id = f.agency_id
),
cohorts AS (SELECT cohort, age_days, gap_days FROM pa UNION ALL SELECT 'ALL', age_days, gap_days FROM pa)
SELECT cohort, COUNT(*) AS agencies,
       SUM(CASE WHEN age_days >= 30 THEN 1 ELSE 0 END) AS mature_30,
       SUM(CASE WHEN age_days >= 30 AND gap_days <= 30 THEN 1 ELSE 0 END) AS repeat_30,
       CASE WHEN SUM(CASE WHEN age_days >= 30 THEN 1 ELSE 0 END) < :min_n THEN NULL
            ELSE ROUND(1.0 * SUM(CASE WHEN age_days >= 30 AND gap_days <= 30 THEN 1 ELSE 0 END) / SUM(CASE WHEN age_days >= 30 THEN 1 ELSE 0 END), 4) END AS retention_30,
       SUM(CASE WHEN age_days >= 60 THEN 1 ELSE 0 END) AS mature_60,
       SUM(CASE WHEN age_days >= 60 AND gap_days <= 60 THEN 1 ELSE 0 END) AS repeat_60,
       CASE WHEN SUM(CASE WHEN age_days >= 60 THEN 1 ELSE 0 END) < :min_n THEN NULL
            ELSE ROUND(1.0 * SUM(CASE WHEN age_days >= 60 AND gap_days <= 60 THEN 1 ELSE 0 END) / SUM(CASE WHEN age_days >= 60 THEN 1 ELSE 0 END), 4) END AS retention_60,
       SUM(CASE WHEN age_days >= 90 THEN 1 ELSE 0 END) AS mature_90,
       SUM(CASE WHEN age_days >= 90 AND gap_days <= 90 THEN 1 ELSE 0 END) AS repeat_90,
       CASE WHEN SUM(CASE WHEN age_days >= 90 THEN 1 ELSE 0 END) < :min_n THEN NULL
            ELSE ROUND(1.0 * SUM(CASE WHEN age_days >= 90 AND gap_days <= 90 THEN 1 ELSE 0 END) / SUM(CASE WHEN age_days >= 90 THEN 1 ELSE 0 END), 4) END AS retention_90
FROM cohorts GROUP BY cohort ORDER BY CASE WHEN cohort = 'ALL' THEN 1 ELSE 0 END, cohort;
