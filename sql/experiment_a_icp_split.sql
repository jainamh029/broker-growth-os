-- OBSERVATIONAL (not an experiment): first-submission rate of ICP vs non-ICP agencies WITHIN Experiment A's control arm,
-- same outcome window (:window_a days from first touch) and mature-only rule as Experiment A. Wilson CIs are added in metrics.py.
SELECT a.is_icp AS is_icp, COUNT(*) AS n,
       SUM(CASE WHEN EXISTS (
           SELECT 1 FROM submissions s
           WHERE s.agency_id = ea.agency_id AND s.is_complete = 1
             AND date(s.submitted_at) >= date(ea.assigned_at)
             AND date(s.submitted_at) <= date(ea.assigned_at, '+' || :window_a || ' days')
       ) THEN 1 ELSE 0 END) AS x
FROM experiment_assignments ea JOIN agencies a ON a.agency_id = ea.agency_id
WHERE ea.experiment_id = 'A' AND ea.arm = 'control'
  AND date(ea.assigned_at, '+' || :window_a || ' days') <= date(:as_of)
GROUP BY a.is_icp ORDER BY a.is_icp DESC;
