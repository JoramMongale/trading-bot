import Badge, { toneFor } from "@/components/Badge";
import RefreshButton from "@/components/RefreshButton";
import StatCard from "@/components/StatCard";
import { isWarehouseReady, query } from "@/lib/duckdb";

export const dynamic = "force-dynamic";

interface HealthRow {
  source_log: string;
  last_event_ts: string;
  last_event: string | null;
  last_bar_checked: string | null;
  bar_fetch_failed_24h: number;
  orders_placed: number;
}

interface OpenRow {
  source: string;
  entry_time: string | null;
  entry: number;
  sl: number;
  tp: number;
  exit_reason: string | null;
  r_multiple: number | null;
  ticket: string | null;
}

interface AiRow {
  day: string;
  consultations: number;
  approved: number;
  approval_rate: number | null;
}

interface LatestRow {
  latest_entry: string | null;
}

interface LiveOrderRow {
  source_log: string;
  ts: string;
  ticket: string;
  entry: string;
  sl: string;
  tp: string;
}

interface ClosedRow {
  ticket: string;
}

export default async function OverviewPage() {
  if (!(await isWarehouseReady())) {
    return <WarehouseEmpty />;
  }

  const [health, open, ai, latest, orders, closed] = await Promise.all([
    query<HealthRow>(
      "SELECT source_log, last_event_ts, last_event, last_bar_checked, " +
        "bar_fetch_failed_24h, orders_placed FROM mart_bot_health ORDER BY source_log",
    ),
    query<OpenRow>(
      "SELECT source, entry_time, entry, sl, tp, exit_reason, r_multiple, ticket " +
        "FROM mart_trade_ledger " +
        "WHERE exit_reason IS NULL OR exit_price IS NULL ORDER BY entry_time DESC LIMIT 20",
    ),
    query<AiRow>(
      "SELECT day, consultations, approved, approval_rate " +
        "FROM mart_ai_gate_activity ORDER BY day DESC LIMIT 1",
    ),
    query<LatestRow>("SELECT max(entry_time) AS latest_entry FROM mart_trade_ledger"),
    query<LiveOrderRow>(
      "SELECT source_log, ts, " +
        "json_extract_string(fields, '$.ticket') AS ticket, " +
        "json_extract_string(fields, '$.entry') AS entry, " +
        "json_extract_string(fields, '$.sl') AS sl, " +
        "json_extract_string(fields, '$.tp') AS tp " +
        "FROM raw_decisions WHERE event = 'order_placed' ORDER BY ts DESC",
    ),
    query<ClosedRow>(
      "SELECT DISTINCT json_extract_string(fields, '$.ticket') AS ticket FROM raw_closes",
    ),
  ]);

  const closedTickets = new Set(closed.map((r) => String(r.ticket)));
  const seenLogs = new Set<string>();
  const liveOpen = orders
    .filter((o) => o.ticket && !seenLogs.has(o.source_log))
    .map((o) => {
      seenLogs.add(o.source_log);
      return {
        source_log: o.source_log,
        ticket: String(o.ticket),
        entry: Number(o.entry),
        sl: Number(o.sl),
        tp: Number(o.tp),
        open: !closedTickets.has(String(o.ticket)),
      };
    })
    .filter((o) => o.open);

  const aiToday = ai[0];
  const latestEntry = latest[0]?.latest_entry ?? null;
  const openCount = liveOpen.length + open.length;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Overview</h1>
          <p className="text-sm text-zinc-500">
            Live bot status, open exposure, and the AI gate&apos;s read on today.
          </p>
        </div>
        <RefreshButton />
      </div>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Decision logs" value={health.length} subtext="bots being monitored" />
        <StatCard
          label="Open positions"
          value={openCount}
          tone={openCount > 0 ? "warn" : "default"}
          subtext={openCount > 0 ? "exposure to the market" : "no open exposure"}
        />
        <StatCard
          label="Latest ledger entry"
          value={latestEntry ? String(latestEntry).slice(0, 10) : "—"}
          subtext={latestEntry ? String(latestEntry).slice(11, 19) : "no trades loaded"}
        />
        <StatCard
          label="Today AI approval rate"
          value={aiToday ? `${(Number(aiToday.approval_rate) * 100).toFixed(0)}%` : "—"}
          subtext={aiToday ? `${aiToday.consultations} consultations` : "no AI activity loaded"}
        />
      </section>

      {liveOpen.length > 0 ? (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Open live positions
          </h2>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/60 text-left text-xs uppercase tracking-wide text-zinc-500">
                  <th className="px-3 py-2 font-medium">Bot log</th>
                  <th className="px-3 py-2 font-medium">Ticket</th>
                  <th className="px-3 py-2 font-medium">Entry</th>
                  <th className="px-3 py-2 font-medium">SL</th>
                  <th className="px-3 py-2 font-medium">TP</th>
                </tr>
              </thead>
              <tbody>
                {liveOpen.map((row, i) => (
                  <tr key={i} className="border-b border-zinc-800/60 last:border-0">
                    <td className="px-3 py-2 font-mono text-xs text-zinc-300">{row.source_log}</td>
                    <td className="px-3 py-2 tabular-nums">{row.ticket}</td>
                    <td className="px-3 py-2 tabular-nums">{row.entry.toFixed(2)}</td>
                    <td className="px-3 py-2 tabular-nums">{row.sl.toFixed(2)}</td>
                    <td className="px-3 py-2 tabular-nums">{row.tp.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Bot health (per decision log)
        </h2>
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/60 text-left text-xs uppercase tracking-wide text-zinc-500">
                <th className="px-3 py-2 font-medium">Log</th>
                <th className="px-3 py-2 font-medium">Last event</th>
                <th className="px-3 py-2 font-medium">Last bar</th>
                <th className="px-3 py-2 font-medium">Fetch failures 24h</th>
                <th className="px-3 py-2 font-medium">Orders</th>
              </tr>
            </thead>
            <tbody>
              {health.map((row, i) => (
                <tr key={i} className="border-b border-zinc-800/60 last:border-0">
                  <td className="px-3 py-2 font-mono text-xs text-zinc-300">{row.source_log}</td>
                  <td className="px-3 py-2 tabular-nums">
                    <Badge value={row.last_event ?? "none"} />
                    <span className="ml-2 text-xs text-zinc-500">{row.last_event_ts}</span>
                  </td>
                  <td className="px-3 py-2 text-xs text-zinc-400">{row.last_bar_checked ?? "—"}</td>
                  <td className="px-3 py-2 tabular-nums">{row.bar_fetch_failed_24h}</td>
                  <td className="px-3 py-2 tabular-nums">{row.orders_placed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {open.length > 0 ? (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Open positions
          </h2>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/60 text-left text-xs uppercase tracking-wide text-zinc-500">
                  <th className="px-3 py-2 font-medium">Source</th>
                  <th className="px-3 py-2 font-medium">Entry</th>
                  <th className="px-3 py-2 font-medium">SL</th>
                  <th className="px-3 py-2 font-medium">TP</th>
                  <th className="px-3 py-2 font-medium">R so far</th>
                </tr>
              </thead>
              <tbody>
                {open.map((row, i) => (
                  <tr key={i} className="border-b border-zinc-800/60 last:border-0">
                    <td className="px-3 py-2">
                      <Badge value={row.source} tone={toneFor(String(row.source))} />
                    </td>
                    <td className="px-3 py-2 tabular-nums">{row.entry}</td>
                    <td className="px-3 py-2 tabular-nums">{row.sl}</td>
                    <td className="px-3 py-2 tabular-nums">{row.tp}</td>
                    <td className="px-3 py-2 tabular-nums">{row.r_multiple ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function WarehouseEmpty() {
  return (
    <div className="rounded-lg border border-amber-900 bg-amber-950/30 p-8 text-center">
      <h1 className="text-lg font-semibold text-amber-300">Warehouse not loaded</h1>
      <p className="mt-2 text-sm text-zinc-400">
        Run the analytics warehouse first, then reload this page:
      </p>
      <pre className="mx-auto mt-4 inline-block rounded bg-zinc-900 px-4 py-3 text-left font-mono text-xs text-zinc-300">
        {`python scripts/warehouse_cli.py load\ncd dbt && dbt run`}
      </pre>
    </div>
  );
}
