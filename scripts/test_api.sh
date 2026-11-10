#!/usr/bin/env bash
# Parcourt les opérations de l'API avec curl et vérifie les codes HTTP.
# La pile doit être démarrée. Le script crée ses propres données (un compte,
# un film, un genre, un prêt) puis les supprime.
#
# Usage : scripts/test_api.sh [URL de base]     (défaut : http://localhost:5001/api/v1)
# L'adresse et le mot de passe de l'administrateur sont lus dans .env
# (ou dans les variables ADMIN_EMAIL et ADMIN_MOT_DE_PASSE).
set -u
cd "$(dirname "$0")/.."
API="${1:-http://localhost:5001/api/v1}"

if [ -r .env ]; then
    : "${ADMIN_EMAIL:=$(sed -n 's/^ADMIN_EMAIL=//p' .env)}"
    : "${ADMIN_MOT_DE_PASSE:=$(sed -n 's/^ADMIN_MOT_DE_PASSE=//p' .env)}"
fi
: "${ADMIN_EMAIL:?ADMIN_EMAIL introuvable (fichier .env ou variable)}"
: "${ADMIN_MOT_DE_PASSE:?ADMIN_MOT_DE_PASSE introuvable (fichier .env ou variable)}"

ECHECS=0
JETON=""
CORPS=$(mktemp)
trap 'rm -f "$CORPS"' EXIT

# appel <code attendu> <méthode> <chemin> [corps JSON]
appel() {
    local attendu=$1 methode=$2 chemin=$3 code
    local args=(-s -o "$CORPS" -w '%{http_code}' -X "$methode")
    [ -n "$JETON" ] && args+=(-H "Authorization: Bearer $JETON")
    [ $# -ge 4 ] && args+=(-H 'Content-Type: application/json' -d "$4")
    code=$(curl "${args[@]}" "$API$chemin")
    if [ "$code" = "$attendu" ]; then
        printf 'OK     %s %-6s %s\n' "$code" "$methode" "$chemin"
    else
        printf 'ECHEC  %s (attendu %s) %s %s\n       %s\n' \
               "$code" "$attendu" "$methode" "$chemin" "$(cat "$CORPS")"
        ECHECS=$((ECHECS + 1))
    fi
}
# champ <expression Python sur d> : extrait une valeur de la dernière réponse
champ() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($1)" "$CORPS"; }

EMAIL="test-$(date +%s)-$$@exemple.fr"
MDP="phrase-de-test-curl"
FILM_JSON='{"titre":"Film de test curl","annee":1999,"support":"physique","format":"DVD","genres":["Genre de test curl"]}'

echo "--- sans jeton"
appel 200 GET  /sante
appel 200 GET  /films
appel 200 GET  /statistiques
appel 401 POST /films "$FILM_JSON"
appel 401 GET  /prets
appel 401 GET  /export

echo "--- administrateur"
appel 401 POST /auth/connexion "{\"email\":\"$ADMIN_EMAIL\",\"mot_de_passe\":\"mauvais-mot-de-passe\"}"
appel 200 POST /auth/connexion "{\"email\":\"$ADMIN_EMAIL\",\"mot_de_passe\":\"$ADMIN_MOT_DE_PASSE\"}"
ADMIN=$(champ 'd["jeton"]')
JETON=$ADMIN
appel 200 GET  /auth/moi
appel 200 GET  /utilisateurs

echo "--- inscription d'un membre"
JETON=""
appel 400 POST /auth/inscription "{\"nom\":\"Test curl\",\"email\":\"$EMAIL\",\"mot_de_passe\":\"court\"}"
appel 201 POST /auth/inscription "{\"nom\":\"Test curl\",\"email\":\"$EMAIL\",\"mot_de_passe\":\"$MDP\"}"
MEMBRE_ID=$(champ 'd["utilisateur"]["id"]')
if [ "$(champ 'd["en_attente"]')" = "True" ]; then
    # mode « validation » : le compte doit être activé par un administrateur
    appel 403 POST /auth/connexion "{\"email\":\"$EMAIL\",\"mot_de_passe\":\"$MDP\"}"
    JETON=$ADMIN
    appel 200 PATCH "/utilisateurs/$MEMBRE_ID" '{"actif":true}'
    JETON=""
fi
appel 409 POST /auth/inscription "{\"nom\":\"Test curl\",\"email\":\"$EMAIL\",\"mot_de_passe\":\"$MDP\"}"
appel 200 POST /auth/connexion "{\"email\":\"$EMAIL\",\"mot_de_passe\":\"$MDP\"}"
MEMBRE=$(champ 'd["jeton"]')
JETON=$MEMBRE
appel 200 GET  /auth/moi
appel 403 GET  /utilisateurs
appel 403 GET  /journal

echo "--- films"
appel 400 POST /films '{"titre":"","support":"betamax","role":"admin"}'
appel 201 POST /films "$FILM_JSON"
FILM=$(champ 'd["film"]["id"]')
appel 200 GET    "/films/$FILM"
appel 200 GET    "/films?q=test%20curl&support=physique&tri=note&ordre=desc&par_page=5"
appel 200 PATCH  "/films/$FILM" '{"duree_min":95}'
appel 200 PUT    "/films/$FILM" '{"titre":"Film de test curl (modifié)","support":"physique","genres":["Genre de test curl"]}'
appel 404 GET    /films/99999999

echo "--- avis"
appel 201 PUT    "/films/$FILM/avis" '{"note":8,"commentaire":"Vu pendant les tests."}'
appel 200 PUT    "/films/$FILM/avis" '{"note":9}'
appel 400 PUT    "/films/$FILM/avis" '{"note":11}'
appel 200 GET    "/films/$FILM/avis"
appel 200 GET    "/films?vu=true"
appel 204 DELETE "/films/$FILM/avis"

echo "--- genres"
appel 200 GET    /genres
GENRE=$(champ 'next(g["id"] for g in d["genres"] if g["nom"] == "Genre de test curl")')
appel 409 POST   /genres '{"nom":"genre de test curl"}'
appel 403 DELETE "/genres/$GENRE"

echo "--- prêts"
appel 201 POST   "/films/$FILM/prets" '{"emprunteur":"Camille","date_retour_prevue":"2099-01-01"}'
PRET=$(champ 'd["pret"]["id"]')
appel 409 POST   "/films/$FILM/prets" '{"emprunteur":"Karim"}'
appel 200 GET    "/films/$FILM/prets"
appel 200 GET    "/prets?en_cours=true"
appel 200 POST   "/prets/$PRET/retour"
appel 409 POST   "/prets/$PRET/retour"
appel 403 DELETE "/prets/$PRET"

echo "--- export et import"
appel 200 GET    /export
appel 403 POST   /import "{\"films\":[$FILM_JSON]}"
JETON=$ADMIN
appel 400 POST   /import '{"films":[{"titre":"","support":"x"}]}'
appel 200 POST   /import '{"films":[{"titre":"Film importé par test curl","support":"numerique"}]}'
appel 200 GET    "/films?q=import%C3%A9%20par%20test%20curl"
IMPORTE=$(champ 'd["films"][0]["id"]')
appel 200 GET    /journal

echo "--- nettoyage par l'administrateur"
appel 204 DELETE "/films/$IMPORTE"
appel 204 DELETE "/prets/$PRET"
appel 204 DELETE "/films/$FILM"
appel 404 DELETE "/films/$FILM"
appel 204 DELETE "/genres/$GENRE"

echo "--- déconnexion : le jeton est révoqué"
JETON=$MEMBRE
appel 204 POST   /auth/deconnexion
appel 401 GET    /auth/moi
JETON=$ADMIN
appel 204 DELETE "/utilisateurs/$MEMBRE_ID"
appel 204 POST   /auth/deconnexion

echo
if [ "$ECHECS" -eq 0 ]; then echo "Tous les appels ont réussi."; else echo "$ECHECS appel(s) en échec."; exit 1; fi
