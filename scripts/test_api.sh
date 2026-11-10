#!/usr/bin/env bash
# Parcourt toutes les opérations de l'API avec curl et vérifie les codes HTTP.
# Usage : scripts/test_api.sh [URL de base]     (défaut : http://localhost:5001/api/v1)
set -u
API="${1:-http://localhost:5001/api/v1}"
ECHECS=0
CORPS=$(mktemp)
trap 'rm -f "$CORPS"' EXIT

# appel <code attendu> <méthode> <chemin> [corps JSON]
appel() {
    local attendu=$1 methode=$2 chemin=$3 code
    local args=(-s -o "$CORPS" -w '%{http_code}' -X "$methode" -H "Authorization: Bearer ${JETON:-}")
    [ $# -ge 4 ] && args+=(-H 'Content-Type: application/json' -d "$4")
    code=$(curl "${args[@]}" "$API$chemin")
    if [ "$code" = "$attendu" ]; then
        printf 'OK     %s %-7s %s\n' "$code" "$methode" "$chemin"
    else
        printf 'ECHEC  %s (attendu %s) %s %s\n       %s\n' "$code" "$attendu" "$methode" "$chemin" "$(cat "$CORPS")"
        ECHECS=$((ECHECS + 1))
    fi
}
# champ <expression Python sur d> : extrait une valeur de la dernière réponse
champ() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($1)" "$CORPS"; }

EMAIL="test-$(date +%s)-$$@exemple.fr"

appel 200 GET  /sante
appel 401 POST /films '{"titre":"Sans jeton","support":"physique"}'
appel 201 POST /auth/inscription "{\"nom\":\"Test curl\",\"email\":\"$EMAIL\",\"mot_de_passe\":\"motdepasse\"}"
appel 409 POST /auth/inscription "{\"nom\":\"Test curl\",\"email\":\"$EMAIL\",\"mot_de_passe\":\"motdepasse\"}"
appel 401 POST /auth/connexion   "{\"email\":\"$EMAIL\",\"mot_de_passe\":\"mauvais\"}"
appel 200 POST /auth/connexion   "{\"email\":\"$EMAIL\",\"mot_de_passe\":\"motdepasse\"}"
JETON=$(champ 'd["jeton"]')
appel 200 GET  /auth/moi

appel 400 POST /films '{"titre":"","support":"betamax"}'
appel 201 POST /films '{"titre":"Film de test curl","annee":1999,"support":"physique","format":"DVD","genres":["Genre de test curl"]}'
FILM=$(champ 'd["film"]["id"]')
appel 200 GET    "/films/$FILM"
appel 200 GET    "/films?q=test%20curl&support=physique&tri=annee&ordre=desc&par_page=5"
appel 200 PATCH  "/films/$FILM" '{"vu":true,"note":7}'
appel 200 PUT    "/films/$FILM" '{"titre":"Film de test curl (modifié)","support":"physique","genres":["Genre de test curl"]}'
appel 404 GET    /films/99999999

appel 200 GET    /genres
GENRE=$(champ 'next(g["id"] for g in d["genres"] if g["nom"] == "Genre de test curl")')
appel 409 POST   /genres '{"nom":"genre de test curl"}'

appel 201 POST   "/films/$FILM/prets" '{"emprunteur":"Camille","date_retour_prevue":"2099-01-01"}'
PRET=$(champ 'd["pret"]["id"]')
appel 409 POST   "/films/$FILM/prets" '{"emprunteur":"Karim"}'
appel 200 GET    "/films/$FILM/prets"
appel 200 GET    "/prets?en_cours=true"
appel 200 POST   "/prets/$PRET/retour"
appel 409 POST   "/prets/$PRET/retour"
appel 200 GET    /statistiques

# nettoyage
appel 204 DELETE "/prets/$PRET"
appel 204 DELETE "/films/$FILM"
appel 404 DELETE "/films/$FILM"
appel 204 DELETE "/genres/$GENRE"

echo
if [ "$ECHECS" -eq 0 ]; then echo "Tous les appels ont réussi."; else echo "$ECHECS appel(s) en échec."; exit 1; fi
