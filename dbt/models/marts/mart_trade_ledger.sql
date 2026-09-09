-- Backtest + live trades in one ledger. Backtest rows come from stg_trades
-- (no ticket — the backtest has no broker); live rows come from stg_closes
-- (watch_closes.py trade_closed lines, keyed by broker ticket). `source`
-- separates the two; a null entry_time marks a live close whose log line did
-- not carry the entry time.
SELECT
    'backtest' AS source,
    entry_time,
    entry, sl, tp,
    exit_time,
    exit_price,
    exit_reason,
    r_multiple,
    NULL AS ticket,
    NULL AS profit,
    NULL AS how,
    loaded_at
FROM {{ ref('stg_trades') }}

UNION ALL

SELECT
    'live' AS source,
    NULL AS entry_time,
    entry,
    NULL AS sl,
    NULL AS tp,
    event_time AS exit_time,
    exit_price,
    how AS exit_reason,
    COALESCE(r_multiple, r) AS r_multiple,
    ticket,
    profit,
    how,
    loaded_at
FROM {{ ref('stg_closes') }}
