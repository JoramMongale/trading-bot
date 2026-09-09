SELECT
    source_log,
    line_number,
    try_strptime(ts, '%Y-%m-%d %H:%M:%S') AS event_time,
    level,
    event,
    fields,
    line,
    loaded_at
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY source_log, line_number
            ORDER BY loaded_at
        ) AS _rn
    FROM {{ source('trading_bot', 'raw_decisions') }}
) AS src
WHERE _rn = 1
