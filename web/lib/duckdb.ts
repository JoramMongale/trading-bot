import { DuckDBInstance } from "@duckdb/node-api";
import fs from "node:fs";
import path from "node:path";

/**
 * The ONLY DuckDB access point in the dashboard (DASH-01/DASH-02).
 *
 * - Read-only: the instance is created with `access_mode = 'read_only'`, so
 *   the web app structurally cannot write the warehouse.
 * - Lazy singleton: one cached instance per process (the Neo client forbids
 *   attaching the same database twice in one process).
 * - Always parameterized: no user input ever reaches SQL text (T-04-05-03).
 * - Values are normalized so JSON serialization never trips on DuckDB's
 *   BigInt / {micros} timestamp representation.
 */

const DEFAULT_DB = path.join(process.cwd(), "..", "data", "analytics", "trading.duckdb");
const dbPath = process.env.DUCKDB_PATH ?? DEFAULT_DB;

const CORE_MARTS = [
  "mart_bot_health",
  "mart_trade_ledger",
  "mart_ai_gate_activity",
  "mart_ai_gate_performance",
];

let _instance: Promise<DuckDBInstance> | null = null;

function getInstance(): Promise<DuckDBInstance> {
  if (!_instance) {
    _instance = DuckDBInstance.create(dbPath, { access_mode: "read_only" });
  }
  return _instance;
}

/** Normalize a DuckDB value to a JSON-serializable one. */
export function normalizeValue(v: unknown): unknown {
  if (typeof v === "bigint") {
    const n = Number(v);
    return Number.isSafeInteger(n) ? n : v.toString();
  }
  if (Array.isArray(v)) return v.map(normalizeValue);
  if (v && typeof v === "object") {
    // DuckDB represents TIMESTAMP as { micros: bigint } and DATE as { days }.
    if ("micros" in v) {
      const micros = (v as { micros: unknown }).micros;
      const num = typeof micros === "bigint" ? Number(micros) : Number(micros);
      return new Date(num / 1000).toISOString();
    }
    if ("days" in v) {
      const days = Number((v as { days: unknown }).days);
      if (Number.isFinite(days)) {
        return new Date(Date.UTC(1970, 0, 1 + days)).toISOString().slice(0, 10);
      }
    }
    // DuckDB represents LIST columns as { items: [...] }.
    if ("items" in v && Array.isArray((v as { items: unknown }).items)) {
      return ((v as { items: unknown[] }).items).map(normalizeValue);
    }
    const out: Record<string, unknown> = {};
    for (const [k, val] of Object.entries(v)) out[k] = normalizeValue(val);
    return out;
  }
  return v;
}

export async function query<T = Record<string, unknown>>(
  sql: string,
  params: unknown[] = [],
): Promise<T[]> {
  const instance = await getInstance();
  const connection = await instance.connect();
  try {
    const reader = await connection.runAndReadAll(sql, params as never);
    const rows = reader.getRowObjects();
    return rows.map((r) => normalizeValue(r) as T);
  } finally {
    connection.closeSync();
  }
}

/** True when the warehouse file exists AND the 03-03 core marts are present. */
export async function isWarehouseReady(): Promise<boolean> {
  try {
    if (!fs.existsSync(/* turbopackIgnore: true */ dbPath)) return false;
    const tables = await query<{ table_name: string }>(
      "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'",
    );
    const present = new Set(tables.map((t) => t.table_name));
    return CORE_MARTS.every((m) => present.has(m));
  } catch {
    return false;
  }
}

export { dbPath };
