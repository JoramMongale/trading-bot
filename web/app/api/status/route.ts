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
    const health = await query(
      "SELECT source_log, last_event_ts, last_event, last_bar_checked, " +
        "bar_fetch_failed_24h, bar_fetch_failed_total, orders_placed " +
        "FROM mart_bot_health ORDER BY source_log",
    );
    const open = await query(
      "SELECT source, entry_time, entry, sl, tp, exit_time, exit_price, " +
        "exit_reason, r_multiple, ticket " +
        "FROM mart_trade_ledger " +
        "WHERE exit_reason IS NULL OR exit_price IS NULL " +
        "ORDER BY entry_time DESC LIMIT 20",
    );
    // Live open positions: the mart only holds CLOSED trades (trades.csv +
    // closes.log), so a position placed by the live bot with no matching close
    // is invisible there. Read the latest order_placed per live log from
    // raw_decisions and flag it open when no trade_closed references its
    // ticket (DASH-01: "open position at a glance").
    const orders = await query<{
      source_log: string;
      ts: string;
      ticket: string;
      entry: string;
      sl: string;
      tp: string;
    }>(
      "SELECT source_log, ts, " +
        "json_extract_string(fields, '$.ticket') AS ticket, " +
        "json_extract_string(fields, '$.entry') AS entry, " +
        "json_extract_string(fields, '$.sl') AS sl, " +
        "json_extract_string(fields, '$.tp') AS tp " +
        "FROM raw_decisions WHERE event = 'order_placed' " +
        "ORDER BY ts DESC",
    );
    const closed = await query<{ ticket: string }>(
      "SELECT DISTINCT json_extract_string(fields, '$.ticket') AS ticket " +
        "FROM raw_closes",
    );
    const closedTickets = new Set(closed.map((r) => String(r.ticket)));
    const seenLogs = new Set<string>();
    const liveOpen: Array<{
      source_log: string;
      ticket: string;
      entry: number;
      sl: number;
      tp: number;
      open: boolean;
    }> = [];
    for (const o of orders) {
      if (!o.ticket || seenLogs.has(o.source_log)) continue;
      seenLogs.add(o.source_log);
      liveOpen.push({
        source_log: o.source_log,
        ticket: String(o.ticket),
        entry: Number(o.entry),
        sl: Number(o.sl),
        tp: Number(o.tp),
        open: !closedTickets.has(String(o.ticket)),
      });
    }
    const latest = await query(
      "SELECT max(entry_time) AS latest_entry FROM mart_trade_ledger",
    );
    return Response.json({
      health,
      open,
      liveOpen,
      latest: latest[0]?.latest_entry ?? null,
    });
  } catch (err) {
    return Response.json(
      { error: "warehouse not loaded", detail: String(err) },
      { status: 503 },
    );
  }
}
