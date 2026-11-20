"""Capture de cotes 1X2 (The Odds API v4) : historique horodaté, résolution des noms, suivi du quota.

La clé vient de la variable d'environnement ODDS_API_KEY ; elle n'est jamais écrite dans la base,
les journaux ni les messages d'erreur. Offre gratuite : environ 500 crédits par mois ; un appel coûte
(nombre de régions x nombre de marchés) crédits par ligue.
"""
import difflib
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SPORT_KEYS = {"E0": "soccer_epl", "F1": "soccer_france_ligue_one"}
BASE = "https://api.the-odds-api.com/v4/sports/{sport}/odds/"

# Noms utilisés par l'API -> noms Football-Data (clé : nom normalisé). Complété par un rapprochement approximatif.
ALIASES = {
    "wolverhampton wanderers": "Wolves", "brighton and hove albion": "Brighton", "tottenham hotspur": "Tottenham",
    "newcastle united": "Newcastle", "west ham united": "West Ham", "leicester city": "Leicester", "leeds united": "Leeds",
    "ipswich town": "Ipswich", "norwich city": "Norwich", "afc bournemouth": "Bournemouth", "luton town": "Luton",
    "west bromwich albion": "West Brom", "sheffield united": "Sheffield United", "nottingham forest": "Nottingham Forest",
    "paris saint germain": "Paris Saint-Germain", "olympique de marseille": "Marseille", "olympique lyonnais": "Lyon",
    "as monaco": "Monaco", "stade rennais": "Rennes", "lille osc": "Lille", "ogc nice": "Nice", "rc lens": "Lens",
    "stade brestois": "Brest", "rc strasbourg alsace": "Strasbourg", "rc strasbourg": "Strasbourg", "toulouse fc": "Toulouse",
    "fc nantes": "Nantes", "montpellier hsc": "Montpellier", "stade de reims": "Reims", "le havre ac": "Le Havre",
    "aj auxerre": "Auxerre", "angers sco": "Angers", "fc lorient": "Lorient", "fc metz": "Metz", "as saint etienne": "St Etienne",
}


class CaptureError(Exception):
    """Erreur de capture sans aucune donnée sensible dans le message."""
    def __init__(self, message, fatal=False):
        super().__init__(message)
        self.fatal = fatal


def now_iso(now=None):
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S")


def _key(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9& ]+", " ", s).replace("&", " and ")
    s = re.sub(r"\b(fc|afc|cf|sc)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def resolve_team(name, known):
    """Nom API -> nom de la base, ou None si incertain (jamais d'appariement ambigu)."""
    index = {_key(k): k for k in known}
    k = _key(name)
    if k in index:
        return index[k]
    target = ALIASES.get(k)
    if target and target in known:
        return target
    close = difflib.get_close_matches(k, list(index), n=2, cutoff=0.84)
    if len(close) == 1:
        return index[close[0]]
    if len(close) == 2:
        r = [difflib.SequenceMatcher(None, k, c).ratio() for c in close]
        if r[0] - r[1] > 0.08:
            return index[close[0]]
    return None


def fetch(league, api_key, regions="eu", timeout=30):
    if league not in SPORT_KEYS:
        raise CaptureError(f"Ligue {league} non prise en charge (ligues : {', '.join(SPORT_KEYS)})")
    qs = urllib.parse.urlencode({"regions": regions, "markets": "h2h", "oddsFormat": "decimal", "dateFormat": "iso", "apiKey": api_key})
    req = urllib.request.Request(BASE.format(sport=SPORT_KEYS[league]) + "?" + qs, headers={"User-Agent": "probafoot/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            hdr = {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        msg = {401: "clé API refusée (vérifiez ODDS_API_KEY)", 422: "paramètres refusés par l'API",
               429: "quota ou débit dépassé"}.get(e.code, f"erreur HTTP {e.code}")
        raise CaptureError(msg, fatal=e.code in (401, 429)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise CaptureError("réseau indisponible ou délai dépassé") from None
    except ValueError:
        raise CaptureError("réponse illisible") from None

    def num(k):
        try:
            return int(float(hdr.get(k, "")))
        except ValueError:
            return None
    return data, {"remaining": num("x-requests-remaining"), "used": num("x-requests-used")}


def parse(events):
    """Réponse API -> liste de matchs avec leurs cotes 1X2 par bookmaker (lignes invalides ignorées)."""
    out = []
    for ev in events if isinstance(events, list) else []:
        try:
            home, away = ev["home_team"], ev["away_team"]
            commence = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(timezone.utc)
        except (KeyError, ValueError, AttributeError):
            continue
        ticks = []
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk.get("key") != "h2h":
                    continue
                px = {o.get("name"): o.get("price") for o in mk.get("outcomes", [])}
                try:
                    h, d, a = float(px[home]), float(px["Draw"]), float(px[away])
                except (KeyError, TypeError, ValueError):
                    continue
                if min(h, d, a) <= 1.0:
                    continue
                ticks.append((bk.get("key", "?"), h, d, a, bk.get("last_update")))
        if ticks and ev.get("id"):
            out.append({"event_id": ev["id"], "commence": commence.strftime("%Y-%m-%dT%H:%M"), "home": home, "away": away, "ticks": ticks})
    return out


def store(conn, league, parsed, captured_at):
    """Écrit fixtures et cotes. Une ligne de cote n'est ajoutée que si elle diffère de la précédente."""
    known = [r[0] for r in conn.execute("SELECT DISTINCT home FROM matches WHERE league = ?", (league,))]
    new_ticks = 0
    for ev in parsed:
        row = conn.execute("SELECT home_db, away_db FROM fixtures WHERE event_id = ?", (ev["event_id"],)).fetchone()
        if row is None:
            conn.execute("INSERT INTO fixtures (event_id, league, commence, home, away, home_db, away_db, first_seen) VALUES (?,?,?,?,?,?,?,?)",
                         (ev["event_id"], league, ev["commence"], ev["home"], ev["away"],
                          resolve_team(ev["home"], known), resolve_team(ev["away"], known), captured_at))
        else:
            conn.execute("UPDATE fixtures SET commence = ? WHERE event_id = ?", (ev["commence"], ev["event_id"]))  # report éventuel
        for bk, h, d, a, upd in ev["ticks"]:
            last = conn.execute("SELECT odd_h, odd_d, odd_a FROM odds_ticks WHERE event_id = ? AND bookmaker = ? ORDER BY captured_at DESC LIMIT 1",
                                (ev["event_id"], bk)).fetchone()
            if last and (last[0], last[1], last[2]) == (h, d, a):
                continue
            cur = conn.execute("INSERT OR IGNORE INTO odds_ticks VALUES (?,?,?,?,?,?,?)", (ev["event_id"], bk, captured_at, h, d, a, upd))
            new_ticks += cur.rowcount
    conn.commit()
    return new_ticks


def _log(conn, captured_at, league, ok, events=0, new_ticks=0, remaining=None, used=None, message=None):
    conn.execute("INSERT INTO capture_log (captured_at, league, ok, events, new_ticks, remaining, used, message) VALUES (?,?,?,?,?,?,?,?)",
                 (captured_at, league, int(ok), events, new_ticks, remaining, used, message))
    conn.commit()


def last_remaining(conn):
    r = conn.execute("SELECT remaining FROM capture_log WHERE remaining IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    return r[0] if r else None


def run_capture(conn, leagues, api_key, regions="eu", min_credits=20, fetcher=fetch, now=None):
    """Un passage de capture. S'arrête proprement si le quota restant passe sous min_credits."""
    results = []
    for lg in leagues:
        ts = now_iso(now)
        rem = last_remaining(conn)
        if rem is not None and rem < min_credits:
            msg = f"quota restant trop bas ({rem} < {min_credits}) : capture suspendue"
            _log(conn, ts, lg, False, message=msg)
            results.append({"league": lg, "ok": False, "message": msg})
            break
        try:
            data, quota = fetcher(lg, api_key, regions)
            parsed = parse(data)
            n = store(conn, lg, parsed, ts)
            _log(conn, ts, lg, True, len(parsed), n, quota.get("remaining"), quota.get("used"))
            results.append({"league": lg, "ok": True, "events": len(parsed), "new_ticks": n, **quota})
        except CaptureError as e:
            _log(conn, ts, lg, False, message=str(e))
            results.append({"league": lg, "ok": False, "message": str(e)})
            if e.fatal:
                break
    return results


def capture_from_file(conn, league, path, now=None):
    """Rejoue une réponse API enregistrée (tests, reprise hors ligne)."""
    with open(path, encoding="utf-8") as fh:
        parsed = parse(json.load(fh))
    ts = now_iso(now)
    n = store(conn, league, parsed, ts)
    _log(conn, ts, league, True, len(parsed), n, message="rejeu depuis un fichier")
    return {"league": league, "ok": True, "events": len(parsed), "new_ticks": n}
