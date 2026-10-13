-- Median hours from submission to quote, overall and by line of business / risk complexity.
-- scope 'all_submissions' = every quoted complete submission; 'first_submissions' = each agency's first complete submission.
-- Median = mean of the middle one/two ranks. Suppressed (NULL) when n < :min_n.
WITH base AS (
    SELECT s.agency_id, s.line_of_business, s.risk_complexity, s.quote_turnaround_hours AS h,
           CASE WHEN s.submitted_at = (SELECT MIN(s2.submitted_at) FROM submissions s2
                                       WHERE s2.agency_id = s.agency_id AND s2.is_complete = 1) THEN 1 ELSE 0 END AS is_first
    FROM submissions s WHERE s.is_complete = 1 AND s.quoted_at IS NOT NULL
),
grp AS (
    SELECT 'all_submissions' AS scope, 'overall' AS dimension, 'all' AS value, h FROM base
    UNION ALL SELECT 'all_submissions', 'line_of_business', line_of_business, h FROM base
    UNION ALL SELECT 'all_submissions', 'risk_complexity', risk_complexity, h FROM base
    UNION ALL SELECT 'first_submissions', 'overall', 'all', h FROM base WHERE is_first = 1
    UNION ALL SELECT 'first_submissions', 'risk_complexity', risk_complexity, h FROM base WHERE is_first = 1
),
ranked AS (
    SELECT scope, dimension, value, h,
           ROW_NUMBER() OVER (PARTITION BY scope, dimension, value ORDER BY h) AS rn,
           COUNT(*) OVER (PARTITION BY scope, dimension, value) AS n
    FROM grp
)
SELECT scope, dimension, value, n,
       CASE WHEN n < :min_n THEN NULL ELSE ROUND(AVG(h), 2) END AS median_hours,
       CASE WHEN n < :min_n THEN 1 ELSE 0 END AS suppressed
FROM ranked WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
GROUP BY scope, dimension, value, n
ORDER BY scope, dimension, value;
