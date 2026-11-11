# Référence de l'API

Toutes les routes sont sous `/api/v1`. Les corps de requête et les réponses
sont en JSON (`Content-Type: application/json`), y compris les erreurs.

## Authentification et rôles

La connexion renvoie un jeton signé, valable 4 heures, à envoyer dans
l'en-tête `Authorization: Bearer <jeton>`. Un jeton cesse de fonctionner dès
que le compte se déconnecte, change de mot de passe, change de rôle ou est
désactivé.

| Profil | Peut… |
|---|---|
| Visiteur (sans jeton) | consulter les films, les avis, les genres et les statistiques ; créer un compte ; se connecter |
| Membre | en plus : ajouter un film, modifier ou supprimer **les films qu'il a ajoutés**, donner son avis, gérer les prêts, créer un genre, exporter le catalogue, gérer son compte |
| Administrateur | en plus : modifier ou supprimer tous les films, supprimer un genre, un prêt ou l'avis d'un autre, importer un catalogue, gérer les comptes, lire le journal d'audit |

Un jeton invalide ou expiré donne toujours `401`, même sur une route publique.

## Routes

Accès : **P** public, **M** membre (jeton requis), **A** administrateur,
**M\*** membre qui a ajouté le film, ou administrateur.

| Méthode | URL | Accès | Opération | Succès | Erreurs |
|---|---|---|---|---|---|
| GET | `/sante` | P | état de l'API et de la base | 200 | 503 |
| POST | `/auth/inscription` | P | crée un compte « membre » | 201 | 400, 403, 409 |
| POST | `/auth/connexion` | P | vérifie les identifiants, renvoie un jeton | 200 | 401, 403, 429 |
| GET | `/auth/moi` | M | compte du jeton | 200 | 401 |
| PATCH | `/auth/moi` | M | modifie son nom | 200 | 400, 401 |
| POST | `/auth/mot-de-passe` | M | change son mot de passe, renvoie un nouveau jeton | 200 | 400, 401 |
| POST | `/auth/deconnexion` | M | révoque tous les jetons du compte | 204 | 401 |
| GET | `/films` | P | liste paginée, recherche, filtres, tri | 200 | 400, 401 |
| POST | `/films` | M | ajoute un film | 201 + `Location` | 400, 401 |
| GET | `/films/{id}` | P | détail d'un film | 200 | 404 |
| PUT | `/films/{id}` | M\* | remplace le film | 200 | 400, 401, 403, 404 |
| PATCH | `/films/{id}` | M\* | modifie les champs fournis | 200 | 400, 401, 403, 404 |
| DELETE | `/films/{id}` | M\* | supprime le film, ses avis et ses prêts | 204 | 401, 403, 404 |
| GET | `/films/{id}/avis` | P | avis de tous les utilisateurs sur le film | 200 | 404 |
| PUT | `/films/{id}/avis` | M | crée ou remplace son avis (« j'ai vu ce film ») | 201 ou 200 | 400, 401, 404 |
| DELETE | `/films/{id}/avis` | M | retire son avis | 204 | 401, 404 |
| DELETE | `/films/{id}/avis/{utilisateur_id}` | A | modération : supprime l'avis d'un utilisateur | 204 | 401, 403, 404 |
| GET | `/films/{id}/prets` | M | historique des prêts du film | 200 | 401, 404 |
| POST | `/films/{id}/prets` | M | prête le film | 201 | 400, 401, 404, 409 |
| GET | `/prets` | M | liste paginée des prêts | 200 | 400, 401 |
| POST | `/prets/{id}/retour` | M | enregistre le retour | 200 | 400, 401, 404, 409 |
| DELETE | `/prets/{id}` | A | retire un prêt de l'historique | 204 | 401, 403, 404 |
| GET | `/genres` | P | genres et nombre de films | 200 | |
| POST | `/genres` | M | crée un genre | 201 | 400, 401, 409 |
| DELETE | `/genres/{id}` | A | supprime un genre (les films restent) | 204 | 401, 403, 404 |
| GET | `/statistiques` | P | chiffres clés (et ceux du compte, avec un jeton) | 200 | |
| GET | `/export` | M | catalogue complet, au format d'échange | 200 | 401 |
| POST | `/import` | A | ajoute les films d'un fichier d'export | 200 | 400, 401, 403, 413 |
| GET | `/utilisateurs` | A | liste paginée des comptes | 200 | 401, 403 |
| PATCH | `/utilisateurs/{id}` | A | change le rôle, active ou désactive | 200 | 400, 401, 403, 404, 409 |
| DELETE | `/utilisateurs/{id}` | A | supprime le compte et ses avis | 204 | 401, 403, 404, 409 |
| GET | `/journal` | A | journal d'audit, du plus récent au plus ancien | 200 | 401, 403 |

### Paramètres d'URL

| Route | Paramètres |
|---|---|
| `GET /films` | `q` (titre, titre original ou réalisateur ; casse et accents ignorés), `genre`, `support` (`physique`, `numerique`), `annee`, `disponible` (`true`, `false`), `tri` (`titre`, `annee`, `note`, `duree_min`, `date_ajout`), `ordre` (`asc`, `desc`), `page`, `par_page` (1 à 100, 20 par défaut). Avec un jeton : `vu` (`true`, `false`) et `mes_ajouts` (`true`) |
| `GET /prets` | `en_cours` (`true`, `false`), `page`, `par_page` |
| `GET /utilisateurs` | `actif` (`true`, `false`), `page`, `par_page` |
| `GET /journal` | `action` (par exemple `connexion_echec`), `page`, `par_page` |

## Codes d'erreur

| Code | Signification |
|---|---|
| 400 | données invalides ; `details` donne le message de chaque champ |
| 401 | jeton absent, invalide, expiré ou révoqué ; identifiants incorrects |
| 403 | droits insuffisants ; compte en attente ou désactivé ; inscriptions fermées |
| 404 | ressource introuvable |
| 409 | conflit : adresse déjà utilisée, film déjà prêté, genre existant, action sur son propre compte |
| 413 | requête de plus de 1 Mo |
| 429 | trop d'échecs de connexion pour cette adresse ; l'en-tête `Retry-After` donne l'attente en secondes |
| 500, 503 | erreur interne, base indisponible (aucun détail technique n'est renvoyé) |

```json
{
  "erreur": {
    "code": 400,
    "message": "Données invalides.",
    "details": {
      "titre": "Obligatoire.",
      "affiche_url": "Doit être une adresse commençant par https://",
      "role": "Champ inconnu ou non modifiable."
    }
  }
}
```

Seuls les champs documentés sont acceptés : tout autre champ est refusé.

## Formats JSON

### Compte et session

Corps de `POST /auth/inscription` (mot de passe : 10 à 128 caractères, ni trop
simple ni trop courant) :

```json
{ "nom": "Alice", "email": "alice@exemple.fr", "mot_de_passe": "une phrase assez longue" }
```

Réponse de `POST /auth/connexion` (et de l'inscription quand `INSCRIPTION=ouverte`,
avec en plus `"en_attente": false`) :

```json
{
  "jeton": "eyJpZCI6NCwidiI6NX0.avPN…",
  "expire_dans_s": 14400,
  "utilisateur": {
    "id": 4,
    "nom": "Administrateur",
    "email": "admin@videotheque.local",
    "role": "admin",
    "actif": true,
    "date_creation": "2026-11-11T02:02:58.027588+00:00",
    "derniere_connexion": "2026-11-11T02:04:18.254646+00:00"
  }
}
```

Avec `INSCRIPTION=validation`, l'inscription renvoie `{"utilisateur": {…}, "en_attente": true}`
sans jeton : un administrateur doit activer le compte.

Autres corps : `PATCH /auth/moi` → `{"nom": "…"}` ; `POST /auth/mot-de-passe` →
`{"ancien": "…", "nouveau": "…"}` ; `PATCH /utilisateurs/{id}` →
`{"role": "admin" | "membre", "actif": true | false}` (au moins l'un des deux).

### Film

Réponse (`GET /films/{id}`, et chaque élément de `GET /films`) :

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
    "affiche_url": null,
    "ajoute_par": null,
    "ajoute_par_nom": null,
    "date_ajout": "2026-11-11T02:02:52.913602+00:00",
    "genres": ["Science-fiction", "Thriller"],
    "disponible": true,
    "note_moyenne": 8.7,
    "nb_notes": 3,
    "mon_avis": { "note": 9, "commentaire": "Un classique.", "date_avis": "2026-11-11T02:04:18.403349+00:00" },
    "modifiable": true
  }
}
```

- `disponible` : faux si le film fait l'objet d'un prêt en cours ;
- `note_moyenne`, `nb_notes` : calculés sur les avis de tous les utilisateurs ;
- `mon_avis` et `modifiable` dépendent du jeton (`null` et `false` pour un visiteur) ;
- `emplacement` vaut `null` pour un visiteur : étagère et chemin de fichier
  sont réservés aux utilisateurs connectés.

Corps de `POST`, `PUT` et `PATCH` : seuls `titre` et `support` sont obligatoires ;
les genres inconnus sont créés (10 genres au plus par film).

```json
{
  "titre": "Alien", "titre_original": null, "annee": 1979, "realisateur": "Ridley Scott",
  "duree_min": 117, "synopsis": "…", "support": "physique", "format": "DVD",
  "emplacement": "Étagère A3", "affiche_url": "https://exemple.fr/alien.jpg",
  "genres": ["Science-fiction", "Horreur"]
}
```

Liste : `{"films": [ … ], "pagination": {"page": 1, "par_page": 20, "total": 13, "pages": 1}}`.

### Avis

Corps de `PUT /films/{id}/avis` : `{"note": 9, "commentaire": "Un classique."}`
(les deux sont facultatifs : un corps `{}` signifie « vu, sans note »).

```json
{
  "avis": [
    { "utilisateur_id": 4, "auteur": "Administrateur", "note": 9,
      "commentaire": "Un classique.", "date_avis": "2026-11-11T02:04:18.403349+00:00" },
    { "utilisateur_id": 1, "auteur": "Camille", "note": 8,
      "commentaire": null, "date_avis": "2026-10-17T02:02:52.919249+00:00" }
  ]
}
```

### Prêt

Corps de `POST /films/{id}/prets` (seul `emprunteur` est obligatoire) et réponse :

```json
{ "emprunteur": "Thomas", "date_pret": "2026-11-06", "date_retour_prevue": "2026-11-20",
  "commentaire": "Prêté avec le boîtier collector" }
```

```json
{
  "pret": {
    "id": 2, "film_id": 6, "film_titre": "Mad Max: Fury Road", "emprunteur": "Thomas",
    "date_pret": "2026-11-06", "date_retour_prevue": "2026-11-20", "date_retour": null,
    "commentaire": "Prêté avec le boîtier collector", "en_cours": true, "en_retard": false
  }
}
```

Seul un film sur support physique se prête, et un seul prêt à la fois.
`POST /prets/{id}/retour` accepte `{"date_retour": "AAAA-MM-JJ"}` (aujourd'hui par défaut).

### Genre

```json
{ "genres": [ { "id": 8, "nom": "Science-fiction", "nb_films": 3 } ] }
```

### Statistiques

`mes_statistiques` n'est présent qu'avec un jeton.

```json
{
  "statistiques": {
    "nb_films": 13, "nb_physiques": 8, "nb_numeriques": 5, "duree_totale_min": 1599,
    "note_moyenne": 8.9, "nb_notes": 12, "nb_prets_en_cours": 2,
    "films_par_genre": [ { "genre": "Drame", "nb_films": 6 } ],
    "films_par_decennie": [ { "decennie": 1960, "nb_films": 1 } ],
    "mieux_notes": [ { "id": 10, "titre": "Le Parrain", "note_moyenne": 10.0, "nb_notes": 1 } ],
    "mes_statistiques": { "nb_vus": 1, "duree_vue_min": 117, "nb_a_voir": 12 }
  }
}
```

### Fichier d'échange (export et import)

`GET /export` renvoie le catalogue seul : ni comptes, ni avis, ni prêts.
`POST /import` accepte le même objet (seule la liste `films` est lue, 500 films
au plus). Un film déjà présent (même titre, même année, même support) est
ignoré ; si un seul film est invalide, rien n'est importé.

```json
{
  "format": "videotheque-rt0705",
  "version": 1,
  "exporte_le": "2026-11-11T02:04:18+00:00",
  "films": [
    { "titre": "Blade Runner", "titre_original": null, "annee": 1982,
      "realisateur": "Ridley Scott", "duree_min": 117, "synopsis": "…",
      "support": "physique", "format": "DVD", "emplacement": "Étagère A2",
      "affiche_url": null, "genres": ["Science-fiction", "Thriller"] }
  ]
}
```

Réponse de l'import : `{"importes": 1, "ignores": ["Blade Runner"]}`.

### Journal d'audit

```json
{
  "journal": [
    { "id": 31, "date_action": "2026-11-11T02:04:18.254646+00:00", "utilisateur_id": 4,
      "utilisateur_nom": "Administrateur", "action": "connexion", "cible": null, "details": null }
  ],
  "actions": ["connexion", "connexion_echec", "film_cree"],
  "pagination": { "page": 1, "par_page": 50, "total": 31, "pages": 1 }
}
```

Actions enregistrées : `inscription`, `connexion`, `connexion_echec`, `deconnexion`,
`mot_de_passe_modifie`, `utilisateur_modifie`, `utilisateur_supprime`, `film_cree`,
`film_modifie`, `film_supprime`, `avis_supprime`, `pret_cree`, `pret_retour`,
`pret_supprime`, `genre_cree`, `genre_supprime`, `export`, `import`.
