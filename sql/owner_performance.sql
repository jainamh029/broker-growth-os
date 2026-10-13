-- Growth owner performance on downstream conversion (not activity volume). Rates suppressed when denominator < :min_n.
WITH r AS (
    SELECT a.owner,
           COUNT(DISTINCT a.agency_id) AS agencies,
           COUNT(DISTINCT CASE WHEN se.stage = 'icp_qualified' THEN a.agency_id END) AS icp_agencies,
           COUNT(DISTINCT CASE WHEN se.stage = 'engaged' THEN a.agency_id END) AS engaged_agencies,
           COUNT(DISTINCT CASE WHEN se.stage = 'first_submission' THEN a.agency_id END) AS first_submissions,
           COUNT(DISTINCT CASE WHEN se.stage = 'bound' THEN a.agency_id END) AS bound_agencies
    FROM agencies a LEFT JOIN stage_events se ON se.agency_id = a.agency_id GROUP BY a.owner
),
c AS (
    SELECT a.owner, COALESCE(SUM(s.commission), 0) AS commission
    FROM agencies a LEFT JOIN submissions s ON s.agency_id = a.agency_id AND s.bound_at IS NOT NULL GROUP BY a.owner
)
SELECT r.owner, r.agencies, r.icp_agencies, r.engaged_agencies, r.first_submissions, r.bound_agencies,
       CASE WHEN r.icp_agencies < :min_n THEN NULL ELSE ROUND(1.0 * r.engaged_agencies / r.icp_agencies, 4) END AS engagement_rate,
       CASE WHEN r.engaged_agencies < :min_n THEN NULL ELSE ROUND(1.0 * r.first_submissions / r.engaged_agencies, 4) END AS activation_rate,
       CASE WHEN r.first_submissions < :min_n THEN NULL ELSE ROUND(1.0 * r.bound_agencies / r.first_submissions, 4) END AS bind_rate_of_submitters,
       CASE WHEN r.agencies < :min_n THEN NULL ELSE ROUND(1.0 * c.commission / r.agencies, 2) END AS commission_per_agency,
       ROUND(c.commission, 2) AS total_commission
FROM r JOIN c ON c.owner = r.owner ORDER BY r.owner;
