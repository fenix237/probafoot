#!/bin/sh
# Met à jour les données puis relance les backtests, en boucle (une fois par jour par défaut).
# Variables : LEAGUES (ex. "E0 F1"), TEST_SEASONS (ex. "2324 2425 2526"), REFRESH_HOURS (défaut 24), RUN_ONCE=1 pour un seul passage.
set -u
LEAGUES="${LEAGUES:-E0 F1}"
TEST_SEASONS="${TEST_SEASONS:-2324 2425 2526}"
REFRESH_HOURS="${REFRESH_HOURS:-24}"

while true; do
  echo "[refresh] $(date -u +%FT%TZ) import des données : $LEAGUES"
  python -m probafoot ingest --leagues $LEAGUES || echo "[refresh] import partiel (source indisponible ?), on continue avec ce qui est en base"
  for lg in $LEAGUES; do
    echo "[refresh] backtest $lg sur $TEST_SEASONS"
    python -m probafoot backtest --league "$lg" --test $TEST_SEASONS > /dev/null || echo "[refresh] backtest $lg en échec"
  done
  echo "[refresh] terminé"
  [ "${RUN_ONCE:-0}" = "1" ] && exit 0
  sleep $((REFRESH_HOURS * 3600))
done
