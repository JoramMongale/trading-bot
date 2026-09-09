type Tone = "green" | "red" | "amber" | "zinc";

const TONES: Record<Tone, string> = {
  green: "bg-emerald-950 text-emerald-400 border-emerald-800",
  red: "bg-red-950 text-red-400 border-red-800",
  amber: "bg-amber-950 text-amber-400 border-amber-800",
  zinc: "bg-zinc-800 text-zinc-400 border-zinc-700",
};

/** Pick a tone from common verdict/reason strings. */
export function toneFor(value: string | null | undefined): Tone {
  const v = (value ?? "").toLowerCase();
  if (["approved", "tp", "positive", "win", "pass", "true", "complete"].some((s) => v.includes(s))) {
    return "green";
  }
  if (["rejected", "blocked", "sl", "negative", "fail", "false", "unavailable", "failed"].some((s) => v.includes(s))) {
    return "red";
  }
  if (["pending", "degraded", "warn", "partial"].some((s) => v.includes(s))) {
    return "amber";
  }
  return "zinc";
}

export default function Badge({ value, tone }: { value: string | number | null | undefined; tone?: Tone }) {
  const t = tone ?? toneFor(String(value ?? ""));
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium border ${TONES[t]}`}>
      {value ?? "—"}
    </span>
  );
}
