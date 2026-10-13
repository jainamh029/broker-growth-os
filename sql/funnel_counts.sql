-- Nested funnel: agencies reaching each stage, step conversion and cumulative conversion.
-- Stage order and definitions live in funnel.py; stage_events is derived from clean tables.
WITH c AS (
    SELECT stage, stage_order, COUNT(DISTINCT agency_id) AS agencies
    FROM stage_events GROUP BY stage, stage_order
),
top AS (SELECT agencies AS raw_n FROM c WHERE stage_order = 1)
SELECT c.stage, c.stage_order, c.agencies,
       ROUND(1.0 * c.agencies / NULLIF(LAG(c.agencies) OVER (ORDER BY c.stage_order), 0), 4) AS step_conversion,
       ROUND(1.0 * c.agencies / NULLIF(top.raw_n, 0), 4) AS cumulative_conversion
FROM c, top ORDER BY c.stage_order;
