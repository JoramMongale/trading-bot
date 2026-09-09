SELECT
    time::TIMESTAMP AS time,
    open::DOUBLE AS open,
    high::DOUBLE AS high,
    low::DOUBLE AS low,
    close::DOUBLE AS close,
    symbol,
    timeframe,
    source_file,
    loaded_at
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY source_file, time
            ORDER BY loaded_at
        ) AS _rn
    FROM {{ source('trading_bot', 'raw_bars') }}
) AS src
WHERE _rn = 1
  AND time IS NOT NULL
