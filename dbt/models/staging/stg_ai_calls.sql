SELECT
    source_file,
    ts,
    kind,
    as_of,
    context,
    result,
    json_extract_string(result, '$.bias') AS bias,
    try_cast(json_extract_string(result, '$.confidence') AS DOUBLE) AS confidence,
    json_extract_string(result, '$.regime') AS regime,
    json_extract_string(result, '$.tradeable') AS tradeable,
    json_extract_string(result, '$.reasoning') AS reasoning,
    json_extract_string(result, '$.invalidation') AS invalidation,
    loaded_at
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY source_file, ts
            ORDER BY loaded_at
        ) AS _rn
    FROM {{ source('trading_bot', 'raw_ai_calls') }}
) AS src
WHERE _rn = 1
