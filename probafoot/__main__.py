"""CLI : python -m probafoot {ingest,backtest,predict}"""
import argparse
import sys
from pathlib import Path

from . import backtest, capture, db, ingest
from .dixoncoles import DixonColes, markets
from .market import devig_power

DEFAULT_SEASONS = ["1516", "1617", "1718", "1819", "1920", "2021", "2122", "2223", "2324", "2425", "2526"]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="probafoot")
    ap.add_argument("--db", default=None, help="chemin SQLite (défaut data/probafoot.sqlite)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ingest", help="télécharge et importe les CSV Football-Data")
    a.add_argument("--leagues", nargs="+", default=["E0"])
    a.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS)
    a.add_argument("--offline", action="store_true", help="n'utiliser que les fichiers déjà dans data/raw")

    b = sub.add_parser("backtest", help="backtest glissant vs cotes de clôture")
    b.add_argument("--league", default="E0")
    b.add_argument("--test", nargs="+", default=["2223", "2324", "2425"])
    b.add_argument("--refit-days", type=int, default=7)
    b.add_argument("--xi", type=float, default=0.0019)
    b.add_argument("--edge", type=float, default=0.03)

    c = sub.add_parser("predict", help="probabilités d'un match à partir de tout l'historique")
    c.add_argument("--league", default="E0")
    c.add_argument("home")
    c.add_argument("away")

    k = sub.add_parser("capture", help="capture des cotes 1X2 (The Odds API) ; clé dans ODDS_API_KEY")
    k.add_argument("--leagues", nargs="+", default=["E0", "F1"])
    k.add_argument("--regions", default="eu")
    k.add_argument("--min-credits", type=int, default=20, help="suspend la capture sous ce quota restant")
    k.add_argument("--from-file", help="rejoue une réponse API enregistrée (JSON), sans clé ni réseau")
    sub.add_parser("capture-status", help="état de la capture et du quota")

    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    conn = db.connect(args.db)

    if args.cmd == "ingest":
        n = ingest.ingest(conn, args.leagues, args.seasons, fetch=not args.offline)
        print(f"Terminé : {n} nouveaux matchs.")
    elif args.cmd == "backtest":
        r = backtest.run(conn, args.league, args.test, refit_days=args.refit_days, xi=args.xi, edge=args.edge)
        text = backtest.report(r)
        out = Path(__file__).resolve().parent.parent / "reports" / f"backtest_{args.league}_{r['run_id']}.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(text)
        print(f"Rapport : {out}")
    elif args.cmd == "capture":
        import os
        if args.from_file:
            print(capture.capture_from_file(conn, args.leagues[0], args.from_file))
            return 0
        key = os.environ.get("ODDS_API_KEY", "").strip()
        if not key:
            print("ODDS_API_KEY absente : créez une clé gratuite sur the-odds-api.com puis définissez la variable d'environnement.")
            return 2
        res = capture.run_capture(conn, args.leagues, key, args.regions, args.min_credits)
        for r in res:
            print(("OK  " if r["ok"] else "ÉCHEC ") + str({k: v for k, v in r.items() if k != "ok"}))
        return 0 if all(r["ok"] for r in res) else 1
    elif args.cmd == "capture-status":
        from . import service
        print(service.capture_status(conn))
    elif args.cmd == "predict":
        rows, odds = backtest.load(conn, args.league)
        from datetime import datetime
        data = [(datetime.fromisoformat(r["kickoff"]).toordinal(), r["home"], r["away"], r["hg"], r["ag"]) for r in rows]
        cutoff = max(d[0] for d in data) - 4 * 365
        dc = DixonColes().fit([d for d in data if d[0] >= cutoff], max(d[0] for d in data))
        m = dc.matrix(args.home, args.away)
        lam, mu = dc.rates(args.home, args.away)
        print(f"{args.home} – {args.away} : buts attendus {lam:.2f} – {mu:.2f} (rho={dc.rho:+.2f})")
        for k, v in markets(m).items():
            print(f"  {k:10s} {v:6.1%}  (cote juste {1 / v:5.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
