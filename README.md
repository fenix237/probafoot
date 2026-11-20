# ProbaFoot (MVP – phase 0/1)

Bibliothèque standard Python uniquement (aucune dépendance). Voir `../ProbaFoot_Analyse_technique.md`.

```powershell
python -m probafoot ingest --leagues E0 F1          # télécharge + importe (idempotent, brut dans data/raw)
python -m probafoot ingest --leagues E0 --offline   # n'utilise que data/raw
python -m probafoot backtest --league E0 --test 2223 2324 2425
python -m probafoot predict --league E0 Arsenal Chelsea
python -m unittest discover -s tests -v
```

## API + front (sans build)
Python 3.12 recommandé pour FastAPI (`pip install fastapi uvicorn httpx`).
```powershell
python -m probafoot backtest --league E0 --test 2223 2324 2425   # crée un run (requis pour l'API)
python -m uvicorn probafoot.api:app --port 8000                    # puis ouvrir http://127.0.0.1:8000
```
- API `/v1` : `leagues`, `teams`, `runs`, `matches`, `matches/{id}`, `performance`, `predict` (docs : `/docs`).
- Front : `static/` (HTML/CSS/JS, thèmes clair/sombre, graphiques SVG avec survol), servi à la racine par l'API.
- `web/` : début d'un projet Next.js (installation npm interrompue par le réseau), non utilisé pour l'instant.

## Docker
Fichiers : `Dockerfile`, `docker-compose.yml`, `docker/refresh.sh`, `docker/Caddyfile`. Un volume `probafoot-data` garde la base SQLite et les CSV bruts.
```powershell
docker compose run --rm worker-once   # 1re fois : import + backtests (quelques minutes)
docker compose up -d                  # API + front sur http://127.0.0.1:8000, mise à jour quotidienne (service worker)
```
- Serveur public avec HTTPS automatique : `DOMAIN=mon-domaine.com docker compose --profile https up -d`
- Variables : `LEAGUES` (défaut `E0 F1`), `TEST_SEASONS` (défaut `2324 2425 2526`), `REFRESH_HOURS` (défaut 24).
- Le port 8000 n'est publié que sur 127.0.0.1 ; l'API tourne en utilisateur non privilégié, système de fichiers en lecture seule.
- Chaque mise à jour crée un nouveau backtest (les anciens restent consultables) ; l'API sert le plus récent.
- Non testé sur cette machine (Docker absent) : à valider au premier `docker compose build`.

## Capture des cotes (The Odds API)
Historique horodaté des cotes 1X2 de plusieurs bookmakers pour les matchs à venir : il ne se rattrape pas, donc à lancer tôt.
```powershell
$env:ODDS_API_KEY = "votre_clé"                      # clé gratuite : the-odds-api.com (jamais dans Git)
python -m probafoot capture --leagues E0 F1          # un passage (2 crédits pour 2 ligues, 1 région)
python -m probafoot capture-status                   # dernière capture, crédits restants, matchs à rapprocher
python -m probafoot capture --from-file reponse.json --leagues E0   # rejeu hors ligne, sans clé
```
- Docker : `docker compose --profile capture up -d` (clé via la variable `ODDS_API_KEY`, voir `.env.example`). Intervalle par défaut 240 min.
- Offre gratuite ≈ 500 crédits/mois : la capture se suspend sous `MIN_CREDITS` (30) crédits restants, sans appel réseau.
- Une ligne n'est écrite que si la cote change (`odds_ticks`) ; les noms d'équipes sont rapprochés de la base, et les cas incertains restent `NULL` (pas d'estimation inventée).
- API : `/v1/odds/upcoming`, `/v1/capture/status` ; front : onglet « À venir ».
- Variable `PROBAFOOT_DB` : chemin de la base pour toutes les commandes.

## Modèle ancré sur le marché
`anchor.py` : `p ∝ m^wm · d^wd · exp(b)` (m = cotes avant match sans marge, d = Dixon-Coles), calé par maximum de vraisemblance avec un a priori qui ramène vers « marché pur » (wm=1, wd=0, b=0). Le backtest le cale uniquement sur des prévisions passées dont le résultat est connu (saisons de calage, puis fenêtre croissante). Règle d'activation : il n'est utilisé que s'il bat `market_pre` (intervalle de confiance sous 0).

## Ce qui est implémenté
- `db.py` : SQLite, journal d'événements bitemporel (`occurred_at` ≤ `known_at`), cotes, prédictions immuables.
- `ingest.py` : Football-Data.co.uk -> matchs, événements `MATCH_RESULT`, cotes (PS, B365, Avg, Max ; avant match et clôture).
- `elo.py`, `dixoncoles.py` : modèles 1 et 2 (Dixon-Coles avec décroissance temporelle, matrice de scores, marchés 1X2 / O/U 2,5 / BTTS).
- `market.py` : retrait de marge (proportionnel, puissance), EV, Kelly fractionné plafonné, CLV.
- `backtest.py` : rejeu glissant « à la date » (un résultat n'est utilisé que si `known_at` < coup d'envoi), comparaison à la clôture, log-loss / RPS / Brier / ECE, IC bootstrap, simulation de paris.

## Limites connues
- `known_at` des résultats est approximé (coup d'envoi + 2 h 10).
- Saison 2018/19 absente si le téléchargement a échoué (relancer `ingest`).
- Pas encore : compositions/blessures, cotes horodatées multiples, direct, API/interface (phases 2+).
