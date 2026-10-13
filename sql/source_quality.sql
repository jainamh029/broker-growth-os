-- Source quality by DOWNSTREAM outcomes (bound, repeat, commission), never by lead count alone.
-- Rates are suppressed (NULL) when the denominator is below :min_n.
WITH reach AS (
    SELECT a.lead_source,
           COUNT(DISTINCT a.agency_id) AS leads,
           COUNT(DISTINCT CASE WHEN se.stage = 'icp_qualified' THEN a.agency_id END) AS icp_agencies,
           COUNT(DISTINCT CASE WHEN se.stage = 'engaged' THEN a.agency_id END) AS engaged_agencies,
           COUNT(DISTINCT CASE WHEN se.stage = 'first_submission' THEN a.agency_id END) AS first_submissions,
           COUNT(DISTINCT CASE WHEN se.stage = 'bound' THEN a.agency_id END) AS bound_agencies,
           COUNT(DISTINCT CASE WHEN se.stage = 'repeat_submission' THEN a.agency_id END) AS repeat_agencies
    FROM agencies a LEFT JOIN stage_events se ON se.agency_id = a.agency_id
    GROUP BY a.lead_source
),
comm AS (
    SELECT a.lead_source, COALESCE(SUM(s.commission), 0) AS commission
    FROM agencies a LEFT JOIN submissions s ON s.agency_id = a.agency_id AND s.bound_at IS NOT NULL
    GROUP BY a.lead_source
)
SELECT r.lead_source, r.leads, r.icp_agencies, r.engaged_agencies, r.first_submissions, r.bound_agencies, r.repeat_agencies,
       CASE WHEN r.leads < :min_n THEN NULL ELSE ROUND(1.0 * r.first_submissions / r.leads, 4) END AS first_submission_rate,
       CASE WHEN r.leads < :min_n THEN NULL ELSE ROUND(1.0 * r.bound_agencies / r.leads, 4) END AS bind_rate_per_lead,
       CASE WHEN r.bound_agencies < :min_n THEN NULL ELSE ROUND(1.0 * r.repeat_agencies / r.bound_agencies, 4) END AS repeat_rate_of_bound,
       CASE WHEN r.leads < :min_n THEN NULL ELSE ROUND(1.0 * c.commission / r.leads, 2) END AS commission_per_lead,
       ROUND(c.commission, 2) AS total_commission,
       CASE WHEN r.leads < :min_n THEN 1 ELSE 0 END AS suppressed
FROM reach r JOIN comm c ON c.lead_source = r.lead_source
ORDER BY r.leads DESC, r.lead_source;
