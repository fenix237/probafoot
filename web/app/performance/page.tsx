"use client";
import { useState } from "react";
import { League, Performance, fmt, pct, useApi } from "@/lib/api";

const NAMES: Record<string, string> = { market: "Marché (à battre)", elo: "Elo", dc: "Dixon-Coles", dc_ctx: "DC + repos" };

function CalibrationChart({ rows }: { rows: Performance["calibration"] }) {
  const S = 300, P = 34;
  const x = (v: number) => P + v * (S - P - 8), y = (v: number) => S - P - v * (S - P - 8);
  return (
    <svg viewBox={`0 0 ${S} ${S}`} style={{ width: "100%", maxWidth: 360 }} role="img"
      aria-label="Courbe de calibration : fréquence observée selon la probabilité annoncée">
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--line)" strokeDasharray="4 4" />
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(0)} stroke="var(--muted)" />
      <line x1={x(0)} y1={y(0)} x2={x(0)} y2={y(1)} stroke="var(--muted)" />
      {[0, 0.5, 1].map((t) => (
        <g key={t}>
          <text x={x(t)} y={S - P + 14} fontSize="10" textAnchor="middle" fill="var(--muted)">{t * 100}%</text>
          <text x={P - 5} y={y(t) + 3} fontSize="10" textAnchor="end" fill="var(--muted)">{t * 100}%</text>
        </g>
      ))}
      <polyline fill="none" stroke="var(--accent)" strokeWidth="2" points={rows.map((r) => `${x(r.p_mean)},${y(r.freq)}`).join(" ")} />
      {rows.map((r, i) => (
        <circle key={i} cx={x(r.p_mean)} cy={y(r.freq)} r={Math.min(7, 2 + Math.sqrt(r.n) / 8)} fill="var(--accent)">
          <title>{`Annoncé ${pct(r.p_mean)} · observé ${pct(r.freq)} · n=${r.n}`}</title>
        </circle>
      ))}
      <text x={S / 2} y={S - 4} fontSize="10" textAnchor="middle" fill="var(--muted)">Probabilité annoncée</text>
      <text x="10" y={S / 2} fontSize="10" textAnchor="middle" fill="var(--muted)" transform={`rotate(-90 10 ${S / 2})`}>Fréquence observée</text>
    </svg>
  );
}

function CumulativeChart({ rows }: { rows: Performance["cumulative"] }) {
  if (rows.length < 2) return null;
  const W = 520, H = 220, P = 40;
  const all = rows.flatMap((r) => [r.market, r.dc]);
  const lo = Math.min(...all) - 0.01, hi = Math.max(...all) + 0.01;
  const x = (i: number) => P + (i / (rows.length - 1)) * (W - P - 10);
  const y = (v: number) => H - 28 - ((v - lo) / (hi - lo)) * (H - 28 - 10);
  const line = (k: "market" | "dc") => rows.map((r, i) => `${x(i)},${y(r[k])}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%" }} role="img" aria-label="Log-loss cumulée moyenne : marché contre modèle">
      {[lo, (lo + hi) / 2, hi].map((t, i) => (
        <g key={i}><line x1={P} x2={W - 10} y1={y(t)} y2={y(t)} stroke="var(--line)" />
          <text x={P - 4} y={y(t) + 3} fontSize="10" textAnchor="end" fill="var(--muted)">{t.toFixed(3)}</text></g>
      ))}
      <polyline fill="none" stroke="var(--navy)" strokeWidth="2" points={line("market")} />
      <polyline fill="none" stroke="var(--accent)" strokeWidth="2" points={line("dc")} />
      <text x={P} y={H - 8} fontSize="10" fill="var(--muted)">{rows[0].date}</text>
      <text x={W - 10} y={H - 8} fontSize="10" textAnchor="end" fill="var(--muted)">{rows[rows.length - 1].date}</text>
      <text x={W - 14} y={14} fontSize="11" textAnchor="end" fill="var(--navy)">— Marché</text>
      <text x={W - 14} y={28} fontSize="11" textAnchor="end" fill="var(--accent)">— Dixon-Coles</text>
    </svg>
  );
}

export default function PerformancePage() {
  const lg = useApi<{ items: League[] }>("/v1/leagues");
  const [league, setLeague] = useState("E0");
  const { data: p, error, loading } = useApi<Performance>(`/v1/performance?league=${league}`);
  return (
    <>
      <h1>Suivi de performance</h1>
      <div className="row">
        <label>Ligue{" "}
          <select value={league} onChange={(e) => setLeague(e.target.value)}>
            {(lg.data?.items ?? [{ league: "E0" } as League]).map((l) => <option key={l.league}>{l.league}</option>)}
          </select>
        </label>
        {p && <span className="muted">Run {p.run_id} · saisons {p.seasons.join(", ")} · {p.n} matchs</span>}
      </div>
      {error && <p className="err">{error}</p>}
      {loading && <p className="muted">Chargement…</p>}
      {p && (
        <>
          <h2>Qualité des probabilités (plus bas = mieux)</h2>
          <div className="card scroll">
            <table>
              <thead><tr><th>Modèle</th><th className="num">Log-loss</th><th className="num">RPS</th><th className="num">Brier</th><th className="num">ECE</th></tr></thead>
              <tbody>
                {Object.entries(p.models).map(([k, s]) => (
                  <tr key={k}><td>{NAMES[k] ?? k}</td><td className="num">{fmt(s.log_loss, 4)}</td><td className="num">{fmt(s.rps, 4)}</td>
                    <td className="num">{fmt(s.brier, 4)}</td><td className="num">{fmt(s.ece, 4)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <h2>Écart de log-loss face au marché (IC 95 %)</h2>
          <div className="card">
            {Object.entries(p.paired).map(([k, v]) => (
              <p key={k}>
                <b>{NAMES[k.replace("_vs_market", "")] ?? k}</b> : {v.mean >= 0 ? "+" : ""}{fmt(v.mean, 4)} [{fmt(v.lo, 4)} ; {fmt(v.hi, 4)}] →{" "}
                <span className={v.verdict === "meilleur" ? "verdict-bon" : v.verdict === "moins bon" ? "verdict-mauvais" : ""}>{v.verdict} que le marché</span>
              </p>
            ))}
            <p className="muted">Négatif = meilleur que les cotes de clôture. « Indistinguable » signifie que l'écart peut être dû au hasard.</p>
          </div>
          <div className="grid">
            <div className="card"><h2 style={{ marginTop: 0 }}>Calibration (Dixon-Coles)</h2><CalibrationChart rows={p.calibration} />
              <p className="muted">Les points proches de la diagonale indiquent des probabilités bien calibrées.</p></div>
            <div className="card" style={{ gridColumn: "span 2" }}><h2 style={{ marginTop: 0 }}>Log-loss cumulée moyenne</h2><CumulativeChart rows={p.cumulative} /></div>
          </div>
          <h2>Simulation de paris (seuil EV ≥ 3 %)</h2>
          {p.bets ? (
            <div className="grid">
              <div className="card stat"><b>{p.bets.n}</b><span>paris simulés</span></div>
              <div className="card stat"><b className={p.bets.roi < 0 ? "neg" : "pos"}>{pct(p.bets.roi)}</b><span>ROI mise plate [{pct(p.bets.roi_lo, 0)} ; {pct(p.bets.roi_hi, 0)}]</span></div>
              <div className="card stat"><b className={p.bets.clv < 0 ? "neg" : "pos"}>{pct(p.bets.clv, 2)}</b><span>CLV moyen</span></div>
              <div className="card stat"><b>{p.bets.bankroll_end.toFixed(1)}</b><span>bankroll finale (départ 100), drawdown {pct(p.bets.max_drawdown, 0)}</span></div>
            </div>
          ) : <p className="muted">Aucun signal émis.</p>}
          <p className="muted">Sous quelques milliers de paris, un ROI n'a aucune valeur probante : privilégiez log-loss, calibration et CLV.</p>
        </>
      )}
    </>
  );
}
