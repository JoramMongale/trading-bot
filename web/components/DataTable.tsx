import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  rows: T[];
  columns: Column<T>[];
  empty?: string;
}

export default function DataTable<T>({ rows, columns, empty = "No rows" }: DataTableProps<T>) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-6 text-center text-sm text-zinc-500">
        {empty}
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 bg-zinc-900/60 text-left text-xs uppercase tracking-wide text-zinc-500">
            {columns.map((c) => (
              <th key={c.key} className="px-3 py-2 font-medium">
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-zinc-800/60 last:border-0">
              {columns.map((c) => (
                <td key={c.key} className="px-3 py-2 tabular-nums text-zinc-300">
                  {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
