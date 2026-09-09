-- Per day: raw trades vs trades taken on days the AI gate was consulted.
-- The join is deliberately loose (by entry day -> as_of day, NULLs allowed):
-- backtest rows have no broker ticket, so a fine-grained per-trade join is
-- not possible; this still shows whether gated days differ from ungated ones.
WITH ledger AS (
    SELECT
        entry_time::DATE AS day,
        r_multiple
    FROM {{ ref('mart_trade_ledger') }}
    WHERE entry_time IS NOT NULL
),
ai_days AS (
    SELECT DISTINCT try_cast(as_of AS DATE) AS day
    FROM {{ ref('stg_ai_calls') }}
    WHERE kind = 'propose_trade'
      AND as_of IS NOT NULL
),
all_days AS (
    SELECT
        day,
        COUNT(*) AS all_trades,
        AVG(r_multiple) AS avg_r_all,
        SUM(CASE WHEN r_multiple >= 0 THEN 1 ELSE 0 END) AS all_wins
    FROM ledger
    GROUP BY day
),
gated_days AS (
    SELECT
        l.day,
        COUNT(*) AS ai_trades,
        AVG(l.r_multiple) AS avg_r_ai
    FROM ledger AS l
    INNER JOIN ai_days AS a ON a.day = l.day
    GROUP BY l.day
)
SELECT
    a.day,
    a.all_trades,
    a.avg_r_all,
    a.all_wins,
    CASE WHEN a.all_trades > 0
         THEN a.all_wins * 1.0 / a.all_trades ELSE NULL END AS win_rate_all,
    COALESCE(g.ai_trades, 0) AS ai_consulted_trades,
    g.avg_r_ai
FROM all_days AS a
LEFT JOIN gated_days AS g ON g.day = a.day
ORDER BY a.day
