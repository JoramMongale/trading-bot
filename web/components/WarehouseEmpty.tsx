export default function WarehouseEmpty() {
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
