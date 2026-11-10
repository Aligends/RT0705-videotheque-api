#!/bin/sh
# Restaure la base à partir d'une sauvegarde produite par scripts/sauvegarde.sh.
# ATTENTION : le contenu actuel de la base est remplacé.
# Usage : scripts/restauration.sh sauvegardes/videotheque-AAAAMMJJ-HHMMSS.dump
set -eu
fichier="${1:?Usage : scripts/restauration.sh <fichier.dump>}"
[ -r "$fichier" ] || { echo "Fichier illisible : $fichier" >&2; exit 1; }
fichier="$(cd "$(dirname "$fichier")" && pwd)/$(basename "$fichier")"
cd "$(dirname "$0")/.."

printf 'Remplacer le contenu de la base par %s ? [o/N] ' "$fichier"
read -r reponse
[ "$reponse" = "o" ] || { echo "Abandon."; exit 1; }

docker compose stop api web
docker compose exec -T db sh -c \
    'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --single-transaction' < "$fichier"
docker compose start api web
echo "Base restaurée."
