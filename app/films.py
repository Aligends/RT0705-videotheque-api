"""Ressource « films » : consultation, recherche, ajout, modification, suppression."""
from flask import Blueprint, g, request

from .audit import journaliser
from .auth import connexion_requise
from .db import get_db
from .erreurs import ErreurAPI, corps_json
from .validation import (Validateur, bloc_pagination, echapper_like, pagination,
                         parametre_booleen, parametre_entier)

bp = Blueprint("films", __name__)

SUPPORTS = ("physique", "numerique")
# Seuls champs qu'un client peut fournir. « genres » n'est pas une colonne
# de la table films : il est enregistré dans la table d'association.
CHAMPS = ("titre", "titre_original", "annee", "realisateur", "duree_min", "synopsis",
          "support", "format", "emplacement", "affiche_url", "genres")
COLONNES = CHAMPS[:-1]
MAX_GENRES = 10
# Tris autorisés : la valeur reçue sert de clé, jamais de texte SQL.
TRIS = {"titre": "lower(f.titre)", "annee": "f.annee", "note": "note_moyenne",
        "duree_min": "f.duree_min", "date_ajout": "f.date_ajout"}

# Un film est renvoyé avec ses genres, sa disponibilité (faux s'il est prêté),
# la moyenne des notes et, pour un utilisateur connecté, son propre avis.
SELECT_FILM = """
    SELECT f.id, f.titre, f.titre_original, f.annee, f.realisateur, f.duree_min,
           f.synopsis, f.support, f.format, f.emplacement, f.affiche_url,
           f.ajoute_par, u.nom AS ajoute_par_nom, f.date_ajout,
           ARRAY(SELECT ge.nom FROM film_genres fg JOIN genres ge ON ge.id = fg.genre_id
                 WHERE fg.film_id = f.id ORDER BY lower(ge.nom)) AS genres,
           NOT EXISTS (SELECT 1 FROM prets p
                       WHERE p.film_id = f.id AND p.date_retour IS NULL) AS disponible,
           (SELECT round(avg(a.note), 1)::float FROM avis a WHERE a.film_id = f.id) AS note_moyenne,
           (SELECT count(a.note) FROM avis a WHERE a.film_id = f.id) AS nb_notes,
           (SELECT json_build_object('note', a.note, 'commentaire', a.commentaire,
                                     'date_avis', a.date_avis)
            FROM avis a
            WHERE a.film_id = f.id AND a.utilisateur_id = %(moi)s) AS mon_avis
    FROM films f LEFT JOIN utilisateurs u ON u.id = f.ajoute_par
"""


def _moi():
    return g.utilisateur["id"] if g.utilisateur else None


def peut_modifier(film):
    """Un film est modifiable par celui qui l'a ajouté et par les administrateurs."""
    utilisateur = g.utilisateur
    return utilisateur is not None and (
        utilisateur["role"] == "admin" or film["ajoute_par"] == utilisateur["id"])


def _completer(film):
    film["modifiable"] = peut_modifier(film)
    return film


def lire_film(film_id):
    film = get_db().execute(SELECT_FILM + " WHERE f.id = %(id)s",
                            {"id": film_id, "moi": _moi()}).fetchone()
    if film is None:
        raise ErreurAPI(404, f"Film {film_id} introuvable.")
    return _completer(film)


def _film_modifiable(film_id):
    film = lire_film(film_id)
    if not film["modifiable"]:
        raise ErreurAPI(403, "Seuls la personne qui a ajouté ce film et les "
                             "administrateurs peuvent le modifier ou le supprimer.")
    return film


def valider_film(donnees, partiel=False):
    """Contrôle et nettoie les champs d'un film.

    Renvoie (valeurs des colonnes, liste des genres ou None si absente).
    Avec ``partiel`` (PATCH), seuls les champs fournis sont pris en compte ;
    sinon (POST, PUT, import) les champs absents sont remis à vide.
    """
    v = Validateur(donnees, CHAMPS)
    lecteurs = {
        "titre": lambda: v.texte("titre", 255, obligatoire=True),
        "titre_original": lambda: v.texte("titre_original", 255),
        "annee": lambda: v.entier("annee", 1888, 2100),
        "realisateur": lambda: v.texte("realisateur", 255),
        "duree_min": lambda: v.entier("duree_min", 1, 32767),
        "synopsis": lambda: v.texte("synopsis", 5000, multiligne=True),
        "support": lambda: v.choix("support", SUPPORTS, obligatoire=True),
        "format": lambda: v.texte("format", 30),
        "emplacement": lambda: v.texte("emplacement", 255),
        "affiche_url": lambda: v.url_https("affiche_url", 500),
    }
    valeurs = {champ: lire() for champ, lire in lecteurs.items()
               if champ in v or not partiel}
    genres = None
    if "genres" in v or not partiel:
        genres = v.liste_textes("genres", 50, MAX_GENRES)
    v.verifier()
    return valeurs, genres


def enregistrer_genres(film_id, noms):
    """Remplace les genres du film ; les genres inconnus sont créés."""
    db = get_db()
    db.execute("DELETE FROM film_genres WHERE film_id = %s", (film_id,))
    for nom in noms:
        db.execute("INSERT INTO genres (nom) VALUES (%s) ON CONFLICT DO NOTHING", (nom,))
        db.execute(
            "INSERT INTO film_genres (film_id, genre_id) "
            "SELECT %s, id FROM genres WHERE lower(nom) = lower(%s) ON CONFLICT DO NOTHING",
            (film_id, nom),
        )


def inserer_film(valeurs, genres):
    """Insère un film validé, au nom de l'utilisateur courant ; renvoie son identifiant."""
    colonnes = [c for c in COLONNES if c in valeurs]     # noms issus de la liste blanche
    film_id = get_db().execute(
        f"INSERT INTO films ({', '.join(colonnes)}, ajoute_par) "
        f"VALUES ({', '.join(['%s'] * len(colonnes))}, %s) RETURNING id",
        [*(valeurs[c] for c in colonnes), g.utilisateur["id"]],
    ).fetchone()["id"]
    enregistrer_genres(film_id, genres or [])
    return film_id


def _libelle(film_id, titre):
    return f"film n° {film_id} « {titre} »"


@bp.get("/films")
def lister_films():
    """Liste paginée, avec recherche et filtres passés dans l'URL."""
    conditions, parametres = [], {"moi": _moi()}

    if q := " ".join(request.args.get("q", "").split()):
        # Recherche insensible à la casse et aux accents.
        conditions.append(
            "(unaccent(f.titre) ILIKE unaccent(%(q)s)"
            " OR unaccent(coalesce(f.titre_original, '')) ILIKE unaccent(%(q)s)"
            " OR unaccent(coalesce(f.realisateur, '')) ILIKE unaccent(%(q)s))")
        parametres["q"] = f"%{echapper_like(q[:100])}%"
    if genre := request.args.get("genre", "").strip():
        conditions.append(
            "EXISTS (SELECT 1 FROM film_genres fg JOIN genres ge ON ge.id = fg.genre_id "
            "WHERE fg.film_id = f.id AND lower(ge.nom) = lower(%(genre)s))")
        parametres["genre"] = genre[:50]
    if support := request.args.get("support", "").strip():
        if support not in SUPPORTS:
            raise ErreurAPI(400, "Le paramètre « support » doit valoir « physique » ou « numerique ».")
        conditions.append("f.support = %(support)s")
        parametres["support"] = support
    if (annee := parametre_entier("annee", None, 1888, 2100)) is not None:
        conditions.append("f.annee = %(annee)s")
        parametres["annee"] = annee
    if (disponible := parametre_booleen("disponible")) is not None:
        conditions.append(
            ("NOT " if disponible else "") +
            "EXISTS (SELECT 1 FROM prets p WHERE p.film_id = f.id AND p.date_retour IS NULL)")
    # Les deux filtres suivants dépendent de l'utilisateur : ils exigent un jeton.
    vu, mes_ajouts = parametre_booleen("vu"), parametre_booleen("mes_ajouts")
    if (vu is not None or mes_ajouts) and g.utilisateur is None:
        raise ErreurAPI(401, "Les filtres « vu » et « mes_ajouts » demandent d'être connecté.")
    if vu is not None:
        conditions.append(
            ("" if vu else "NOT ") +
            "EXISTS (SELECT 1 FROM avis a WHERE a.film_id = f.id AND a.utilisateur_id = %(moi)s)")
    if mes_ajouts:
        conditions.append("f.ajoute_par = %(moi)s")

    tri = request.args.get("tri") or "titre"
    ordre = (request.args.get("ordre") or "asc").lower()
    if tri not in TRIS or ordre not in ("asc", "desc"):
        raise ErreurAPI(400, f"Tri invalide : tri parmi {sorted(TRIS)}, ordre « asc » ou « desc ».")
    page, par_page, decalage = pagination()

    ou = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    db = get_db()
    total = db.execute("SELECT count(*) AS n FROM films f" + ou, parametres).fetchone()["n"]
    films = db.execute(
        f"{SELECT_FILM}{ou} ORDER BY {TRIS[tri]} {ordre} NULLS LAST, f.id "
        f"LIMIT %(limite)s OFFSET %(decalage)s",
        {**parametres, "limite": par_page, "decalage": decalage},
    ).fetchall()
    return {"films": [_completer(film) for film in films],
            "pagination": bloc_pagination(page, par_page, total)}


@bp.post("/films")
@connexion_requise
def creer_film():
    valeurs, genres = valider_film(corps_json())
    film_id = inserer_film(valeurs, genres)
    journaliser("film_cree", cible=_libelle(film_id, valeurs["titre"]))
    get_db().commit()
    return ({"film": lire_film(film_id)}, 201,
            {"Location": f"{request.path.rstrip('/')}/{film_id}"})


@bp.get("/films/<int:film_id>")
def detail_film(film_id):
    return {"film": lire_film(film_id)}


@bp.route("/films/<int:film_id>", methods=["PUT", "PATCH"])
@connexion_requise
def modifier_film(film_id):
    """PUT remplace le film entier, PATCH ne modifie que les champs fournis."""
    film = _film_modifiable(film_id)
    valeurs, genres = valider_film(corps_json(), partiel=request.method == "PATCH")
    db = get_db()
    if valeurs:
        colonnes = [c for c in COLONNES if c in valeurs]
        db.execute(
            f"UPDATE films SET {', '.join(c + ' = %s' for c in colonnes)} WHERE id = %s",
            [*(valeurs[c] for c in colonnes), film_id],
        )
    if genres is not None:
        enregistrer_genres(film_id, genres)
    journaliser("film_modifie", cible=_libelle(film_id, valeurs.get("titre", film["titre"])))
    db.commit()
    return {"film": lire_film(film_id)}


@bp.delete("/films/<int:film_id>")
@connexion_requise
def supprimer_film(film_id):
    film = _film_modifiable(film_id)
    db = get_db()
    db.execute("DELETE FROM films WHERE id = %s", (film_id,))
    journaliser("film_supprime", cible=_libelle(film_id, film["titre"]))
    db.commit()
    return "", 204
