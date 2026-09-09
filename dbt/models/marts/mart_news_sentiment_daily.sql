-- Per fetch-day: article count, average lexicon sentiment, positive/negative
-- counts, and the five most strongly-scored headlines. This is the daily
-- number the dashboard and (via the snapshot) the AI regime reader see.
WITH scored AS (
    SELECT
        fetched_at::DATE AS day,
        title,
        score,
        ROW_NUMBER() OVER (
            PARTITION BY fetched_at::DATE
            ORDER BY abs(score) DESC, fetched_at DESC
        ) AS rn
    FROM {{ ref('stg_news_articles') }}
    WHERE score IS NOT NULL
),
daily AS (
    SELECT
        day,
        COUNT(*) AS article_count,
        AVG(score) AS avg_score,
        COUNT(*) FILTER (WHERE score > 0) AS positive_count,
        COUNT(*) FILTER (WHERE score < 0) AS negative_count
    FROM scored
    GROUP BY day
),
tops AS (
    SELECT
        day,
        list(title) AS top_titles
    FROM (
        SELECT day, title
        FROM scored
        WHERE rn <= 5
        ORDER BY day, rn
    ) t
    GROUP BY day
)
SELECT
    d.day,
    d.article_count,
    d.avg_score,
    d.positive_count,
    d.negative_count,
    t.top_titles
FROM daily AS d
LEFT JOIN tops AS t USING (day)
ORDER BY d.day
