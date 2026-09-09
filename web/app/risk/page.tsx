import RefreshButton from "@/components/RefreshButton";
import StatCard from "@/components/StatCard";
import { query } from "@/lib/duckdb";
import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

type Scalar = string | number | boolean;
type TomlTable = Record<string, Scalar>;

const CONFIGS = ["config/config-cent.toml", "config/config-btc.toml"];

function parseToml(text: string): Record<string, TomlTable> {
  const out: Record<string, TomlTable> = {};
  let section = "";
  for (const rawLine of text.split("\n")) {
    const line = rawLine.split("#")[0].trim();
    if (!line) continue;
    const header = line.match(/^\[([a-z_.]+)\]$/);
    if (header) {
      section = header[1];
      out[section] = out[section] ?? {};
      continue;
    }
    const kv = line.match(/^([a-z_][a-z0-9_.]*)\s*=\s*(.+)$/);
    if (!kv || !section) continue;
    const raw = kv[2].trim();
    let value: Scalar = raw;
    if (raw.startsWith('"')) value = raw.replace(/^"|"$/g, "");
    else if (raw === "true" || raw === "false") value = raw === "true";
    else if (/^-?\d+(\.\d+)?$/.test(raw)) value = Number(raw);
    out[section][kv[1]] = value;
  }
  return out;
}

const RISK_ORDER = [
  "max_loss_pct_per_trade",
  "sizing",
  "max_daily_loss_pct",
  "lot_min",
  "lot_step",
  "max_leverage",
  "max_concurrent",
  "min_rr",
];

export default async function RiskPage() {
  const configs: Record<string, { risk?: TomlTable; live?: TomlTable; file: string }> = {};
  for (const rel of CONFIGS) {
    const file = path.join(/* turbopackIgnore: true */ process.cwd(), "..", rel);
    const entry: { risk?: TomlTable; live?: TomlTable; file: string } = { file: rel };
    try {
      const parsed = parseToml(fs.readFileSync(/* turbopackIgnore: true */ file, "utf-8"));
      entry.risk = parsed["risk"];
      entry.live = parsed["live"];
    } catch {
      entry.risk = { error: "unreadable" };
    }
    configs[rel] = entry;
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Risk</h1>
          <p className="text-sm text-zinc-500">
            Read-only view of the [risk] tables. Editing stays in the warned CLI:{" "}
            <code className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs">scripts/tune_risk.py</code>
          </p>
        </div>
        <RefreshButton />
      </div>

      {Object.entries(configs).map(([rel, cfg]) => (
        <section key={rel} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <h2 className="mb-3 font-mono text-sm font-semibold text-zinc-300">{rel}</h2>
          {cfg.risk ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {RISK_ORDER.filter((k) => k in cfg.risk!).map((k) => (
                <StatCard key={k} label={k} value={String(cfg.risk![k])} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-zinc-500">unreadable / no [risk] table</p>
          )}
          {cfg.live ? (
            <p className="mt-3 text-xs text-zinc-500">
              live: mode={String(cfg.live.mode ?? "—")} magic={String(cfg.live.magic_number ?? "—")} enabled=
              {String(cfg.live.enabled ?? "—")}
            </p>
          ) : null}
        </section>
      ))}
    </div>
  );
}
