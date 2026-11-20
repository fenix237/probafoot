"use client";
import { useEffect, useState } from "react";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Probs = [number, number, number];
export type MatchItem = {
  id: number; league: string; season: string; kickoff: string; home: string; away: string;
  hg: number; ag: number; result: "H" | "D" | "A";
  probs: Partial<Record<"market" | "elo" | "dc" | "dc_ctx", Probs>>;
  odds_b365_pre: Probs | null; ev_dc: Probs | null; as_of: string;
};
export type MatchList = { run_id: string; total: number; items: MatchItem[] };
export type League = { league: string; matches: number; first_season: string; last_season: string; last_kickoff: string };
export type Performance = {
  run_id: string; league: string; seasons: string[]; n: number;
  models: Record<string, { n: number; log_loss: number; rps: number; brier: number; ece: number }>;
  paired: Record<string, { mean: number; lo: number; hi: number; verdict: string }>;
  calibration: { lo: number; hi: number; n: number; p_mean: number; freq: number }[];
  cumulative: { n: number; date: string; market: number; dc: number }[];
  bets: { n: number; roi: number; roi_lo: number; roi_hi: number; clv: number; bankroll_end: number; max_drawdown: number } | null;
};
export type Detail = MatchItem & {
  odds: Record<string, Record<string, Probs>>; close_fair_probs: Probs | null; run_id: string;
  events: { event_type: string; occurred_at: string; known_at: string; source: string; payload: Record<string, unknown> }[];
};
export type Prediction = {
  league: string; home: string; away: string; model: string; trained_until: string;
  expected_goals: { home: number; away: number }; rho: number;
  markets: Record<string, { p: number; fair_odds: number | null }>;
  top_scores: { score: string; p: number }[]; notice: string;
};

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setLoading(true); setError(null);
    fetch(`${API}${path}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `Erreur ${r.status}`);
        return r.json();
      })
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && (setData(null), setError(e.message === "Failed to fetch" ? "API injoignable. Lancez : uvicorn probafoot.api:app --port 8000" : e.message)))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [path]);
  return { data, error, loading };
}

export const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)} %`;
export const fmt = (x: number, d = 3) => x.toFixed(d);
