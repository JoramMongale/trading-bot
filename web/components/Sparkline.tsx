interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
}

/** Hand-rolled SVG polyline sparkline — no chart library (plan 03-05). */
export default function Sparkline({
  values,
  width = 260,
  height = 48,
  stroke = "#22d3ee",
}: SparklineProps) {
  if (values.length < 2) {
    return (
      <div className="text-xs text-zinc-600" style={{ height }}>
        not enough data
      </div>
    );
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - 4 - ((v - min) / span) * (height - 8)).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <polyline points={points} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}
