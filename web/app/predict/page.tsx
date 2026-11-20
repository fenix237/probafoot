"use client";
import { useState } from "react";
import { League, Prediction, pct, useApi } from "@/lib/api";

const LABELS: Record<string, string> = {
  "1": "Victoire domicile", X: "Match nul", "2": "Victoire extérieur", "over_2.5": "Plus de 2,5 buts", "under_2.5": "Moins de 2,5 buts",
  btts_yes: "Les deux équipes marquent : oui", btts_no: "Les deux équipes marquent : non",
};

export default function PredictPage() {
  const lg = useApi<{ items: League[] }>("/v1/leagues");
  const [league, setLeague] = useState("E0");
  const teams = useApi<{ items: string[] }>(`/v1/teams?league=${league}`);
  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [query, setQuery] = useState<string | null>(null);
  const pred = useApi<Prediction>(query);
  const list = teams.data?.items ?? [];

  return (
    <>
      <h1>Estimer un match</h1>
      <p className="muted">Modèle Dixon-Coles entraîné sur les 4 dernières années. Sans compositions ni blessures.</p>
      <div className="row">
        <select value={league} onChange={(e) => { setLeague(e.target.value); setHome(""); setAway(""); setQuery(null); }}>
          {(lg.data?.items ?? [{ league: "E0" } as League]).map((l) => <option key={l.league}>{l.league}</option>)}
        </select>
        <select value={home} onChange={(e) => setHome(e.target.value)}><option value="">Domicile…</option>{list.map((t) => <option key={t}>{t}</option>)}</select>
        <span>contre</span>
        <select value={away} onChange={(e) => setAway(e.target.value)}><option value="">Extérieur…</option>{list.map((t) => <option key={t}>{t}</option>)}</select>
        <button disabled={!home || !away || home === away}
          onClick={() => setQuery(`/v1/predict?league=${league}&home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`)}>Estimer</button>
      </div>
      {pred.error && <p className="err">{pred.error}</p>}
      {pred.loading && <p className="muted">Calcul…</p>}
      {pred.data && (
        <>
          <div className="grid">
            <div className="card stat"><b>{pred.data.expected_goals.home.toFixed(2)} – {pred.data.expected_goals.away.toFixed(2)}</b><span>buts attendus</span></div>
            <div className="card stat"><b>{pred.data.rho.toFixed(2)}</b><span>corrélation scores faibles (ρ)</span></div>
          </div>
          <h2>Marchés</h2>
          <div className="card scroll">
            <table>
              <thead><tr><th>Marché</th><th className="num">Probabilité</th><th className="num">Cote juste</th></tr></thead>
              <tbody>
                {Object.entries(pred.data.markets).map(([k, m]) => (
                  <tr key={k}><td>{LABELS[k] ?? k}</td><td className="num">{pct(m.p)}</td><td className="num">{m.fair_odds?.toFixed(2) ?? "–"}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="muted">Cote juste = 1 / probabilité. Une cote proposée au-dessus ne garantit rien : le modèle peut se tromper.</p>
          </div>
          <h2>Scores les plus probables</h2>
          <div className="card row">{pred.data.top_scores.map((s) => <span key={s.score} className="badge">{s.score} · {pct(s.p)}</span>)}</div>
          <p className="muted">{pred.data.notice}</p>
        </>
      )}
    </>
  );
}
