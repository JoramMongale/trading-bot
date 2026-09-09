import { isWarehouseReady, query } from "@/lib/duckdb";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    if (!(await isWarehouseReady())) {
      return Response.json(
        { error: "warehouse not loaded", detail: "run the 03-03 loader + dbt first" },
        { status: 503 },
      );
    }
    const raw = new URL(request.url).searchParams.get("limit");
    const limit = Math.min(1000, Math.max(1, Number(raw) || 200));

    const rows = await query(
      "SELECT source, entry_time, entry, sl, tp, exit_time, exit_price, " +
        "exit_reason, r_multiple, ticket " +
        "FROM mart_trade_ledger " +
        "ORDER BY entry_time DESC NULLS LAST LIMIT $1",
      [limit],
    );
    const agg = await query(
      "SELECT COUNT(*) AS total_trades, " +
        "COALESCE(SUM(r_multiple), 0) AS net_r, " +
        "COALESCE(AVG(r_multiple), 0) AS avg_r, " +
        "SUM(CASE WHEN r_multiple > 0 THEN 1 ELSE 0 END) AS wins " +
        "FROM mart_trade_ledger WHERE r_multiple IS NOT NULL",
    );
    const a = agg[0] ?? {};
    const total = Number(a.total_trades) || 0;
    return Response.json({
      rows,
      aggregates: {
        total_trades: total,
        win_rate: total > 0 ? Number(a.wins) / total : 0,
        net_r: Number(a.net_r) || 0,
        avg_r: Number(a.avg_r) || 0,
      },
    });
  } catch (err) {
    return Response.json(
      { error: "warehouse not loaded", detail: String(err) },
      { status: 503 },
    );
  }
}
