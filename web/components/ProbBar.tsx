import { Probs, pct } from "@/lib/api";

export default function ProbBar({ p }: { p?: Probs }) {
  if (!p) return <span className="muted">n/d</span>;
  return (
    <div title={`1 ${pct(p[0])} · X ${pct(p[1])} · 2 ${pct(p[2])}`}>
      <div className="bar" role="img" aria-label={`Domicile ${pct(p[0], 0)}, nul ${pct(p[1], 0)}, extérieur ${pct(p[2], 0)}`}>
        <i className="h" style={{ width: `${p[0] * 100}%` }} />
        <i className="d" style={{ width: `${p[1] * 100}%` }} />
        <i className="a" style={{ width: `${p[2] * 100}%` }} />
      </div>
      <span className="muted">{(p[0] * 100).toFixed(0)} · {(p[1] * 100).toFixed(0)} · {(p[2] * 100).toFixed(0)}</span>
    </div>
  );
}
