import Badge, { toneFor } from "@/components/Badge";
import RefreshButton from "@/components/RefreshButton";
import Sparkline from "@/components/Sparkline";
import WarehouseEmpty from "@/components/WarehouseEmpty";
import { isWarehouseReady, query } from "@/lib/duckdb";

export const dynamic = "force-dynamic";

interface NewsRow {
  day: string;
  article_count: number;
  avg_score: number | null;
  positive_count: number;
  negative_count: number;
  top_titles: string[];
}

interface TableRow {
  table_name: string;
}

export default async function NewsPage() {
  if (!(await isWarehouseReady())) return <WarehouseEmpty />;

  const tables = await query<TableRow>(
    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'",
  );
  const hasNews = tables.some((t) => t.table_name === "mart_news_sentiment_daily");
  if (!hasNews) {
    return (
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">News Sentiment</h1>
            <p className="text-sm text-zinc-500">Daily lexicon sentiment from the RSS pipeline.</p>
          </div>
          <RefreshButton />
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-8 text-center text-sm text-zinc-500">
          No news data yet — run the news pipeline:
          <pre className="mx-auto mt-4 inline-block rounded bg-zinc-900 px-4 py-3 font-mono text-xs text-zinc-300">
            {`python scripts/news.py fetch\npython scripts/news.py sentiment\ncd dbt && dbt run --select stg_news_articles+ mart_news_sentiment_daily`}
          </pre>
        </div>
      </div>
    );
  }

  const rows = await query<NewsRow>(
    "SELECT day, article_count, avg_score, positive_count, negative_count, " +
      "top_titles FROM mart_news_sentiment_daily ORDER BY day DESC",
  );

  const scores = [...rows].reverse().map((r) => (r.avg_score == null ? 0 : Number(r.avg_score)));
  const today = rows[0];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">News Sentiment</h1>
          <p className="text-sm text-zinc-500">Daily lexicon sentiment from the RSS pipeline.</p>
        </div>
        <RefreshButton />
      </div>

      {today ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Latest score</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">
              <Badge value={Number(today.avg_score).toFixed(2)} tone={toneFor(String(today.avg_score))} />
            </div>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Articles</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">{today.article_count}</div>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Positive / Negative</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">
              <span className="text-emerald-400">{today.positive_count}</span>
              <span className="mx-1 text-zinc-600">/</span>
              <span className="text-red-400">{today.negative_count}</span>
            </div>
          </div>
        </div>
      ) : null}

      {scores.length >= 2 ? (
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Daily sentiment score
          </h2>
          <Sparkline values={scores} stroke="#34d399" />
        </section>
      ) : null}

      {today?.top_titles && Array.isArray(today.top_titles) && (today.top_titles as string[]).length > 0 ? (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Top headlines
          </h2>
          <ul className="space-y-2">
            {(today.top_titles as string[]).map((title, i) => (
              <li key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm text-zinc-300">
                {title}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
