"""Couche de service : toute la logique des réponses de l'API (sans dépendance web, donc testable seule)."""
import json
from datetime import datetime

from . import market, metrics
from .dixoncoles import DixonColes, markets

MODELS = ("market", "elo", "dc", "dc_ctx")
_MODEL_CACHE = {}
_PERF_CACHE = {}  # un run est immuable : son résultat ne change jamais


class NotFound(Exception):
    pass


def leagues(conn):
    return [dict(r) for r in conn.execute(
        "SELECT league, COUNT(*) AS matches, MIN(season) AS first_season, MAX(season) AS last_season, "
        "MAX(kickoff) AS last_kickoff FROM matches GROUP BY league ORDER BY league")]


def teams(conn, league):
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT home FROM matches WHERE league = ? ORDER BY home", (league,))]


def runs(conn, league=None, limit=20):
    q = "SELECT run_id, league, seasons, created_at, summary FROM runs"
    args = []
    if league:
        q += " WHERE league = ?"
        args.append(league)
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    out = []
    for r in conn.execute(q, args):
        d = dict(r)
        d["seasons"] = json.loads(d["seasons"])
        d["summary"] = json.loads(d["summary"])
        out.append(d)
    return out


def resolve_run(conn, run_id=None, league=None):
    if run_id:
        row = conn.execute("SELECT run_id FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    else:
        q = "SELECT run_id FROM runs" + (" WHERE league = ?" if league else "") + " ORDER BY created_at DESC LIMIT 1"
        row = conn.execute(q, (league,) if league else ()).fetchone()
    if not row:
        raise NotFound("Aucun backtest enregistré : lancez `python -m probafoot backtest`.")
    return row[0]


def _preds_by_match(conn, run_id):
    out = {}
    for r in conn.execute("SELECT match_id, model, p_h, p_d, p_a, as_of FROM predictions WHERE run_id = ?", (run_id,)):
        out.setdefault(r["match_id"], {})[r["model"]] = [r["p_h"], r["p_d"], r["p_a"]]
        out[r["match_id"]]["_as_of"] = r["as_of"]
    return out


def _odds_for(conn, mid):
    d = {}
    for r in conn.execute("SELECT bookmaker, kind, odd_h, odd_d, odd_a FROM odds_snapshots WHERE match_id = ?", (mid,)):
        d.setdefault(r["kind"], {})[r["bookmaker"]] = [r["odd_h"], r["odd_d"], r["odd_a"]]
    return d


def _outcome(hg, ag):
    return 0 if hg > ag else 1 if hg == ag else 2


def matches(conn, league=None, season=None, run_id=None, limit=50, offset=0):
    run_id = resolve_run(conn, run_id, league)
    preds = _preds_by_match(conn, run_id)
    ids = list(preds)
    if not ids:
        return {"run_id": run_id, "total": 0, "items": []}
    q = "SELECT * FROM matches WHERE id IN (%s)" % ",".join("?" * len(ids))
    args = list(ids)
    if league:
        q += " AND league = ?"
        args.append(league)
    if season:
        q += " AND season = ?"
        args.append(season)
    rows = conn.execute(q + " ORDER BY kickoff DESC", args).fetchall()
    total = len(rows)
    items = []
    for r in rows[offset:offset + limit]:
        p = preds[r["id"]]
        taken = _odds_for(conn, r["id"]).get("pre", {}).get("B365")
        ev = [round(market.ev(p["dc"][i], taken[i]), 4) for i in range(3)] if taken and "dc" in p else None
        items.append({
            "id": r["id"], "league": r["league"], "season": r["season"], "kickoff": r["kickoff"],
            "home": r["home"], "away": r["away"], "hg": r["hg"], "ag": r["ag"],
            "result": "HDA"[_outcome(r["hg"], r["ag"])],
            "probs": {m: p[m] for m in MODELS if m in p},
            "odds_b365_pre": taken, "ev_dc": ev, "as_of": p["_as_of"],
        })
    return {"run_id": run_id, "total": total, "items": items}


def match_detail(conn, match_id, run_id=None):
    r = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not r:
        raise NotFound(f"Match {match_id} introuvable")
    run_id = resolve_run(conn, run_id, r["league"])
    probs = _preds_by_match(conn, run_id).get(match_id, {})
    events = [{"event_type": e["event_type"], "occurred_at": e["occurred_at"], "known_at": e["known_at"],
               "source": e["source"], "payload": json.loads(e["payload"])}
              for e in conn.execute("SELECT * FROM events WHERE match_id = ? ORDER BY known_at", (match_id,))]
    odds = _odds_for(conn, match_id)
    close = None
    for b in ("PS", "B365", "AVG"):
        if b in odds.get("close", {}):
            close = market.devig_power(odds["close"][b])
            break
    return {
        "id": r["id"], "league": r["league"], "season": r["season"], "kickoff": r["kickoff"],
        "home": r["home"], "away": r["away"], "hg": r["hg"], "ag": r["ag"],
        "result": "HDA"[_outcome(r["hg"], r["ag"])], "run_id": run_id, "as_of": probs.pop("_as_of", None),
        "probs": probs, "odds": odds, "close_fair_probs": close, "events": events,
    }


def performance(conn, run_id=None, league=None):
    run_id = resolve_run(conn, run_id, league)
    if run_id in _PERF_CACHE:
        return _PERF_CACHE[run_id]
    run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    rows = conn.execute(
        "SELECT p.match_id, p.model, p.p_h, p.p_d, p.p_a, m.kickoff, m.hg, m.ag FROM predictions p "
        "JOIN matches m ON m.id = p.match_id WHERE p.run_id = ? ORDER BY m.kickoff", (run_id,)).fetchall()
    per = {}
    outs = {}
    kick = {}
    for r in rows:
        per.setdefault(r["model"], {})[r["match_id"]] = [r["p_h"], r["p_d"], r["p_a"]]
        outs[r["match_id"]] = _outcome(r["hg"], r["ag"])
        kick[r["match_id"]] = r["kickoff"]
    order = sorted(outs, key=lambda i: kick[i])
    result = {"run_id": run_id, "league": run["league"], "seasons": json.loads(run["seasons"]),
              "n": len(order), "models": {}, "paired": {}, "calibration": [], "cumulative": []}
    for name, d in per.items():
        ps = [d[i] for i in order if i in d]
        os_ = [outs[i] for i in order if i in d]
        s = metrics.score(ps, os_)
        s["ece"] = metrics.ece(ps, os_)
        result["models"][name] = s
    if "market" in per:
        for name in per:
            if name == "market":
                continue
            diffs = [metrics.log_loss(per[name][i], outs[i]) - metrics.log_loss(per["market"][i], outs[i]) for i in order]
            lo, hi = metrics.bootstrap_ci(diffs)
            result["paired"][name + "_vs_market"] = {"mean": metrics.mean(diffs), "lo": lo, "hi": hi,
                                                     "verdict": "meilleur" if hi < 0 else "moins bon" if lo > 0 else "indistinguable"}
        for name in ("dc",):
            if name in per:
                ps = [per[name][i] for i in order]
                result["calibration"] = [{"lo": a, "hi": b, "n": n, "p_mean": pm, "freq": fr}
                                         for a, b, n, pm, fr in metrics.calibration(ps, [outs[i] for i in order])]
                cm = cd = 0.0
                for k, i in enumerate(order, 1):
                    cm += metrics.log_loss(per["market"][i], outs[i])
                    cd += metrics.log_loss(per[name][i], outs[i])
                    if k % 10 == 0 or k == len(order):
                        result["cumulative"].append({"n": k, "date": kick[i][:10], "market": cm / k, "dc": cd / k})
    if "anchor" in per and "market_pre" in per:
        diffs = [metrics.log_loss(per["anchor"][i], outs[i]) - metrics.log_loss(per["market_pre"][i], outs[i]) for i in order]
        lo, hi = metrics.bootstrap_ci(diffs)
        result["paired"]["anchor_vs_market_pre"] = {"mean": metrics.mean(diffs), "lo": lo, "hi": hi,
                                                    "verdict": "meilleur" if hi < 0 else "moins bon" if lo > 0 else "indistinguable"}
    summ = json.loads(run["summary"])
    result["anchor"] = summ.get("anchor")
    result["bets_anchor"] = summ.get("bets_anchor")
    result["bets"] = json.loads(run["summary"]).get("bets")
    _PERF_CACHE[run_id] = result
    return result


def predict(conn, league, home, away):
    known = set(teams(conn, league))
    if not known:
        raise NotFound(f"Ligue {league} inconnue")
    for t in (home, away):
        if t not in known:
            raise NotFound(f"Équipe inconnue dans {league} : {t}")
    if home == away:
        raise NotFound("Deux équipes différentes requises")
    stamp = conn.execute("SELECT MAX(kickoff), COUNT(*) FROM matches WHERE league = ?", (league,)).fetchone()
    stamp = tuple(stamp)
    cached = _MODEL_CACHE.get(league)
    if not cached or cached[0] != stamp:
        rows = conn.execute("SELECT kickoff, home, away, hg, ag FROM matches WHERE league = ? ORDER BY kickoff",
                            (league,)).fetchall()
        data = [(datetime.fromisoformat(r["kickoff"]).toordinal(), r["home"], r["away"], r["hg"], r["ag"]) for r in rows]
        last = data[-1][0]
        dc = DixonColes().fit([d for d in data if d[0] >= last - 4 * 365], last)
        _MODEL_CACHE[league] = cached = (stamp, dc)
    dc = cached[1]
    m = dc.matrix(home, away)
    lam, mu = dc.rates(home, away)
    mk = markets(m)
    top = sorted(((x, y, v) for x, r in enumerate(m) for y, v in enumerate(r)), key=lambda t: -t[2])[:6]
    return {
        "league": league, "home": home, "away": away, "model": "dixon-coles", "trained_until": stamp[0],
        "expected_goals": {"home": lam, "away": mu}, "rho": dc.rho,
        "markets": {k: {"p": v, "fair_odds": 1 / v if v > 0 else None} for k, v in mk.items()},
        "top_scores": [{"score": f"{x}-{y}", "p": v} for x, y, v in top],
        "notice": "Estimation statistique, pas une certitude. Sans compositions ni blessures. Aucune garantie de gain.",
    }


def _latest_ticks(conn, event_id):
    """Dernière cote de chaque bookmaker et première cote observée (ouverture)."""
    rows = conn.execute("SELECT bookmaker, captured_at, odd_h, odd_d, odd_a FROM odds_ticks WHERE event_id = ? ORDER BY captured_at", (event_id,)).fetchall()
    first, last = {}, {}
    for r in rows:
        o = [r["odd_h"], r["odd_d"], r["odd_a"]]
        first.setdefault(r["bookmaker"], o)
        last[r["bookmaker"]] = (o, r["captured_at"])
    return first, last


def _consensus(books):
    """Moyenne des probabilités sans marge de plusieurs bookmakers."""
    ps = [market.devig_power(o) for o in books]
    return [sum(p[i] for p in ps) / len(ps) for i in range(3)] if ps else None


def upcoming(conn, league=None, limit=30, now=None):
    """Matchs à venir avec cotes captées, mouvement depuis l'ouverture et, si possible, estimation du modèle."""
    now_s = (now or datetime.utcnow()).strftime("%Y-%m-%dT%H:%M")
    q = "SELECT * FROM fixtures WHERE commence >= ?" + (" AND league = ?" if league else "") + " ORDER BY commence LIMIT ?"
    args = [now_s] + ([league] if league else []) + [limit]
    items = []
    for f in conn.execute(q, args).fetchall():
        first, last = _latest_ticks(conn, f["event_id"])
        if not last:
            continue
        cur = {b: v[0] for b, v in last.items()}
        best = []
        for i in range(3):
            bk = max(cur, key=lambda b: cur[b][i])
            best.append({"odds": cur[bk][i], "bookmaker": bk})
        fair = _consensus(list(cur.values()))
        opening = _consensus([first[b] for b in cur])
        item = {
            "event_id": f["event_id"], "league": f["league"], "commence": f["commence"], "home": f["home"], "away": f["away"],
            "n_books": len(cur), "best": best, "fair": fair,
            "move": [fair[i] - opening[i] for i in range(3)] if opening else None,
            "last_capture": max(v[1] for v in last.values()),
            "model": None, "ev": None, "resolved": bool(f["home_db"] and f["away_db"]),
        }
        if item["resolved"]:
            try:
                pr = predict(conn, f["league"], f["home_db"], f["away_db"])
                m = [pr["markets"]["1"]["p"], pr["markets"]["X"]["p"], pr["markets"]["2"]["p"]]
                item["model"] = m
                item["ev"] = [market.ev(m[i], best[i]["odds"]) for i in range(3)]
            except NotFound:
                pass
        items.append(item)
    return {"items": items, "as_of": now_s}


def capture_status(conn):
    last = [dict(r) for r in conn.execute(
        "SELECT l.* FROM capture_log l JOIN (SELECT league, MAX(id) mid FROM capture_log GROUP BY league) m ON l.id = m.mid ORDER BY l.league")]
    tot = conn.execute("SELECT (SELECT COUNT(*) FROM fixtures), (SELECT COUNT(*) FROM odds_ticks), "
                       "(SELECT COUNT(*) FROM fixtures WHERE home_db IS NULL OR away_db IS NULL)").fetchone()
    return {"leagues": last, "fixtures": tot[0], "ticks": tot[1], "unresolved_fixtures": tot[2]}
