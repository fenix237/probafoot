"""Stockage SQLite : matchs, journal d'événements bitemporel, cotes, prédictions."""
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "probafoot.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
  id INTEGER PRIMARY KEY,
  league TEXT NOT NULL, season TEXT NOT NULL,
  kickoff TEXT NOT NULL,                       -- ISO 'YYYY-MM-DDTHH:MM' (UTC approx.)
  home TEXT NOT NULL, away TEXT NOT NULL,
  hg INTEGER, ag INTEGER,
  status TEXT NOT NULL DEFAULT 'FT',
  UNIQUE (league, kickoff, home, away)
);
CREATE INDEX IF NOT EXISTS ix_matches_kick ON matches (league, kickoff);

-- Journal d'événements en ajout seul, bitemporel (occurred_at / known_at).
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  match_id INTEGER REFERENCES matches(id),
  payload TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  known_at TEXT NOT NULL CHECK (known_at >= occurred_at),
  source TEXT NOT NULL, source_ref TEXT,
  schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_events_match ON events (match_id, known_at);
CREATE INDEX IF NOT EXISTS ix_events_known ON events (event_type, known_at);

CREATE TABLE IF NOT EXISTS odds_snapshots (
  match_id INTEGER NOT NULL REFERENCES matches(id),
  bookmaker TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('pre','close')),
  odd_h REAL NOT NULL, odd_d REAL NOT NULL, odd_a REAL NOT NULL,
  PRIMARY KEY (match_id, bookmaker, kind)
);

-- Capture de cotes en continu (The Odds API) : matchs à venir et historique horodaté.
CREATE TABLE IF NOT EXISTS fixtures (
  event_id TEXT PRIMARY KEY, league TEXT NOT NULL, commence TEXT NOT NULL,   -- 'YYYY-MM-DDTHH:MM' UTC
  home TEXT NOT NULL, away TEXT NOT NULL,
  home_db TEXT, away_db TEXT,                  -- noms résolus vers la table matches (NULL = à revoir)
  first_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fixtures_commence ON fixtures (league, commence);
CREATE TABLE IF NOT EXISTS odds_ticks (        -- ajout seul ; une ligne seulement quand la cote change
  event_id TEXT NOT NULL REFERENCES fixtures(event_id), bookmaker TEXT NOT NULL, captured_at TEXT NOT NULL,
  odd_h REAL NOT NULL, odd_d REAL NOT NULL, odd_a REAL NOT NULL, source_update TEXT,
  PRIMARY KEY (event_id, bookmaker, captured_at)
);
CREATE TABLE IF NOT EXISTS capture_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, captured_at TEXT NOT NULL, league TEXT NOT NULL,
  ok INTEGER NOT NULL, events INTEGER NOT NULL DEFAULT 0, new_ticks INTEGER NOT NULL DEFAULT 0,
  remaining INTEGER, used INTEGER, message TEXT
);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, league TEXT NOT NULL, seasons TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
  summary TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS predictions (       -- jamais modifiée, uniquement ajoutée
  run_id TEXT NOT NULL, model TEXT NOT NULL, match_id INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  p_h REAL NOT NULL, p_d REAL NOT NULL, p_a REAL NOT NULL,
  PRIMARY KEY (run_id, model, match_id)
);
"""


def connect(path=None):
    path = Path(path or os.environ.get("PROBAFOOT_DB") or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # lecteurs (API) et écrivain (worker) en parallèle
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    return conn
