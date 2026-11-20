"""Backtest glissant « à la date » : aucun modèle ne voit un résultat dont known_at >= coup d'envoi."""
import heapq
import json
import uuid
from datetime import datetime

from . import features, market, metrics
from .anchor import Anchor
from .dixoncoles import DixonColes
from .elo import Elo

CLOSE_BOOKS = ["PS", "B365", "AVG"]   # cote de clôture de référence (ordre de préférence)
PRE_BOOKS = ["PS", "AVG", "B365"]     # prix avant match servant d'ancre (Pinnacle d'abord)
TAKEN_BOOK = "B365"                   # cote réellement « prenable » pour la simulation de paris


def _day(iso):
    return datetime.fromisoformat(iso).toordinal()


def load(conn, league):
    rows = conn.execute(
        "SELECT m.id, m.season, m.kickoff, m.home, m.away, m.hg, m.ag, e.known_at "
        "FROM matches m JOIN events e ON e.match_id = m.id AND e.event_type = 'MATCH_RESULT' "
        "WHERE m.league = ? ORDER BY m.kickoff", (league,)).fetchall()
    odds = {}
    for r in conn.execute("SELECT o.* FROM odds_snapshots o JOIN matches m ON m.id = o.match_id WHERE m.league = ?",
                          (league,)):
        odds.setdefault((r["match_id"], r["kind"]), {})[r["bookmaker"]] = (r["odd_h"], r["odd_d"], r["odd_a"])
    return rows, odds


def _pick(odds, mid, kind, books):
    d = odds.get((mid, kind), {})
    for b in books:
        if b in d:
            return d[b]
    return None


def outcome(hg, ag):
    return 0 if hg > ag else 1 if hg == ag else 2


def run(conn, league, test_seasons, refit_days=7, train_years=4, xi=0.0019, edge=0.03, run_id=None, save=True,
        warmup_seasons=None, ridge=40.0):
    """Rejeu « à la date ». Le modèle ancré se cale sur des prévisions passées déjà connues :
    saisons de calage (warmup_seasons, par défaut les 2 précédant le test), puis fenêtre croissante pendant le test."""
    run_id = run_id or uuid.uuid4().hex[:12]
    rows, odds = load(conn, league)
    seasons = sorted({r["season"] for r in rows})
    if warmup_seasons is None:
        warmup_seasons = [x for x in seasons if x < min(test_seasons)][-2:]
    by_known = sorted(rows, key=lambda r: r["known_at"])
    cal = features.calendar_features(rows)
    elo, dc = Elo(), DixonColes(xi=xi)
    dcx = DixonColes(xi=xi, n_ctx=len(features.FEATURE_NAMES))
    anchor = Anchor(ridge=ridge)
    ptr, last_season, last_fit_day, last_fitx_day, last_anchor_day = 0, None, None, None, None
    known = []     # résultats connus (jour, home, away, hg, ag, variables)
    pending = []   # (known_at, n, échantillon d'ancrage) : n'entre dans le calage qu'une fois le résultat connu
    training = []
    res = {"market": [], "market_pre": [], "elo": [], "dc": [], "dc_ctx": [], "anchor": []}
    outs, mids = [], []
    bets, bets_anchor = [], []

    for m in rows:
        ko = m["kickoff"]
        # 1) n'intégrer que les résultats connus STRICTEMENT avant ce coup d'envoi
        while ptr < len(by_known) and by_known[ptr]["known_at"] < ko:
            r = by_known[ptr]
            if last_season is not None and r["season"] != last_season:
                elo.new_season()
            last_season = r["season"]
            elo.update(r["home"], r["away"], r["hg"], r["ag"])
            known.append((_day(r["kickoff"]), r["home"], r["away"], r["hg"], r["ag"], features.features_as_of(cal, r["id"])))
            ptr += 1
        in_test = m["season"] in test_seasons
        if not (in_test or m["season"] in warmup_seasons):
            continue
        pre = _pick(odds, m["id"], "pre", PRE_BOOKS)
        close = _pick(odds, m["id"], "close", CLOSE_BOOKS)
        if pre is None or (in_test and close is None):
            continue
        today = _day(ko)
        # 2) réestimation périodique sur fenêtre glissante
        train = None
        if last_fit_day is None or today - last_fit_day >= refit_days:
            train = [k for k in known if k[0] >= today - int(train_years * 365)]
            dc.fit(train, today)
            last_fit_day = today
        if in_test and (last_fitx_day is None or today - last_fitx_day >= refit_days):
            train = train or [k for k in known if k[0] >= today - int(train_years * 365)]
            dcx.fit(train, today)
            last_fitx_day = today
        while pending and pending[0][0] < ko:           # résultats désormais connus -> données de calage
            training.append(heapq.heappop(pending)[2])
        if last_anchor_day is None or today - last_anchor_day >= refit_days:
            anchor.fit(training)
            last_anchor_day = today
        p_pre = market.devig_power(pre)
        p_dc = dc.predict(m["home"], m["away"])
        o = outcome(m["hg"], m["ag"])
        heapq.heappush(pending, (m["known_at"], len(pending) + len(training), (p_pre, p_dc, o)))
        if not in_test:
            continue
        p_mkt = market.devig_power(close)
        p_elo = elo.predict(m["home"], m["away"])
        p_dcx = dcx.predict(m["home"], m["away"], x=features.features_as_of(cal, m["id"]))
        p_anc = anchor.predict(p_pre, p_dc)
        allp = (("market", p_mkt), ("market_pre", p_pre), ("elo", p_elo), ("dc", p_dc), ("dc_ctx", p_dcx), ("anchor", p_anc))
        for k_, v_ in allp:
            res[k_].append(v_)
        outs.append(o)
        mids.append(m["id"])
        if save:
            for name, p in allp:
                conn.execute("INSERT OR IGNORE INTO predictions VALUES (?,?,?,?,?,?,?)", (run_id, name, m["id"], ko, *p))
        # 3) signaux de valeur contre la cote prenable (modèle statistique seul, puis modèle ancré)
        taken = _pick(odds, m["id"], "pre", [TAKEN_BOOK])
        if taken:
            for p_, bucket in ((p_dc, bets), (p_anc, bets_anchor)):
                best = max(range(3), key=lambda i: market.ev(p_[i], taken[i]))
                e = market.ev(p_[best], taken[best])
                if edge <= e <= 0.5:
                    bucket.append({"mid": m["id"], "sel": best, "odds": taken[best], "p": p_[best], "ev": e,
                                   "win": best == o, "clv": market.clv(taken[best], p_mkt[best])})
    out = {"run_id": run_id, "league": league, "seasons": list(test_seasons), "preds": res, "outcomes": outs,
           "match_ids": mids, "bets": bets, "bets_anchor": bets_anchor, "dc": dc, "dc_ctx": dcx, "elo": elo,
           "anchor": anchor, "warmup_seasons": list(warmup_seasons), "anchor_samples": len(training)}
    if save:
        conn.execute("INSERT OR REPLACE INTO runs (run_id, league, seasons, summary) VALUES (?,?,?,?)",
                     (run_id, league, json.dumps(list(test_seasons)), json.dumps(summarize(out))))
        conn.commit()
    return out


def summarize(r):
    """Résumé JSON stocké avec le run (utilisé par l'API)."""
    outs = r["outcomes"]
    summ = {"n": len(outs), "scores": {}, "bets": None, "bets_anchor": None, "theta": r["dc_ctx"].theta,
            "anchor": {"theta": r["anchor"].theta, "samples": r.get("anchor_samples"), "warmup": r.get("warmup_seasons")}}
    if outs:
        for name, preds in r["preds"].items():
            s = metrics.score(preds, outs)
            s["ece"] = metrics.ece(preds, outs)
            summ["scores"][name] = s
    for key, bets in (("bets", r["bets"]), ("bets_anchor", r.get("bets_anchor"))):
        if bets:
            profit = [(x["odds"] - 1) if x["win"] else -1.0 for x in bets]
            lo, hi = metrics.bootstrap_ci(profit)
            bk, mdd = bankroll_sim(bets)
            summ[key] = {"n": len(bets), "roi": metrics.mean(profit), "roi_lo": lo, "roi_hi": hi,
                         "clv": metrics.mean([x["clv"] for x in bets]), "bankroll_end": bk, "max_drawdown": mdd}
    return summ


def bankroll_sim(bets, start=100.0):
    bk, peak, mdd = start, start, 0.0
    for b in bets:
        f = market.kelly_fraction(b["p"], b["odds"])
        stake = bk * f
        bk += stake * (b["odds"] - 1) if b["win"] else -stake
        peak = max(peak, bk)
        mdd = max(mdd, (peak - bk) / peak)
    return bk, mdd


def report(r):
    outs = r["outcomes"]
    lines = [f"# Backtest {r['league']} — saisons {', '.join(r['seasons'])} (run {r['run_id']})", ""]
    if not outs:
        return "\n".join(lines + ["Aucun match évalué (données ou cotes de clôture manquantes)."])
    lines += [f"Matchs évalués : **{len(outs)}** (même échantillon pour tous les modèles).", "",
              "| Modèle | Log-loss | RPS | Brier | ECE |", "|---|---|---|---|---|"]
    scores = {}
    for name in ("market", "market_pre", "elo", "dc", "dc_ctx", "anchor"):
        s = metrics.score(r["preds"][name], outs)
        scores[name] = s
        lines.append(f"| {name} | {s['log_loss']:.4f} | {s['rps']:.4f} | {s['brier']:.4f} | "
                     f"{metrics.ece(r['preds'][name], outs):.4f} |")
    lines += ["", "*market = cotes de clôture sans marge (modèle 0, à battre) ; market_pre = cotes avant match (l'ancre) ; anchor = ancre corrigée par dc. Plus bas = mieux.*", ""]
    for name, ref in (("elo", "market"), ("dc", "market"), ("dc_ctx", "market"), ("dc_ctx", "dc"), ("market_pre", "market"), ("anchor", "market_pre"), ("anchor", "market"), ("anchor", "dc")):
        d = [metrics.log_loss(p, o) - metrics.log_loss(q, o)
             for p, q, o in zip(r["preds"][name], r["preds"][ref], outs)]
        lo, hi = metrics.bootstrap_ci(d)
        verdict = "meilleur" if hi < 0 else "moins bon" if lo > 0 else "indistinguable"
        lines.append(f"- {name} − {ref} (log-loss, IC 95 % bootstrap) : {metrics.mean(d):+.4f} [{lo:+.4f} ; {hi:+.4f}] → **{verdict}**")
    th = r["dc_ctx"].theta
    lines += ["", "Coefficients de contexte (dernier réajustement) : " +
              ", ".join(f"{n}={t:+.3f}" for n, t in zip(features.FEATURE_NAMES, th)),
              "", "**Règle d'activation** : une variable n'est activée en production que si dc_ctx est *meilleur* que dc "
              "(intervalle de confiance entièrement sous 0). Sinon elle reste collectée mais désactivée.", ""]
    th = r["anchor"].theta
    lines += ["", f"Ancrage : poids marché wm={th[0]:.3f}, poids modèle wd={th[1]:.3f}, biais nul={th[2]:+.3f}, biais extérieur={th[3]:+.3f} "
              f"(calé sur {r['anchor_samples']} matchs ; saisons de calage {', '.join(r['warmup_seasons']) or 'aucune'}). "
              "Marché pur = (1, 0, 0, 0).", ""]
    dA = [metrics.log_loss(p, o) - metrics.log_loss(q, o) for p, q, o in zip(r["preds"]["anchor"], r["preds"]["market_pre"], outs)]
    loA, hiA = metrics.bootstrap_ci(dA)
    lines += [f"**Règle d'activation de l'ancrage** : il n'est utilisé en production que si anchor bat market_pre "
              f"(IC 95 % entièrement sous 0). Écart : {metrics.mean(dA):+.4f} [{loA:+.4f} ; {hiA:+.4f}] → "
              f"**{'activé' if hiA < 0 else 'non activé : le prix du marché reste la meilleure estimation'}**.", ""]
    ba = r.get("bets_anchor")
    if ba:
        pa = [(x["odds"] - 1) if x["win"] else -1.0 for x in ba]
        lo, hi = metrics.bootstrap_ci(pa)
        lines += [f"Paris simulés avec le modèle ancré (EV ≥ 3 % contre {TAKEN_BOOK}) : **{len(ba)}**, ROI {metrics.mean(pa):+.1%} (IC 95 % [{lo:+.1%} ; {hi:+.1%}]), CLV moyen {metrics.mean([x['clv'] for x in ba]):+.2%}.", ""]
    else:
        lines += ["Modèle ancré : aucun signal à EV ≥ 3 % (il reste proche du marché).", ""]
    b = r["bets"]
    lines += ["", f"## Simulation de paris (modèle dc contre cotes {TAKEN_BOOK} avant match, seuil EV ≥ 3 %)", ""]
    if b:
        profit = [(x["odds"] - 1) if x["win"] else -1.0 for x in b]
        lo, hi = metrics.bootstrap_ci(profit)
        clvs = [x["clv"] for x in b]
        bk, mdd = bankroll_sim(b)
        lines += [f"- Paris simulés : **{len(b)}** ; ROI mise plate : {metrics.mean(profit):+.1%} (IC 95 % [{lo:+.1%} ; {hi:+.1%}])",
                  f"- CLV moyen : {metrics.mean(clvs):+.2%}",
                  f"- Bankroll au quart de Kelly (plafond 2 %) : 100 → {bk:.1f} ; drawdown max {mdd:.0%}",
                  "- Attention : sous quelques milliers de paris, le ROI n'a aucune valeur probante (voir analyse technique, section 10.4)."]
    else:
        lines.append("- Aucun signal émis.")
    lines += ["", "## Calibration du modèle dc", "", "| Tranche | n | p moyenne | fréquence observée |", "|---|---|---|---|"]
    for lo_, hi_, n, pm, fr in metrics.calibration(r["preds"]["dc"], outs):
        lines.append(f"| {lo_:.1f}–{hi_:.1f} | {n} | {pm:.3f} | {fr:.3f} |")
    return "\n".join(lines) + "\n"
