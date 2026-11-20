#!/bin/sh
# Capture périodique des cotes. Variables : ODDS_API_KEY (obligatoire), LEAGUES, CAPTURE_MINUTES (défaut 180), MIN_CREDITS (défaut 30).
# Budget : offre gratuite ~500 crédits/mois ; 2 ligues x 1 région = 2 crédits par passage. Toutes les 3 h : ~480 crédits/mois (limite).
# Mettez CAPTURE_MINUTES=240 ou plus pour garder une marge.
set -u
LEAGUES="${LEAGUES:-E0 F1}"
CAPTURE_MINUTES="${CAPTURE_MINUTES:-240}"
MIN_CREDITS="${MIN_CREDITS:-30}"

if [ -z "${ODDS_API_KEY:-}" ]; then
  echo "[capture] ODDS_API_KEY absente : définissez-la dans un fichier .env (voir .env.example). Arrêt."
  exit 2
fi
while true; do
  echo "[capture] $(date -u +%FT%TZ)"
  python -m probafoot capture --leagues $LEAGUES --min-credits "$MIN_CREDITS" || echo "[capture] passage incomplet"
  sleep $((CAPTURE_MINUTES * 60))
done
