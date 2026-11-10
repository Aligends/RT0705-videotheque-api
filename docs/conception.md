# RT0705 – Gestion d'une vidéothèque : dossier de conception

## 0. Lecture du sujet

Le sujet demande « une API REST agissant sur un stockage JSON » et précise que
« les communications entre les services se feront au format JSON ». L'ambiguïté
sur le stockage est levée de la façon suivante :

- **le stockage est une base de données relationnelle** (PostgreSQL) ;
- **tous les échanges entre services sont en JSON** : le site web et l'API ne
  se parlent qu'en JSON, et c'est l'API qui traduit ces objets JSON en requêtes SQL.

La base apporte ce qu'un fichier JSON ne garantit pas : contraintes d'intégrité,
accès concurrents, recherche et tri efficaces.

---

# Partie 1 – Modélisation

## 1.1 Fonctionnalités

Visiteur (sans compte) :

| # | Fonctionnalité |
|---|---|
| F1 | Consulter la liste des films, page par page |
| F2 | Rechercher un film (titre, titre original, réalisateur) |
| F3 | Filtrer par genre, support (physique / numérique), vu / à voir, année ; trier |
| F4 | Consulter la fiche détaillée d'un film et l'historique de ses prêts |
| F5 | Consulter les prêts (en cours ou tout l'historique) et les genres |
| F6 | Consulter les chiffres clés de la vidéothèque |
| F7 | Créer un compte, se connecter |

Utilisateur connecté (en plus) :

| # | Fonctionnalité |
|---|---|
| F8 | Ajouter un film (physique ou numérique) |
| F9 | Modifier un film, le marquer comme vu / à voir, le noter |
| F10 | Supprimer un film |
| F11 | Prêter un film physique à quelqu'un, puis enregistrer son retour |
| F12 | Créer ou supprimer un genre |
| F13 | Se déconnecter |

## 1.2 Acteurs et schéma général

| Acteur | Rôle | Charge |
|---|---|---|
| **Utilisateur** | Consulte et gère la collection depuis son navigateur | Saisie, lecture |
| **Client (navigateur)** | Affiche les pages HTML, envoie les formulaires | Rendu HTML/CSS |
| **Serveur de présentation** | Construit les pages, gère la session de l'utilisateur, traduit ses actions en appels à l'API | Logique d'interface, aucun accès aux données |
| **Serveur de données (API REST)** | Seul point d'accès aux données : validation, règles métier, authentification | Logique métier |
| **Base de données** | Conserve les données et garantit leur intégrité | Stockage |

```
 Utilisateur
     |
 [ Navigateur ] --(1) HTTP : pages HTML, formulaires--> [ Serveur de présentation ]
                                                              |
                                              (2) HTTP : requêtes et réponses JSON
                                                              v
                                                    [ API REST (données) ]
                                                              |
                                                       (3) SQL (TCP 5432)
                                                              v
                                                    [ Base PostgreSQL ]
```

Échanges :

1. navigateur ↔ présentation : requêtes HTTP (GET de pages, POST de formulaires),
   réponses HTML ; un cookie de session signé identifie l'utilisateur ;
2. présentation ↔ API : requêtes HTTP dont le corps et la réponse sont en JSON ;
   les écritures portent le jeton de l'utilisateur (`Authorization: Bearer`) ;
3. API ↔ base : requêtes SQL paramétrées.

## 1.3 Données du système

**Utilisateur**

| Champ | Type | Remarque |
|---|---|---|
| id | entier | identifiant |
| nom | chaîne (100) | obligatoire |
| email | chaîne (255) | obligatoire, unique, en minuscules |
| mot_de_passe | chaîne | empreinte ; jamais renvoyée par l'API |
| date_creation | date-heure | |

**Film**

| Champ | Type | Remarque |
|---|---|---|
| id | entier | identifiant |
| titre | chaîne (255) | obligatoire |
| titre_original | chaîne (255) | |
| annee | entier | 1888 à 2100 |
| realisateur | chaîne (255) | |
| duree_min | entier | durée en minutes, > 0 |
| synopsis | texte | |
| support | énumération | `physique` ou `numerique`, obligatoire |
| format | chaîne (30) | DVD, Blu-ray, VHS, MKV, MP4… |
| emplacement | chaîne (255) | étagère (physique) ou chemin du fichier (numérique) |
| note | entier | 0 à 10 |
| vu | booléen | faux par défaut |
| affiche_url | chaîne | adresse de l'affiche |
| genres | liste de chaînes | association n-n avec Genre |
| disponible | booléen | calculé : aucun prêt en cours |
| ajoute_par | entier | identifiant de l'utilisateur |
| date_ajout | date-heure | |

**Genre** : `id` (entier), `nom` (chaîne (50), unique sans tenir compte de la casse),
`nb_films` (entier, calculé).

**Prêt**

| Champ | Type | Remarque |
|---|---|---|
| id | entier | identifiant |
| film_id | entier | film prêté (support physique uniquement) |
| emprunteur | chaîne (100) | obligatoire |
| date_pret | date | aujourd'hui par défaut |
| date_retour_prevue | date | ≥ date_pret |
| date_retour | date | vide tant que le film n'est pas rendu |
| commentaire | texte | |
| en_cours, en_retard | booléens | calculés |

Règles : un film n'a qu'un seul prêt en cours ; seul un film physique se prête.

## 1.4 Modèle d'exécution et échanges

Modèle **requête / réponse synchrone**, sans état côté serveurs : chaque action
de l'utilisateur déclenche une requête HTTP vers le serveur de présentation,
qui émet un ou plusieurs appels à l'API et attend leurs réponses avant de
renvoyer la page.

Exemple – ajout d'un film (F8) :

```
Navigateur            Présentation                 API                      Base
    | POST /films/nouveau |                         |                        |
    |  (formulaire)       |                         |                        |
    |-------------------->| vérifie session + CSRF  |                        |
    |                     | formulaire -> objet JSON|                        |
    |                     | POST /api/v1/films      |                        |
    |                     |  + jeton, corps JSON    |                        |
    |                     |------------------------>| vérifie le jeton       |
    |                     |                         | valide les champs      |
    |                     |                         | INSERT films, genres   |
    |                     |                         |----------------------->|
    |                     |                         |<-----------------------|
    |                     |    201 + film en JSON   | COMMIT                 |
    |                     |<------------------------|                        |
    |  302 -> /films/42   |                         |                        |
    |<--------------------|                         |                        |
```

Opérations effectuées à la réception :

| Récepteur | Traitement |
|---|---|
| Présentation, requête du navigateur | contrôle de la session et du jeton CSRF, conversion du formulaire en JSON, appel(s) à l'API |
| API, requête de la présentation | contrôle du jeton (écritures), validation du JSON, règles métier, requêtes SQL dans une transaction, réponse JSON |
| Présentation, réponse de l'API | 2xx : rendu du gabarit ou redirection ; 400 : formulaire réaffiché avec les erreurs par champ ; 401 : retour à la page de connexion ; autre : page d'erreur |
| Navigateur, réponse | affichage de la page |

---

# Partie 2 – Implémentation

## 2.1 Architecture générale

Modèle Web 3 tiers, chaque service dans un conteneur Docker :

| Conteneur | Image | Rôle | Port |
|---|---|---|---|
| `web` | `python:3.12-slim` + Flask + requests | tiers présentation | 5000, publié sur l'hôte en **8080** |
| `api` | `python:3.12-slim` + Flask + psycopg | tiers d'accès aux données | 5000, publié sur `127.0.0.1:5001` pour les tests |
| `db` | `postgres:16-alpine` | stockage | 5432, **non publié** |

```
        hôte Docker
   :8080          127.0.0.1:5001
     |                 |
  +--+-----------------+------ réseau « presentation » ----+
  |  web  ---- JSON/HTTP ---->  api                         |
  +-----------------------------+---------------------------+
                                |
  +-----------------------------+- réseau « donnees » (interne)
  |                            api ---- SQL ---->  db        |
  +----------------------------------------------------------+
                                                   volume db_data
```

- Deux réseaux Docker : `web` ne peut pas joindre `db` ; le réseau `donnees` est
  interne (aucun accès depuis l'extérieur).
- Résolution de noms par le DNS de Docker (`http://api:5000`, `db:5432`).
- Volumes : `db_data` (données PostgreSQL) ; les dossiers `app/` des deux
  serveurs Flask sont partagés avec l'hôte (rechargement à chaud).
- `docker compose up` crée les trois conteneurs de façon coordonnée ; `api`
  attend que `db` soit prête (*healthcheck*).

Dépôts Git : `RT0705-videotheque-serveur` (présentation), `RT0705-videotheque-api`
(API) et `RT0705-videotheque-data-base` (schéma et image de la base).

## 2.2 Architecture du tiers données

### Hiérarchie des données

```
/api/v1
├── /sante
├── /auth
│   ├── /inscription
│   ├── /connexion
│   └── /moi
├── /films
│   └── /{id}
│       └── /prets
├── /genres
│   └── /{id}
├── /prets
│   └── /{id}
│       └── /retour
└── /statistiques
```

Schéma relationnel : voir `init/01_schema.sql` dans le dépôt de la base.

### Description de l'API

🔒 = jeton requis (`Authorization: Bearer <jeton>`).

| Méthode | URL | Opération | Succès | Erreurs |
|---|---|---|---|---|
| GET | `/sante` | état de l'API et de la base | 200 | 503 |
| POST | `/auth/inscription` | crée un compte, renvoie un jeton | 201 | 400, 409 |
| POST | `/auth/connexion` | vérifie les identifiants, renvoie un jeton | 200 | 400, 401 |
| GET 🔒 | `/auth/moi` | utilisateur du jeton | 200 | 401 |
| GET | `/films` | liste paginée, recherche, filtres, tri | 200 | 400 |
| POST 🔒 | `/films` | ajoute un film | 201 + `Location` | 400, 401 |
| GET | `/films/{id}` | détail d'un film | 200 | 404 |
| PUT 🔒 | `/films/{id}` | remplace le film | 200 | 400, 401, 404 |
| PATCH 🔒 | `/films/{id}` | modifie les champs fournis | 200 | 400, 401, 404 |
| DELETE 🔒 | `/films/{id}` | supprime le film (et ses prêts) | 204 | 401, 404 |
| GET | `/films/{id}/prets` | historique des prêts du film | 200 | 404 |
| POST 🔒 | `/films/{id}/prets` | prête le film | 201 | 400, 401, 404, 409 |
| GET | `/prets` | liste des prêts (`?en_cours=true`) | 200 | |
| POST 🔒 | `/prets/{id}/retour` | enregistre le retour | 200 | 400, 401, 404, 409 |
| DELETE 🔒 | `/prets/{id}` | supprime un prêt de l'historique | 204 | 401, 404 |
| GET | `/genres` | liste des genres et nombre de films | 200 | |
| POST 🔒 | `/genres` | crée un genre | 201 | 400, 401, 409 |
| DELETE 🔒 | `/genres/{id}` | supprime un genre (les films restent) | 204 | 401, 404 |
| GET | `/statistiques` | chiffres clés | 200 | |

Paramètres de `GET /films` : `q`, `genre`, `support`, `annee`, `vu`, `disponible`,
`tri` (`titre`, `annee`, `note`, `duree_min`, `date_ajout`), `ordre` (`asc`, `desc`),
`page`, `par_page` (1 à 100, 20 par défaut).

### Formats JSON

Film (réponse) :

```json
{
  "film": {
    "id": 2,
    "titre": "Blade Runner",
    "titre_original": null,
    "annee": 1982,
    "realisateur": "Ridley Scott",
    "duree_min": 117,
    "synopsis": "Los Angeles, 2019 : un ancien policier traque des réplicants en fuite.",
    "support": "physique",
    "format": "DVD",
    "emplacement": "Étagère A2",
    "note": 9,
    "vu": true,
    "affiche_url": null,
    "ajoute_par": 1,
    "date_ajout": "2026-11-10T16:40:12.345678+00:00",
    "genres": ["Science-fiction", "Thriller"],
    "disponible": true
  }
}
```

Film (corps de `POST`, `PUT`, `PATCH`) : les mêmes champs sans `id`, `ajoute_par`,
`date_ajout` ni `disponible`. Seuls `titre` et `support` sont obligatoires ;
les genres inconnus sont créés.

```json
{ "titre": "Alien", "annee": 1979, "support": "physique", "format": "DVD",
  "genres": ["Science-fiction", "Horreur"] }
```

Liste de films :

```json
{
  "films": [ { "id": 2, "titre": "Blade Runner", "…": "…" } ],
  "pagination": { "page": 1, "par_page": 20, "total": 8, "pages": 1 }
}
```

Genre :

```json
{ "genres": [ { "id": 8, "nom": "Science-fiction", "nb_films": 3 } ] }
```

Prêt (réponse) et corps de création :

```json
{
  "pret": {
    "id": 2, "film_id": 6, "film_titre": "Mad Max: Fury Road",
    "emprunteur": "Karim", "date_pret": "2026-11-05",
    "date_retour_prevue": "2026-11-19", "date_retour": null,
    "commentaire": "Prêté avec le boîtier collector",
    "en_cours": true, "en_retard": false
  }
}
```

```json
{ "emprunteur": "Karim", "date_pret": "2026-11-05",
  "date_retour_prevue": "2026-11-19", "commentaire": "…" }
```

Authentification (corps d'inscription, puis réponse d'inscription ou de connexion) :

```json
{ "nom": "Démo", "email": "demo@videotheque.local", "mot_de_passe": "videotheque" }
```

```json
{
  "jeton": "eyJpZCI6MX0.aRIc…",
  "expire_dans_s": 28800,
  "utilisateur": { "id": 1, "nom": "Démo", "email": "demo@videotheque.local",
                   "date_creation": "2026-11-10T16:40:12.345678+00:00" }
}
```

Statistiques :

```json
{
  "statistiques": {
    "nb_films": 8, "nb_physiques": 5, "nb_numeriques": 3, "nb_vus": 6, "nb_a_voir": 2,
    "duree_totale_min": 1038, "note_moyenne": 8.8, "nb_prets_en_cours": 1,
    "films_par_genre": [ { "genre": "Science-fiction", "nb_films": 3 } ]
  }
}
```

Erreur (toujours en JSON ; `details` donne le message de chaque champ invalide) :

```json
{
  "erreur": {
    "code": 400,
    "message": "Données invalides.",
    "details": { "titre": "Obligatoire.", "note": "Doit être un entier entre 0 et 10." }
  }
}
```

## 2.3 Architecture du tiers de présentation

Application Flask ; pages rendues par des gabarits Jinja. Fichiers : `app/__init__.py`
(routes), `app/api.py` (client JSON de l'API), `app/templates/` (gabarits),
`app/static/style.css`.

| Page (URL) | Gabarit | Opérations | Appels à l'API |
|---|---|---|---|
| `GET /` | `accueil.html` | chiffres clés, derniers ajouts, recherche | `GET /statistiques`, `GET /films?tri=date_ajout&ordre=desc&par_page=4` |
| `GET /films` | `films.html` | liste, recherche, filtres, tri, pagination | `GET /films?…`, `GET /genres` |
| `GET /films/{id}` | `film.html` | fiche du film, historique des prêts, boutons d'action | `GET /films/{id}`, `GET /films/{id}/prets` |
| `GET` `POST /films/nouveau` 🔒 | `film_form.html` | formulaire d'ajout puis traitement | `GET /genres`, `POST /films` |
| `GET` `POST /films/{id}/modifier` 🔒 | `film_form.html` | formulaire prérempli puis traitement | `GET /films/{id}`, `GET /genres`, `PUT /films/{id}` |
| `POST /films/{id}/vu` 🔒 | — (redirection) | bascule vu / à voir | `PATCH /films/{id}` |
| `POST /films/{id}/supprimer` 🔒 | — (redirection) | suppression après confirmation | `DELETE /films/{id}` |
| `GET` `POST /films/{id}/preter` 🔒 | `pret_form.html` | formulaire de prêt puis traitement | `GET /films/{id}`, `POST /films/{id}/prets` |
| `GET /prets` | `prets.html` | prêts en cours, ou tous (`?tous=1`) | `GET /prets[?en_cours=true]` |
| `POST /prets/{id}/retour` 🔒 | — (redirection) | enregistre le retour | `POST /prets/{id}/retour` |
| `GET` `POST /genres` | `genres.html` | liste ; ajout et suppression 🔒 | `GET /genres`, `POST /genres`, `DELETE /genres/{id}` |
| `GET` `POST /connexion` | `connexion.html` | ouvre la session (jeton conservé en session) | `POST /auth/connexion` |
| `GET` `POST /inscription` | `inscription.html` | crée le compte et ouvre la session | `POST /auth/inscription` |
| `POST /deconnexion` | — (redirection) | vide la session | aucun |
| erreurs | `erreur.html` | 400, 404, API indisponible… | — |

🔒 = réservé à un utilisateur connecté (sinon redirection vers `/connexion`).
Éléments communs : `base.html` (en-tête, navigation, messages) et `_macros.html`
(carte d'un film, champ de formulaire). Tous les formulaires portent un jeton CSRF.
