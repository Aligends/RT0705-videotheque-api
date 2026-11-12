# RT0705 – Vidéothèque : API REST

Tiers d'accès aux données de l'application de gestion de vidéothèque (projet RT0705).
API REST en Python / Flask : elle reçoit et renvoie du **JSON**, et stocke les
données dans une **base PostgreSQL**. Ce dépôt porte aussi l'orchestration
Docker de l'application complète.

| Dépôt | Tiers |
|---|---|
| `RT0705-videotheque-serveur` | présentation (site web Flask / Jinja) |
| `RT0705-videotheque-api` (celui-ci) | accès aux données (API REST), orchestration, scripts |
| `RT0705-videotheque-data-base` | stockage (PostgreSQL : schéma, rôles, données de démonstration) |

```
navigateur --HTTP(S)--> site web --JSON/HTTP--> API REST --SQL--> PostgreSQL
```

## Démarrage

Cloner les trois dépôts côte à côte, puis, depuis ce dépôt :

```bash
scripts/init-env.sh
```

```bash
docker compose up -d --build
```

Le premier script crée le fichier `.env` avec des secrets aléatoires et affiche
le mot de passe de l'administrateur (`admin@videotheque.local`). Il n'existe
aucun mot de passe par défaut : sans `.env`, `docker compose` refuse de démarrer.

- site web : <http://localhost:8080>
- API : <http://localhost:5001/api/v1> (depuis la machine hôte uniquement)

Tout arrêter en conservant les données, ou en les effaçant :

```bash
docker compose down
```

```bash
docker compose down -v
```

## Trois façons de lancer l'application

| Mode | Commande | Ce qui change |
|---|---|---|
| TP (défaut) | `docker compose up -d --build` | site en HTTP sur le port 8080, API sur `127.0.0.1:5001` |
| HTTPS | `docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build` | un proxy Caddy chiffre les échanges (ports 80 et 443) ; ni le site ni l'API ne sont publiés directement |
| Développement | `docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.dev.yml up --build` | serveur Flask avec débogueur et rechargement à chaud, inscriptions ouvertes, pages de test `/tp` |

En HTTPS, indiquer dans `.env` le nom ou l'adresse IP tapés dans le navigateur
(`NOM_DU_SITE=192.168.1.20`). Le certificat vient de l'autorité interne de
Caddy : le navigateur affiche un avertissement tant qu'elle n'est pas installée
sur le poste.

Le mode développement ne doit servir que sur une machine de développement : le
débogueur de Flask permet d'exécuter du code sur le serveur.

## Comptes et droits

| Profil | Droits |
|---|---|
| Visiteur | consulter les films, les avis, les genres et les statistiques |
| Membre | ajouter des films, modifier ou supprimer les siens, donner son avis, gérer les prêts, exporter le catalogue |
| Administrateur | tout modifier, importer un catalogue, gérer les comptes, lire le journal d'audit |

Par défaut (`INSCRIPTION=validation`), un compte créé depuis le site reste en
attente jusqu'à ce qu'un administrateur l'active (page « Comptes »).
`INSCRIPTION=ouverte` rend les comptes utilisables tout de suite,
`INSCRIPTION=fermee` interdit les inscriptions.

Mot de passe oublié (la commande demande le nouveau mot de passe) :

```bash
docker compose exec api flask --app app mot-de-passe adresse@exemple.fr
```

## Utiliser l'API

La référence complète (routes, droits, formats JSON, erreurs) est dans
[`docs/api.md`](docs/api.md).

```bash
curl "http://localhost:5001/api/v1/films?q=nolan&tri=note&ordre=desc"
```

Les écritures demandent un jeton, obtenu à la connexion :

```bash
curl -X POST http://localhost:5001/api/v1/auth/connexion \
     -H 'Content-Type: application/json' \
     -d '{"email": "admin@videotheque.local", "mot_de_passe": "<mot de passe>"}'
```

```bash
curl -X POST http://localhost:5001/api/v1/films \
     -H 'Content-Type: application/json' -H 'Authorization: Bearer <jeton>' \
     -d '{"titre": "Alien", "annee": 1979, "support": "physique", "genres": ["Science-fiction"]}'
```

## Sécurité

| Sujet | Mesure |
|---|---|
| Secrets | aucun secret dans le code ni valeur par défaut ; `.env` généré, lisible par son seul propriétaire ; l'API refuse de démarrer sans clé d'au moins 32 caractères |
| Mots de passe | empreinte scrypt ; 10 caractères au minimum, mots de passe courants refusés |
| Connexion | verrouillage de l'adresse après 5 échecs en 15 minutes ; même réponse et même temps de calcul que le compte existe ou non |
| Jetons | signés HMAC-SHA256, valables 4 h, révoqués à la déconnexion, au changement de mot de passe ou de rôle, à la désactivation |
| Droits | rôles vérifiés par l'API à chaque requête ; un membre ne modifie que ses films ; prêts et emplacements réservés aux utilisateurs connectés |
| Entrées | liste blanche des champs, types et longueurs contrôlés, requêtes SQL toujours paramétrées, 1 Mo au plus par requête |
| Base | l'API utilise un compte PostgreSQL sans droit de structure ; journal d'audit en ajout seul ; 5 secondes au plus par requête SQL |
| Conteneurs | utilisateur non root, système de fichiers en lecture seule, aucune capacité Linux, base sur un réseau interne non publié |
| Traçabilité | journal d'audit des opérations sensibles et des échecs de connexion |

## Exploitation

Sauvegarder la base (fichier dans `sauvegardes/`), puis la restaurer :

```bash
scripts/sauvegarde.sh
```

```bash
scripts/restauration.sh sauvegardes/videotheque-AAAAMMJJ-HHMMSS.dump
```

Journaux des services :

```bash
docker compose logs -f api web
```

Le schéma n'est créé qu'à la première initialisation du volume de la base.
Après une modification du schéma, il faut repartir d'une base neuve
(`docker compose down -v`), en sauvegardant les données avant si besoin.

## Tests

Script curl : 57 appels sur l'application lancée, avec vérification des codes
HTTP. Il crée puis supprime ses propres données.

```bash
scripts/test_api.sh
```

Parcours complet du site dans un navigateur (56 contrôles), sur une base
neuve ; demande Node.js et Playwright, voir l'en-tête du fichier :

```bash
node tests/navigateur/parcours.js http://localhost:8080 "<mot de passe admin>" /tmp/captures
```

Tests automatiques (pytest), sur une base contenant le schéma et **dont les
tables seront vidées** :

```bash
pip install -r requirements-dev.txt
```

```bash
DATABASE_URL_TEST=postgresql://utilisateur:motdepasse@localhost:5432/videotheque_test python -m pytest
```

## Organisation du dépôt

| Fichier | Contenu |
|---|---|
| `app/__init__.py` | création de l'application, configuration, en-têtes de sécurité |
| `app/auth.py` | comptes, jetons, verrouillage, contrôle des rôles |
| `app/validation.py` | contrôle des données reçues |
| `app/films.py`, `avis.py`, `genres.py`, `prets.py` | ressources du catalogue |
| `app/utilisateurs.py`, `journal.py`, `audit.py` | administration des comptes, journal d'audit |
| `app/echanges.py`, `statistiques.py` | import / export JSON, chiffres clés |
| `app/cli.py` | commandes `init-admin` et `mot-de-passe` |
| `app/db.py`, `erreurs.py` | connexion PostgreSQL, erreurs au format JSON |
| `docker-compose*.yml`, `deploiement/Caddyfile` | création coordonnée des conteneurs, proxy HTTPS |
| `Dockerfile`, `demarrage.sh`, `gunicorn.conf.py` | image de l'API |
| `scripts/` | génération de `.env`, sauvegarde, restauration, test de l'API |
| `tests/` | tests automatiques |

## Configuration

Variables du fichier `.env` (lues par `docker compose`) :

| Variable | Rôle |
|---|---|
| `POSTGRES_PASSWORD` | mot de passe du propriétaire de la base (administration, sauvegardes) |
| `API_DB_PASSWORD` | mot de passe du compte SQL restreint utilisé par l'API |
| `API_SECRET_KEY`, `WEB_SECRET_KEY` | clés de signature des jetons et du cookie de session |
| `ADMIN_EMAIL`, `ADMIN_MOT_DE_PASSE` | premier administrateur, créé au démarrage s'il n'existe pas |
| `INSCRIPTION` | `validation` (défaut), `ouverte` ou `fermee` |
| `DONNEES_DEMO` | `1` : charge les données de démonstration à la création de la base |
| `WEB_PORT` | port du site en HTTP (8080) |
| `NOM_DU_SITE` | nom ou adresse IP du site en HTTPS |

Variables lues par l'API elle-même : `DATABASE_URL`, `SECRET_KEY`, `INSCRIPTION`,
`DUREE_JETON_S` (14400), `MAX_ECHECS_CONNEXION` (5), `FENETRE_ECHECS_S` (900).
