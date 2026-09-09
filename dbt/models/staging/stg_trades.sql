SELECT
    source,
    entry_time::TIMESTAMP AS entry_time,
    entry::DOUBLE AS entry,
    sl::DOUBLE AS sl,
    tp::DOUBLE AS tp,
    exit_time::TIMESTAMP AS exit_time,
    exit_price::DOUBLE AS exit_price,
    exit_reason,
    pnl_points::DOUBLE AS pnl_points,
    r_multiple::DOUBLE AS r_multiple,
    loaded_at
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY source, entry_time, entry
            ORDER BY loaded_at
        ) AS _rn
    FROM {{ source('trading_bot', 'raw_trades') }}
) AS src
WHERE _rn = 1
  AND entry_time IS NOT NULL
  AND entry IS NOT NULL
