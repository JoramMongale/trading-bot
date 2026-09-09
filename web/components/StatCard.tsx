interface StatCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  tone?: "default" | "positive" | "negative" | "warn";
}

const TONES: Record<string, string> = {
  default: "border-zinc-800 bg-zinc-900/60",
  positive: "border-emerald-900 bg-emerald-950/40",
  negative: "border-red-900 bg-red-950/40",
  warn: "border-amber-900 bg-amber-950/40",
};

const VALUE_TONES: Record<string, string> = {
  default: "text-zinc-100",
  positive: "text-emerald-400",
  negative: "text-red-400",
  warn: "text-amber-400",
};

export default function StatCard({ label, value, subtext, tone = "default" }: StatCardProps) {
  return (
    <div className={`rounded-lg border p-4 ${TONES[tone]}`}>
      <div className="text-xs uppercase tracking-wide text-zinc-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${VALUE_TONES[tone]}`}>{value}</div>
      {subtext ? <div className="mt-1 text-xs text-zinc-500">{subtext}</div> : null}
    </div>
  );
}
