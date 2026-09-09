SELECT
    source_log,
    line_number,
    try_strptime(ts, '%Y-%m-%d %H:%M:%S') AS event_time,
    fields,
    json_extract_string(fields, '$.ticket') AS ticket,
    json_extract_string(fields, '$.symbol') AS symbol,
    json_extract_string(fields, '$.how') AS how,
    try_cast(json_extract_string(fields, '$.r_multiple') AS DOUBLE) AS r_multiple,
    try_cast(json_extract_string(fields, '$.r') AS DOUBLE) AS r,
    try_cast(json_extract_string(fields, '$.profit') AS DOUBLE) AS profit,
    try_cast(json_extract_string(fields, '$.entry') AS DOUBLE) AS entry,
    try_cast(json_extract_string(fields, '$.exit') AS DOUBLE) AS exit_price,
    line,
    loaded_at
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY source_log, line_number
            ORDER BY loaded_at
        ) AS _rn
    FROM {{ source('trading_bot', 'raw_closes') }}
) AS src
WHERE _rn = 1
