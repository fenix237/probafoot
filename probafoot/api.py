"""API FastAPI (lecture seule). Lancer : uvicorn probafoot.api:app --port 8000"""
import os
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__, db, service

DISCLAIMER = "Les paris comportent des risques de perte. Estimations statistiques, aucune garantie de gain. Réservé aux majeurs."

app = FastAPI(title="ProbaFoot API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("PROBAFOOT_CORS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["GET"], allow_headers=["*"],
)


@contextmanager
def _conn():
    conn = db.connect(os.environ.get("PROBAFOOT_DB"))
    try:
        yield conn
    finally:
        conn.close()


def _call(fn, *args, **kw):
    try:
        with _conn() as conn:
            data = fn(conn, *args, **kw)
    except service.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(data, dict):
        data = {**data, "disclaimer": DISCLAIMER}
    return data


@app.get("/v1/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/v1/leagues")
def leagues():
    return _call(lambda c: {"items": service.leagues(c)})


@app.get("/v1/teams")
def teams(league: str = "E0"):
    return _call(lambda c: {"items": service.teams(c, league)})


@app.get("/v1/runs")
def runs(league: str | None = None, limit: int = Query(20, ge=1, le=100)):
    return _call(lambda c: {"items": service.runs(c, league, limit)})


@app.get("/v1/matches")
def matches(league: str | None = None, season: str | None = None, run_id: str | None = None,
            limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return _call(service.matches, league, season, run_id, limit, offset)


@app.get("/v1/matches/{match_id}")
def match(match_id: int, run_id: str | None = None):
    return _call(service.match_detail, match_id, run_id)


@app.get("/v1/performance")
def performance(run_id: str | None = None, league: str | None = None):
    return _call(service.performance, run_id, league)


@app.get("/v1/predict")
def predict(league: str, home: str, away: str):
    return _call(service.predict, league, home, away)


@app.get("/v1/odds/upcoming")
def odds_upcoming(league: str | None = None, limit: int = Query(30, ge=1, le=100)):
    return _call(service.upcoming, league, limit)


@app.get("/v1/capture/status")
def capture_status():
    return _call(service.capture_status)


# Front sans build, servi à la racine (monté en dernier pour ne pas masquer /v1).
STATIC = Path(__file__).resolve().parent.parent / "static"
if STATIC.exists():
    app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="front")
