# RT0705 – Vidéothèque : API REST

Tiers d'accès aux données de l'application de gestion de vidéothèque (projet RT0705).
API REST en Python / Flask : elle reçoit et renvoie du **JSON**, et stocke les
données dans une **base PostgreSQL**.

Le projet est réparti sur trois dépôts :

| Dépôt | Tiers |
|---|---|
| `RT0705-videotheque-serveur` | présentation (site web Flask / Jinja) |
| `RT0705-videotheque-api` (celui-ci) | accès aux données (API REST) |
| `RT0705-videotheque-data-base` | stockage (PostgreSQL : schéma et données) |

Le dossier de conception (fonctionnalités, acteurs, données, échanges,
architecture, description complète de l'API et formats JSON) est dans
[`docs/conception.md`](docs/conception.md).

## Lancer l'application complète

Cloner les trois dépôts côte à côte, puis depuis ce dépôt :

```bash
docker compose up -d --build
```

- site web : <http://localhost:8080>
- API : <http://localhost:5001/api/v1> (accessible depuis l'hôte uniquement)
- compte de démonstration : `demo@videotheque.local` / `videotheque`

Pour un usage autre que le TP, copier `.env.example` en `.env` et changer les
mots de passe et les clés. Si les dépôts voisins portent un autre nom de dossier,
renseigner `DB_CONTEXT` et `WEB_CONTEXT` dans `.env`.

Tout arrêter et effacer la base :

```bash
docker compose down -v
```

## Utiliser l'API

```bash
curl http://localhost:5001/api/v1/films?q=nolan
```

Les écritures demandent un jeton, obtenu à la connexion :

```bash
curl -X POST http://localhost:5001/api/v1/auth/connexion \
     -H 'Content-Type: application/json' \
     -d '{"email": "demo@videotheque.local", "mot_de_passe": "videotheque"}'
```

```bash
curl -X POST http://localhost:5001/api/v1/films \
     -H 'Content-Type: application/json' -H 'Authorization: Bearer <jeton>' \
     -d '{"titre": "Alien", "annee": 1979, "support": "physique", "genres": ["Science-fiction"]}'
```

| Méthode | URL (sous `/api/v1`) | Opération |
|---|---|---|
| GET | `/sante` | état de l'API et de la base |
| POST | `/auth/inscription`, `/auth/connexion` | création de compte, connexion |
| GET 🔒 | `/auth/moi` | utilisateur connecté |
| GET | `/films` | liste, recherche, filtres, tri, pagination |
| POST 🔒 | `/films` | ajout |
| GET | `/films/{id}` | détail |
| PUT 🔒, PATCH 🔒 | `/films/{id}` | remplacement, modification partielle |
| DELETE 🔒 | `/films/{id}` | suppression |
| GET, POST 🔒 | `/films/{id}/prets` | historique des prêts, nouveau prêt |
| GET | `/prets` | prêts (`?en_cours=true`) |
| POST 🔒 | `/prets/{id}/retour` | retour d'un film |
| DELETE 🔒 | `/prets/{id}` | suppression d'un prêt |
| GET, POST 🔒 | `/genres` | liste, création |
| DELETE 🔒 | `/genres/{id}` | suppression |
| GET | `/statistiques` | chiffres clés |

🔒 = en-tête `Authorization: Bearer <jeton>` requis.

## Tests

Script curl parcourant toutes les opérations sur l'application lancée
(il crée puis supprime ses propres données) :

```bash
scripts/test_api.sh
```

Tests automatiques (pytest), sur une base contenant le schéma **dont les tables
seront vidées** :

```bash
pip install -r requirements-dev.txt
```

```bash
DATABASE_URL_TEST=postgresql://utilisateur:motdepasse@localhost:5432/videotheque_test python -m pytest
```

## Organisation du code

| Fichier | Contenu |
|---|---|
| `app/__init__.py` | création de l'application Flask, sérialisation JSON |
| `app/db.py` | connexion PostgreSQL (une par requête) |
| `app/erreurs.py` | erreurs renvoyées en JSON |
| `app/auth.py` | comptes, jetons signés, décorateur `connexion_requise` |
| `app/films.py`, `genres.py`, `prets.py`, `statistiques.py` | les ressources |
| `Dockerfile`, `docker-compose.yml` | image de l'API, création coordonnée des conteneurs |

## Configuration

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | adresse de la base (`postgresql://utilisateur:motdepasse@hôte:5432/base`) |
| `SECRET_KEY` | clé de signature des jetons |
| `DUREE_JETON_S` | durée de validité d'un jeton en secondes (8 h par défaut) |
| `FLASK_DEBUG` | `1` : mode développement avec rechargement à chaud |

Le serveur de développement de Flask suffit pour le TP ; en production il
faudrait un serveur WSGI (gunicorn) et `FLASK_DEBUG=0`.
