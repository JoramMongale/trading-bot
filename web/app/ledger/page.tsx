import Badge, { toneFor } from "@/components/Badge";
import DataTable from "@/components/DataTable";
import RefreshButton from "@/components/RefreshButton";
import StatCard from "@/components/StatCard";
import WarehouseEmpty from "@/components/WarehouseEmpty";
import { isWarehouseReady, query } from "@/lib/duckdb";

export const dynamic = "force-dynamic";

interface LedgerRow {
  source: string;
  entry_time: string | null;
  entry: number | null;
  sl: number | null;
  tp: number | null;
  exit_time: string | null;
  exit_price: number | null;
  exit_reason: string | null;
  r_multiple: number | null;
  ticket: string | null;
}

interface AggRow {
  total_trades: number;
  net_r: number;
  avg_r: number;
  wins: number;
}

export default async function LedgerPage() {
  if (!(await isWarehouseReady())) return <WarehouseEmpty />;

  const [rows, aggRows] = await Promise.all([
    query<LedgerRow>(
      "SELECT source, entry_time, entry, sl, tp, exit_time, exit_price, " +
        "exit_reason, r_multiple, ticket FROM mart_trade_ledger " +
        "ORDER BY entry_time DESC NULLS LAST LIMIT 200",
    ),
    query<AggRow>(
      "SELECT COUNT(*) AS total_trades, COALESCE(SUM(r_multiple),0) AS net_r, " +
        "COALESCE(AVG(r_multiple),0) AS avg_r, " +
        "SUM(CASE WHEN r_multiple > 0 THEN 1 ELSE 0 END) AS wins " +
        "FROM mart_trade_ledger WHERE r_multiple IS NOT NULL",
    ),
  ]);

  const agg = aggRows[0] ?? ({} as AggRow);
  const total = Number(agg.total_trades) || 0;
  const aggregates = {
    total_trades: total,
    win_rate: total > 0 ? Number(agg.wins) / total : 0,
    net_r: Number(agg.net_r) || 0,
    avg_r: Number(agg.avg_r) || 0,
  };

  const fmt = (v: unknown, d = 2) => (v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(d));

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Trade Ledger</h1>
          <p className="text-sm text-zinc-500">Backtest + live trades, merged from the warehouse.</p>
        </div>
        <RefreshButton />
      </div>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total trades" value={aggregates.total_trades} />
        <StatCard
          label="Win rate"
          value={`${(aggregates.win_rate * 100).toFixed(1)}%`}
          tone={aggregates.win_rate >= 0.5 ? "positive" : "negative"}
        />
        <StatCard label="Net R" value={fmt(aggregates.net_r)} tone={aggregates.net_r >= 0 ? "positive" : "negative"} />
        <StatCard label="Avg R" value={fmt(aggregates.avg_r)} tone={aggregates.avg_r >= 0 ? "positive" : "negative"} />
      </section>

      <DataTable
        rows={rows}
        empty="No trades in the ledger yet — run the backtest or watch_closes."
        columns={[
          {
            key: "source",
            header: "Source",
            render: (r) => <Badge value={String(r.source)} tone={toneFor(String(r.source))} />,
          },
          { key: "entry_time", header: "Entry time", render: (r) => String(r.entry_time ?? "").slice(0, 16) },
          { key: "entry", header: "Entry", render: (r) => fmt(r.entry) },
          { key: "sl", header: "SL", render: (r) => fmt(r.sl) },
          { key: "tp", header: "TP", render: (r) => fmt(r.tp) },
          { key: "exit_price", header: "Exit", render: (r) => fmt(r.exit_price) },
          {
            key: "exit_reason",
            header: "Exit",
            render: (r) => <Badge value={r.exit_reason ?? null} />,
          },
          { key: "r_multiple", header: "R", render: (r) => fmt(r.r_multiple) },
          { key: "ticket", header: "Ticket", render: (r) => (r.ticket ? String(r.ticket) : "—") },
        ]}
      />
    </div>
  );
}
