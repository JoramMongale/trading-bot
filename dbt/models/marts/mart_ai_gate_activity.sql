-- Per UTC day: how the AI gate treated the deterministic setups.
-- Consultations = ai_proposal lines; approved = verdict=APPROVED; blocked =
-- verdict=BLOCKED; rejected = order_skipped reason=ai_rejected; unavailable =
-- order_skipped reason=ai_unavailable (transport failure, fail CLOSED).
-- Approval rate = approved / consultations.
WITH decisions AS (
    SELECT
        event_time::DATE AS day,
        event,
        fields
    FROM {{ ref('stg_decisions') }}
    WHERE event_time IS NOT NULL
),
props AS (
    SELECT day, COUNT(*) AS consultations
    FROM decisions
    WHERE event = 'ai_proposal'
    GROUP BY day
),
approved AS (
    SELECT day, COUNT(*) AS approved
    FROM decisions
    WHERE event = 'ai_proposal'
      AND json_extract_string(fields, '$.verdict') = 'APPROVED'
    GROUP BY day
),
blocked AS (
    SELECT day, COUNT(*) AS blocked
    FROM decisions
    WHERE event = 'ai_proposal'
      AND json_extract_string(fields, '$.verdict') = 'BLOCKED'
    GROUP BY day
),
rejected AS (
    SELECT day, COUNT(*) AS rejected
    FROM decisions
    WHERE event = 'order_skipped'
      AND json_extract_string(fields, '$.reason') = 'ai_rejected'
    GROUP BY day
),
unavailable AS (
    SELECT day, COUNT(*) AS unavailable
    FROM decisions
    WHERE event = 'order_skipped'
      AND json_extract_string(fields, '$.reason') = 'ai_unavailable'
    GROUP BY day
)
SELECT
    p.day,
    p.consultations,
    COALESCE(a.approved, 0) AS approved,
    COALESCE(b.blocked, 0) AS blocked,
    COALESCE(r.rejected, 0) AS rejected,
    COALESCE(u.unavailable, 0) AS unavailable,
    CASE
        WHEN p.consultations > 0
        THEN COALESCE(a.approved, 0) * 1.0 / p.consultations
        ELSE NULL
    END AS approval_rate
FROM props AS p
LEFT JOIN approved AS a ON a.day = p.day
LEFT JOIN blocked AS b ON b.day = p.day
LEFT JOIN rejected AS r ON r.day = p.day
LEFT JOIN unavailable AS u ON u.day = p.day
ORDER BY p.day
