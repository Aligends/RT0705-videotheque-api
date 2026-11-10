#!/bin/sh
# Démarrage du conteneur de l'API : crée l'administrateur initial s'il
# n'existe pas encore (ADMIN_EMAIL, ADMIN_MOT_DE_PASSE), puis lance le serveur.
set -e
flask --app app init-admin
exec "$@"
