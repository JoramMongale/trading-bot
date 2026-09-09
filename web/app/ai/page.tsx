import Badge, { toneFor } from "@/components/Badge";
import DataTable from "@/components/DataTable";
import RefreshButton from "@/components/RefreshButton";
import Sparkline from "@/components/Sparkline";
import WarehouseEmpty from "@/components/WarehouseEmpty";
import { isWarehouseReady, query } from "@/lib/duckdb";

export const dynamic = "force-dynamic";

interface ActivityRow {
  day: string;
  consultations: number;
  approved: number;
  blocked: number;
  rejected: number;
  unavailable: number;
  approval_rate: number | null;
}

interface PerformanceRow {
  day: string;
  all_trades: number;
  avg_r_all: number | null;
  win_rate_all: number | null;
  ai_consulted_trades: number;
  avg_r_ai: number | null;
}

export default async function AiPage() {
  if (!(await isWarehouseReady())) return <WarehouseEmpty />;

  const [activity, performance] = await Promise.all([
    query<ActivityRow>(
      "SELECT day, consultations, approved, blocked, rejected, unavailable, " +
        "approval_rate FROM mart_ai_gate_activity ORDER BY day DESC",
    ),
    query<PerformanceRow>(
      "SELECT day, all_trades, avg_r_all, win_rate_all, ai_consulted_trades, " +
        "avg_r_ai FROM mart_ai_gate_performance ORDER BY day DESC",
    ),
  ]);

  const approvalHistory = [...activity]
    .reverse()
    .slice(-14)
    .map((r) => (r.approval_rate == null ? 0 : Number(r.approval_rate)));

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">AI Gate</h1>
          <p className="text-sm text-zinc-500">
            Monitoring the model for unexpected behavior — every consultation, veto, and verdict.
          </p>
        </div>
        <RefreshButton />
      </div>

      {approvalHistory.length >= 2 ? (
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Approval rate — last {Math.min(activity.length, 14)} days
          </h2>
          <Sparkline values={approvalHistory} />
        </section>
      ) : null}

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Daily gate activity
        </h2>
        <DataTable
          rows={activity}
          empty="No AI activity in the warehouse yet."
          columns={[
            { key: "day", header: "Day", render: (r) => String(r.day).slice(0, 10) },
            { key: "consultations", header: "Consulted" },
            { key: "approved", header: "Approved" },
            { key: "blocked", header: "Blocked" },
            { key: "rejected", header: "Rejected" },
            { key: "unavailable", header: "Unavailable" },
            {
              key: "approval_rate",
              header: "Approval rate",
              render: (r) => (
                <Badge value={`${(Number(r.approval_rate ?? 0) * 100).toFixed(0)}%`} tone={toneFor(String(r.approval_rate))} />
              ),
            },
          ]}
        />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Gated vs raw performance
        </h2>
        <DataTable
          rows={performance}
          empty="No performance rows yet."
          columns={[
            { key: "day", header: "Day", render: (r) => String(r.day).slice(0, 10) },
            { key: "all_trades", header: "All trades" },
            {
              key: "avg_r_all",
              header: "Avg R (all)",
              render: (r) => (r.avg_r_all == null ? "—" : Number(r.avg_r_all).toFixed(3)),
            },
            { key: "ai_consulted_trades", header: "AI-consulted trades" },
            {
              key: "avg_r_ai",
              header: "Avg R (AI)",
              render: (r) => (r.avg_r_ai == null ? "—" : Number(r.avg_r_ai).toFixed(3)),
            },
          ]}
        />
      </section>
    </div>
  );
}
