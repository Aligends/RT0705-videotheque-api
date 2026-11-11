#!/bin/sh
# Crée le fichier .env avec des secrets aléatoires. Sans effet s'il existe déjà.
# Usage : scripts/init-env.sh
set -eu
cd "$(dirname "$0")/.."

if [ -e .env ]; then
    echo ".env existe déjà : rien n'est modifié." >&2
    exit 0
fi

# alea N : N octets aléatoires, écrits en hexadécimal
alea() { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

mot_de_passe_admin="$(alea 3)-$(alea 3)-$(alea 3)-$(alea 3)"

umask 077       # fichier lisible par son seul propriétaire
cat > .env <<FIN
# Généré par scripts/init-env.sh. Ne pas committer, ne pas partager.
POSTGRES_PASSWORD=$(alea 24)
API_DB_PASSWORD=$(alea 24)
API_SECRET_KEY=$(alea 32)
WEB_SECRET_KEY=$(alea 32)

ADMIN_EMAIL=admin@videotheque.local
ADMIN_MOT_DE_PASSE=$mot_de_passe_admin

INSCRIPTION=validation
DONNEES_DEMO=1
WEB_PORT=8080
NOM_DU_SITE=localhost
FIN

cat <<FIN
Fichier .env créé.

Compte administrateur du site (créé au premier démarrage) :
    adresse      : admin@videotheque.local
    mot de passe : $mot_de_passe_admin
Changez ce mot de passe depuis la page « Mon compte » après la première connexion.

Lancement : docker compose up -d --build
FIN
