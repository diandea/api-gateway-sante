#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Tests de bout en bout À TRAVERS KONG (pile Docker démarrée).
#   cd /vagrant && bash tests/e2e_kong.sh
#
# Scénarios : réponse complète, valeurs réellement nulles, structure inconnue,
# erreur partielle (500), délai dépassé, service arrêté, service principal
# arrêté, identifiant de corrélation généré par Kong.
# ---------------------------------------------------------------------------
set -u
BASE_URL="${BASE_URL:-http://localhost:8000}"
STOP_CMD="${STOP_CMD:-docker compose stop}"     # + nom du service
START_CMD="${START_CMD:-docker compose start}"
DASH="$BASE_URL/api/v1/dashboard/structures"
PASS=0; FAIL=0
TMP=$(mktemp)

chaos() {  # chaos <port> <mode> [delay]
  curl -s -X POST "http://localhost:$1/_chaos" -H 'Content-Type: application/json' \
       -d "{\"mode\":\"$2\",\"delay\":${3:-5}}" > /dev/null
}
reset_chaos() { for p in 9001 9002 9003; do chaos $p normal; done; }

call() {   # call <id> -> remplit HTTP, TIME, BODY (fichier $TMP)
  read -r HTTP TIME < <(curl -s -D "$TMP.h" -o "$TMP" -w "%{http_code} %{time_total}" \
                         -H "X-Correlation-ID: e2e-$RANDOM" "$DASH/$1")
}
jqv() { jq -r "$1" "$TMP"; }

check() {  # check "<description>" <condition-bash>
  if eval "$2"; then echo "  ✔ $1"; PASS=$((PASS+1));
  else echo "  ✘ $1   (obtenu : $3)"; FAIL=$((FAIL+1)); fi
}

trap 'reset_chaos; rm -f "$TMP" "$TMP.h"' EXIT
reset_chaos

echo "1) Réponse complète — GET /dashboard/structures/1"
call 1
check "HTTP 200"                     '[ "$HTTP" = 200 ]' "$HTTP"
check "statut_agregation = COMPLET"  '[ "$(jqv .statut_agregation)" = COMPLET ]' "$(jqv .statut_agregation)"
check "3 sources DISPONIBLE"         '[ "$(jqv "[.sources[].statut]|unique|join(\",\")")" = DISPONIBLE ]' "$(jqv "[.sources[].statut]|join(\",\")")"

echo "2) Données réellement nulles — structure 5 (aucun patient, aucun indicateur)"
call 5
check "HTTP 200 et COMPLET"          '[ "$HTTP" = 200 ] && [ "$(jqv .statut_agregation)" = COMPLET ]' "$HTTP $(jqv .statut_agregation)"
check "patients.total = 0 (zéro réel)" '[ "$(jqv .patients.donnees.total)" = 0 ]' "$(jqv .patients.donnees.total)"
check "indicateurs ABSENT (≠ INDISPONIBLE)" '[ "$(jqv .indicateurs.statut)" = ABSENT ]' "$(jqv .indicateurs.statut)"

echo "3) Structure inexistante — GET /dashboard/structures/999"
call 999
check "HTTP 404"                     '[ "$HTTP" = 404 ]' "$HTTP"

echo "4) Erreur partielle — API patients en erreur 500"
chaos 9002 error; call 1; chaos 9002 normal
check "HTTP 200 et PARTIEL"          '[ "$HTTP" = 200 ] && [ "$(jqv .statut_agregation)" = PARTIEL ]' "$HTTP $(jqv .statut_agregation)"
check "patients INDISPONIBLE / UPSTREAM_ERROR" '[ "$(jqv .patients.erreur.code)" = UPSTREAM_ERROR ]' "$(jqv .patients.erreur.code)"

echo "5) Délai dépassé — API indicateurs lente (5 s)"
chaos 9003 slow 5; call 1; chaos 9003 normal
check "indicateurs TIMEOUT"          '[ "$(jqv .indicateurs.erreur.code)" = TIMEOUT ]' "$(jqv .indicateurs.erreur.code)"
check "réponse en moins de 3 s"      'awk "BEGIN{exit !($TIME < 3)}"' "${TIME}s"

echo "6) Indisponibilité — API indicateurs arrêtée"
$STOP_CMD indicateurs > /dev/null 2>&1; call 1
check "PARTIEL / SERVICE_UNREACHABLE" '[ "$(jqv .indicateurs.erreur.code)" = SERVICE_UNREACHABLE ]' "$(jqv .indicateurs.erreur.code)"
$START_CMD indicateurs > /dev/null 2>&1

echo "7) Service principal arrêté — API structures arrêtée"
$STOP_CMD structures > /dev/null 2>&1; call 1
check "HTTP 503"                     '[ "$HTTP" = 503 ]' "$HTTP"
$START_CMD structures > /dev/null 2>&1

echo "8) Identifiant de corrélation généré par Kong (aucun en-tête envoyé)"
CID=$(curl -s -D - -o /dev/null "$DASH/1" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-correlation-id"{print $2}')
check "en-tête X-Correlation-ID présent" '[ -n "$CID" ]' "vide"
echo "     -> $CID   (cherchez-le : docker compose logs | grep $CID)"

echo
echo "Résultat : $PASS réussis, $FAIL échoués"
[ "$FAIL" -eq 0 ]
