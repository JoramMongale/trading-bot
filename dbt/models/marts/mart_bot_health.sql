-- Per decision-log file: poll freshness for the dashboard. last_event_ts is
-- the newest SAFE-02 line in the file; last_bar_checked is the newest bar the
-- log processed; bar_fetch_failed_24h counts dead polls in the last 24h of
-- that log's own history (so historical logs still produce a meaningful
-- freshness figure rather than a count across their whole span).
WITH decisions AS (
    SELECT
        source_log,
        event_time,
        event,
        json_extract_string(fields, '$.bar') AS bar,
        json_extract_string(fields, '$.reason') AS reason
    FROM {{ ref('stg_decisions') }}
    WHERE event_time IS NOT NULL
),
agg AS (
    SELECT
        source_log,
        MAX(event_time) AS last_event_ts,
        MAX(event_time) - INTERVAL '24 hours' AS cut_off,
        MAX(event) AS last_event
    FROM decisions
    GROUP BY source_log
)
SELECT
    d.source_log,
    a.last_event_ts,
    a.last_event,
    MAX(d.bar) AS last_bar_checked,
    COUNT(CASE WHEN d.event = 'bar_fetch_failed' AND d.event_time >= a.cut_off THEN 1 END) AS bar_fetch_failed_24h,
    COUNT(CASE WHEN d.event = 'bar_fetch_failed' THEN 1 END) AS bar_fetch_failed_total,
    COUNT(CASE WHEN d.event = 'order_placed' THEN 1 END) AS orders_placed
FROM decisions AS d
LEFT JOIN agg AS a ON a.source_log = d.source_log
GROUP BY d.source_log, a.last_event_ts, a.last_event, a.cut_off
