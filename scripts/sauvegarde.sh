#!/bin/sh
# Sauvegarde la base dans sauvegardes/videotheque-AAAAMMJJ-HHMMSS.dump
# (format compressé de pg_dump). La pile doit être démarrée.
# Usage : scripts/sauvegarde.sh
set -eu
cd "$(dirname "$0")/.."

mkdir -p sauvegardes
chmod 700 sauvegardes           # les sauvegardes contiennent des données personnelles
fichier="sauvegardes/videotheque-$(date +%Y%m%d-%H%M%S).dump"

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$fichier"
echo "Sauvegarde écrite dans $fichier ($(wc -c < "$fichier") octets)."
