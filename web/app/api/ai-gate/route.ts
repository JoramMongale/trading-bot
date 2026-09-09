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
    const rows = await query(
      "SELECT day, consultations, approved, blocked, rejected, unavailable, " +
        "approval_rate FROM mart_ai_gate_activity ORDER BY day DESC",
    );
    const performance = await query(
      "SELECT day, all_trades, avg_r_all, win_rate_all, ai_consulted_trades, " +
        "avg_r_ai FROM mart_ai_gate_performance ORDER BY day DESC",
    );
    return Response.json({ rows, performance });
  } catch (err) {
    return Response.json(
      { error: "warehouse not loaded", detail: String(err) },
      { status: 503 },
    );
  }
}
