-- One row per experiment assignment with its binary outcome.
-- A: complete submission within :window_a days of assignment (first touch).
-- B: complete submission within :window_b days of assignment (engagement).
-- C: complete submission within :window_c days AFTER assignment (reactivation date T0).
-- mature = the full outcome window ended on/before :as_of (immature units are excluded by experiments.py).
WITH base AS (
    SELECT ea.experiment_id, ea.agency_id, ea.arm, ea.assigned_at,
           CASE ea.experiment_id WHEN 'A' THEN :window_a WHEN 'B' THEN :window_b ELSE :window_c END AS window_days
    FROM experiment_assignments ea
)
SELECT b.experiment_id, b.agency_id, b.arm, b.assigned_at, b.window_days,
       CASE WHEN date(b.assigned_at, '+' || b.window_days || ' days') <= date(:as_of) THEN 1 ELSE 0 END AS mature,
       CASE WHEN EXISTS (
           SELECT 1 FROM submissions s
           WHERE s.agency_id = b.agency_id AND s.is_complete = 1
             AND (date(s.submitted_at) > date(b.assigned_at) OR (b.experiment_id <> 'C' AND date(s.submitted_at) = date(b.assigned_at)))
             AND date(s.submitted_at) <= date(b.assigned_at, '+' || b.window_days || ' days')
       ) THEN 1 ELSE 0 END AS outcome
FROM base b ORDER BY b.experiment_id, b.agency_id;
