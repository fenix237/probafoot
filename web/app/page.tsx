"use client";
import Link from "next/link";
import { useState } from "react";
import ProbBar from "@/components/ProbBar";
import { League, MatchList, pct, useApi } from "@/lib/api";

const PAGE = 25;

export default function Home() {
  const lg = useApi<{ items: League[] }>("/v1/leagues");
  const [league, setLeague] = useState("E0");
  const [season, setSeason] = useState("");
  const [minEv, setMinEv] = useState(0);
  const [offset, setOffset] = useState(0);
  const q = `/v1/matches?league=${league}&limit=${PAGE}&offset=${offset}${season ? `&season=${season}` : ""}`;
  const { data, error, loading } = useApi<MatchList>(q);
  const items = (data?.items ?? []).filter((m) => minEv <= 0 || (m.ev_dc && Math.max(...m.ev_dc) >= minEv / 100));

  return (
    <>
      <h1>Matchs évalués</h1>
      <p className="muted">
        Probabilités calculées <b>avant</b> chaque match (rejeu « à la date ») par trois modèles, comparées aux cotes de clôture.
        Barre : domicile · nul · extérieur.
      </p>
      <div className="row">
        <label>Ligue{" "}
          <select value={league} onChange={(e) => { setLeague(e.target.value); setOffset(0); }}>
            {(lg.data?.items ?? [{ league: "E0" } as League]).map((l) => <option key={l.league}>{l.league}</option>)}
          </select>
        </label>
        <label>Saison{" "}
          <select value={season} onChange={(e) => { setSeason(e.target.value); setOffset(0); }}>
            <option value="">Toutes</option>
            {["2223", "2324", "2425"].map((s) => <option key={s} value={s}>{s.slice(0, 2)}/{s.slice(2)}</option>)}
          </select>
        </label>
        <label>EV min (%){" "}
          <input type="number" min={0} step={1} value={minEv} onChange={(e) => setMinEv(Number(e.target.value))} style={{ width: 70 }} />
        </label>
        {data && <span className="muted">Run {data.run_id} · {data.total} matchs</span>}
      </div>

      {error && <p className="err">{error}</p>}
      {loading && <p className="muted">Chargement…</p>}
      <div className="card scroll">
        <table>
          <thead>
            <tr><th>Date</th><th>Match</th><th>Score</th><th>Marché (clôture)</th><th>Modèle DC</th><th className="num">Meilleur EV</th></tr>
          </thead>
          <tbody>
            {items.map((m) => {
              const best = m.ev_dc ? Math.max(...m.ev_dc) : null;
              return (
                <tr key={m.id}>
                  <td>{m.kickoff.slice(0, 10)}</td>
                  <td><Link href={`/matches/${m.id}`}>{m.home} – {m.away}</Link></td>
                  <td>{m.hg}–{m.ag}</td>
                  <td><ProbBar p={m.probs.market} /></td>
                  <td><ProbBar p={m.probs.dc} /></td>
                  <td className={`num ${best !== null && best >= 0.03 ? "pos" : ""}`}>{best !== null ? pct(best) : "n/d"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="row">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Précédent</button>
        <button disabled={!data || offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Suivant</button>
      </div>
      <p className="muted">EV = valeur espérée du meilleur choix selon le modèle contre les cotes Bet365 avant match. Une EV positive n'est pas une garantie : elle ne se confirme qu'après des milliers de paris.</p>
    </>
  );
}
