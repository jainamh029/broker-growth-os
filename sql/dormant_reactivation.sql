-- Dormant agencies worth reactivating (tier = Reactivation), ranked by prior bound premium, then fit score.
WITH prior AS (
    SELECT agency_id,
           COUNT(*) AS prior_complete_submissions,
           MAX(date(submitted_at)) AS last_submission_date,
           COALESCE(SUM(CASE WHEN bound_at IS NOT NULL THEN premium END), 0) AS prior_bound_premium,
           COALESCE(SUM(CASE WHEN bound_at IS NOT NULL THEN commission END), 0) AS prior_commission
    FROM submissions WHERE is_complete = 1 GROUP BY agency_id
)
SELECT ROW_NUMBER() OVER (ORDER BY p.prior_bound_premium DESC, r.score DESC, r.agency_id) AS priority_rank,
       r.agency_id, r.name, r.owner, a.state, a.specialty_focus,
       p.last_submission_date,
       CAST(julianday(date(:as_of)) - julianday(p.last_submission_date) AS INTEGER) AS days_dormant,
       p.prior_complete_submissions, p.prior_bound_premium, p.prior_commission, r.score
FROM ranked_accounts r JOIN prior p ON p.agency_id = r.agency_id JOIN agencies a ON a.agency_id = r.agency_id
WHERE r.tier = 'Reactivation'
ORDER BY priority_rank;
