"""Import Football-Data.co.uk (CSV) vers matchs, journal d'événements et cotes. Idempotent."""
import csv
import json
import re
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
SOURCE = "football-data.co.uk"
NS = uuid.UUID("6f1c2d3e-0000-4000-8000-00000000f007")

# (bookmaker, préfixe de colonne) ; 'pre' = <préfixe>H/D/A, 'close' = <préfixe>CH/CD/CA
BOOKS = [("PS", "PS"), ("B365", "B365"), ("AVG", "Avg"), ("MAX", "Max")]
ALIASES = {
    "Man United": "Manchester United", "Man City": "Manchester City", "Nott'm Forest": "Nottingham Forest",
    "Paris SG": "Paris Saint-Germain", "St Etienne": "Saint-Etienne",
}


def norm_team(name):
    name = re.sub(r"\s+", " ", name.strip())
    return ALIASES.get(name, name)


def download(season, league, force=False):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{season}_{league}.csv"
    if path.exists() and path.stat().st_size > 0 and not force:
        return path
    req = urllib.request.Request(URL.format(season=season, league=league), headers={"User-Agent": "probafoot/0.1"})
    with urllib.request.urlopen(req, timeout=40) as r:
        data = r.read()
    path.write_bytes(data)  # brut conservé tel quel
    return path


def parse_kickoff(date_s, time_s):
    d = None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            d = datetime.strptime((date_s or "").strip(), fmt)
            break
        except ValueError:
            continue
    if d is None:
        return None
    hh, mm = 15, 0
    if time_s and re.fullmatch(r"\d{1,2}:\d{2}", time_s.strip()):
        hh, mm = map(int, time_s.strip().split(":"))
    return d.replace(hour=hh, minute=mm)


def _f(row, key):
    try:
        v = float(row.get(key, "") or "")
        return v if v > 1.0 else None
    except ValueError:
        return None


def ingest_file(conn, path, league, season):
    n_new = 0
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            ko = parse_kickoff(row.get("Date", ""), row.get("Time", ""))
            home, away = norm_team(row.get("HomeTeam", "")), norm_team(row.get("AwayTeam", ""))
            if not ko or not home or not away:
                continue
            try:
                hg, ag = int(row["FTHG"]), int(row["FTAG"])
            except (KeyError, ValueError):
                continue  # match non joué
            kick = ko.strftime("%Y-%m-%dT%H:%M")
            cur = conn.execute(
                "INSERT OR IGNORE INTO matches (league,season,kickoff,home,away,hg,ag) VALUES (?,?,?,?,?,?,?)",
                (league, season, kick, home, away, hg, ag))
            if cur.rowcount:
                n_new += 1
            mid = conn.execute("SELECT id FROM matches WHERE league=? AND kickoff=? AND home=? AND away=?",
                               (league, kick, home, away)).fetchone()[0]
            # Résultat : survenu ~ coup d'envoi + 2 h, connu 10 min plus tard (approximation documentée).
            occ = (ko + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
            known = (ko + timedelta(hours=2, minutes=10)).strftime("%Y-%m-%dT%H:%M")
            ref = f"{league}/{season}/{kick}/{home}-{away}"
            conn.execute(
                "INSERT OR IGNORE INTO events (event_id,event_type,match_id,payload,occurred_at,known_at,source,source_ref) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid5(NS, f"{SOURCE}|{ref}|MATCH_RESULT")), "MATCH_RESULT", mid,
                 json.dumps({"hg": hg, "ag": ag}), occ, known, SOURCE, ref))
            for bk, pre in BOOKS:
                for kind, cols in (("pre", (pre + "H", pre + "D", pre + "A")),
                                   ("close", (pre + "CH", pre + "CD", pre + "CA"))):
                    o = [_f(row, c) for c in cols]
                    if all(o):
                        conn.execute("INSERT OR IGNORE INTO odds_snapshots VALUES (?,?,?,?,?,?)", (mid, bk, kind, *o))
    conn.commit()
    return n_new


def ingest(conn, leagues, seasons, fetch=True):
    total = 0
    for lg in leagues:
        for s in seasons:
            path = RAW_DIR / f"{s}_{lg}.csv"
            if not path.exists() and fetch:
                try:
                    path = download(s, lg)
                except Exception as exc:  # source indisponible : on continue, reprise possible
                    print(f"  ! {s} {lg}: téléchargement impossible ({exc})")
                    continue
            if not path.exists():
                continue
            n = ingest_file(conn, path, lg, s)
            total += n
            print(f"  {lg} {s}: {n} nouveaux matchs")
    return total
