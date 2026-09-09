import { isWarehouseReady, query } from "@/lib/duckdb";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    if (!(await isWarehouseReady())) {
      return Response.json(
        { error: "warehouse not loaded", detail: "run the 03-03 loader + dbt first" },
        { status: 503 },
      );
    }
    // mart_news_sentiment_daily is built by the parallel plan 03-04 and may
    // not exist yet — empty news is a valid state, not an outage (200 + []).
    const tables = await query<{ table_name: string }>(
      "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'",
    );
    const hasNews = tables.some((t) => t.table_name === "mart_news_sentiment_daily");
    if (!hasNews) {
      return Response.json({ rows: [] });
    }
    const rows = await query(
      "SELECT day, article_count, avg_score, positive_count, negative_count, " +
        "top_titles FROM mart_news_sentiment_daily ORDER BY day DESC",
    );
    return Response.json({ rows });
  } catch (err) {
    return Response.json(
      { error: "warehouse not loaded", detail: String(err) },
      { status: 503 },
    );
  }
}
