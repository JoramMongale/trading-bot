import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

const CONFIGS = ["config/config-cent.toml", "config/config-btc.toml"];

type Scalar = string | number | boolean;
type TomlTable = Record<string, Scalar>;

/**
 * Minimal TOML section parser for the [risk]/[live] tables only. Hand-rolled
 * (stdlib fs, no dependency) and strictly read-only: scalar values only, so
 * the risk page can render them without ever writing back (DASH-02). Editing
 * stays in scripts/tune_risk.py's warned CLI.
 */
function parseRiskToml(text: string): Record<string, TomlTable> {
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
    const key = kv[1];
    const raw = kv[2].trim();
    let value: Scalar = raw;
    if (raw.startsWith('"')) value = raw.replace(/^"|"$/g, "");
    else if (raw === "true" || raw === "false") value = raw === "true";
    else if (/^-?\d+(\.\d+)?$/.test(raw)) value = Number(raw);
    out[section][key] = value;
  }
  return out;
}

export async function GET() {
  const configs: Record<string, { file: string; risk?: TomlTable; live?: TomlTable }> = {};
  for (const rel of CONFIGS) {
    const file = path.join(/* turbopackIgnore: true */ process.cwd(), "..", rel);
    const entry: { file: string; risk?: TomlTable; live?: TomlTable } = { file: rel };
    try {
      const parsed = parseRiskToml(fs.readFileSync(/* turbopackIgnore: true */ file, "utf-8"));
      entry.risk = parsed["risk"];
      entry.live = parsed["live"];
    } catch {
      entry.risk = { error: "unreadable" };
    }
    configs[rel] = entry;
  }
  return Response.json({ configs });
}
