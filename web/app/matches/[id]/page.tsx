"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import ProbBar from "@/components/ProbBar";
import { Detail, pct, useApi } from "@/lib/api";

const NAMES: Record<string, string> = { market: "Marché (clôture sans marge)", elo: "Elo", dc: "Dixon-Coles", dc_ctx: "Dixon-Coles + repos" };

export default function MatchPage() {
  const { id } = useParams<{ id: string }>();
  const { data: d, error, loading } = useApi<Detail>(`/v1/matches/${id}`);
  if (error) return <p className="err">{error}</p>;
  if (loading || !d) return <p className="muted">Chargement…</p>;
  const outcomeLabel = { H: d.home, D: "Nul", A: d.away }[d.result];
  return (
    <>
      <p><Link href="/">← Matchs</Link></p>
      <h1>{d.home} – {d.away}</h1>
      <p className="muted">{d.kickoff.replace("T", " ")} · {d.league} · saison {d.season} · run {d.run_id}</p>
      <div className="grid">
        <div className="card stat"><b>{d.hg}–{d.ag}</b><span>Score final · {outcomeLabel}</span></div>
        <div className="card stat"><b>{d.as_of?.replace("T", " ")}</b><span>Prédiction émise à cet instant (as_of)</span></div>
      </div>

      <h2>Probabilités par modèle</h2>
      <div className="card scroll">
        <table>
          <thead><tr><th>Modèle</th><th>Distribution</th><th className="num">1</th><th className="num">X</th><th className="num">2</th></tr></thead>
          <tbody>
            {Object.entries(d.probs).map(([k, p]) => (
              <tr key={k}>
                <td>{NAMES[k] ?? k}</td><td><ProbBar p={p as [number, number, number]} /></td>
                {(p as number[]).map((v, i) => <td key={i} className="num">{pct(v)}</td>)}
              </tr>
            ))}
            {d.close_fair_probs && (
              <tr><td>Cotes de clôture (juste prix)</td><td><ProbBar p={d.close_fair_probs} /></td>
                {d.close_fair_probs.map((v, i) => <td key={i} className="num">{pct(v)}</td>)}</tr>
            )}
          </tbody>
        </table>
      </div>

      <h2>Cotes enregistrées</h2>
      <div className="card scroll">
        <table>
          <thead><tr><th>Moment</th><th>Bookmaker</th><th className="num">1</th><th className="num">X</th><th className="num">2</th></tr></thead>
          <tbody>
            {Object.entries(d.odds).flatMap(([kind, books]) =>
              Object.entries(books).map(([bk, o]) => (
                <tr key={kind + bk}><td>{kind === "pre" ? "Avant match" : "Clôture"}</td><td>{bk}</td>
                  {o.map((v, i) => <td key={i} className="num">{v.toFixed(2)}</td>)}</tr>
              )))}
          </tbody>
        </table>
      </div>

      <h2>Chronologie des événements</h2>
      <div className="card scroll">
        <table>
          <thead><tr><th>Type</th><th>Survenu (occurred_at)</th><th>Connu (known_at)</th><th>Source</th><th>Contenu</th></tr></thead>
          <tbody>
            {d.events.map((e, i) => (
              <tr key={i}><td><span className="badge">{e.event_type}</span></td><td>{e.occurred_at.replace("T", " ")}</td>
                <td>{e.known_at.replace("T", " ")}</td><td>{e.source}</td><td><code>{JSON.stringify(e.payload)}</code></td></tr>
            ))}
          </tbody>
        </table>
        <p className="muted">Seul known_at décide de ce qu'un modèle a le droit de voir : c'est la garantie anti-fuite de données.</p>
      </div>
    </>
  );
}
