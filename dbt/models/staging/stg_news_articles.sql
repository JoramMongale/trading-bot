SELECT
    published_ts::TIMESTAMP AS published_ts,
    title,
    link,
    source_feed,
    description,
    score::DOUBLE AS score,
    fetched_at::TIMESTAMP AS fetched_at
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY link
            ORDER BY fetched_at DESC
        ) AS _rn
    FROM {{ source('trading_bot', 'raw_news_articles') }}
) AS src
WHERE _rn = 1
  AND title IS NOT NULL
  AND link IS NOT NULL
