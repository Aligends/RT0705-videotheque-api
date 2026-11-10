"""Ressource « films » : consultation, recherche, ajout, modification, suppression."""
from flask import Blueprint, g, request

from .auth import connexion_requise
from .db import get_db
from .erreurs import ErreurAPI, corps_json

bp = Blueprint("films", __name__)

SUPPORTS = ("physique", "numerique")
# champ -> longueur maximale (None : texte libre)
CHAMPS_TEXTE = {
    "titre": 255, "titre_original": 255, "realisateur": 255, "synopsis": None,
    "format": 30, "emplacement": 255, "affiche_url": None,
}
# champ -> (minimum, maximum)
CHAMPS_ENTIERS = {"annee": (1888, 2100), "duree_min": (1, 32767), "note": (0, 10)}
COLONNES = [*CHAMPS_TEXTE, *CHAMPS_ENTIERS, "support", "vu"]
TRIS = {"titre": "lower(f.titre)", "annee": "f.annee", "note": "f.note",
        "duree_min": "f.duree_min", "date_ajout": "f.date_ajout"}

# Un film est renvoyé avec la liste de ses genres et sa disponibilité
# (faux s'il fait l'objet d'un prêt en cours).
SELECT_FILM = """
    SELECT f.id, f.titre, f.titre_original, f.annee, f.realisateur, f.duree_min,
           f.synopsis, f.support, f.format, f.emplacement, f.note, f.vu,
           f.affiche_url, f.ajoute_par, f.date_ajout,
           ARRAY(SELECT g.nom FROM film_genres fg JOIN genres g ON g.id = fg.genre_id
                 WHERE fg.film_id = f.id ORDER BY g.nom) AS genres,
           NOT EXISTS (SELECT 1 FROM prets p
                       WHERE p.film_id = f.id AND p.date_retour IS NULL) AS disponible
    FROM films f
"""


def lire_film(film_id):
    film = get_db().execute(SELECT_FILM + " WHERE f.id = %s", (film_id,)).fetchone()
    if film is None:
        raise ErreurAPI(404, f"Film {film_id} introuvable.")
    return film


def valider_film(donnees, partiel=False):
    """Contrôle et nettoie les champs d'un film.

    Renvoie (valeurs des colonnes, liste des genres ou None si absente).
    Avec ``partiel`` (PATCH), seuls les champs fournis sont pris en compte ;
    sinon (POST, PUT) les champs absents sont remis à vide.
    """
    details, valeurs = {}, {}
    inconnus = set(donnees) - set(COLONNES) - {"genres"}
    for champ in inconnus:
        details[champ] = "Champ inconnu ou non modifiable."

    for champ, longueur in CHAMPS_TEXTE.items():
        if champ not in donnees:
            if not partiel:
                valeurs[champ] = None
            continue
        valeur = donnees[champ]
        if valeur is None or valeur == "":
            valeurs[champ] = None
        elif not isinstance(valeur, str):
            details[champ] = "Doit être une chaîne de caractères."
        elif longueur and len(valeur.strip()) > longueur:
            details[champ] = f"{longueur} caractères au plus."
        else:
            valeurs[champ] = valeur.strip() or None

    for champ, (mini, maxi) in CHAMPS_ENTIERS.items():
        if champ not in donnees:
            if not partiel:
                valeurs[champ] = None
            continue
        valeur = donnees[champ]
        if valeur is None:
            valeurs[champ] = None
        elif isinstance(valeur, bool) or not isinstance(valeur, int) or not mini <= valeur <= maxi:
            details[champ] = f"Doit être un entier entre {mini} et {maxi}."
        else:
            valeurs[champ] = valeur

    if "vu" in donnees:
        if isinstance(donnees["vu"], bool):
            valeurs["vu"] = donnees["vu"]
        else:
            details["vu"] = "Doit être un booléen."
    elif not partiel:
        valeurs["vu"] = False

    if "support" in donnees:
        if donnees["support"] in SUPPORTS:
            valeurs["support"] = donnees["support"]
        else:
            details["support"] = "Doit valoir « physique » ou « numerique »."
    elif not partiel:
        details["support"] = "Obligatoire : « physique » ou « numerique »."

    if ("titre" in donnees or not partiel) and not valeurs.get("titre") and "titre" not in details:
        details["titre"] = "Obligatoire."

    genres = None
    if "genres" in donnees:
        brut = donnees["genres"]
        if (not isinstance(brut, list)
                or any(not isinstance(nom, str) or not nom.strip() or len(nom.strip()) > 50
                       for nom in brut)):
            details["genres"] = "Doit être une liste de noms de genres (50 caractères au plus)."
        else:
            genres = [nom.strip() for nom in brut]
    elif not partiel:
        genres = []

    if details:
        raise ErreurAPI(400, "Données invalides.", details)
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


def _entier(nom, defaut, mini, maxi):
    brut = request.args.get(nom)
    if brut is None:
        return defaut
    try:
        valeur = int(brut)
    except ValueError:
        raise ErreurAPI(400, f"Le paramètre « {nom} » doit être un entier.")
    if not mini <= valeur <= maxi:
        raise ErreurAPI(400, f"Le paramètre « {nom} » doit être entre {mini} et {maxi}.")
    return valeur


def _booleen(nom):
    brut = request.args.get(nom)
    if brut is None or brut == "":
        return None
    if brut.lower() in ("1", "true", "oui"):
        return True
    if brut.lower() in ("0", "false", "non"):
        return False
    raise ErreurAPI(400, f"Le paramètre « {nom} » doit valoir true ou false.")


@bp.get("/films")
def lister_films():
    """Liste paginée, avec recherche et filtres passés dans l'URL."""
    conditions, parametres = [], []

    if q := request.args.get("q", "").strip():
        conditions.append("(f.titre ILIKE %s OR f.titre_original ILIKE %s OR f.realisateur ILIKE %s)")
        parametres += [f"%{q}%"] * 3
    if genre := request.args.get("genre", "").strip():
        conditions.append("EXISTS (SELECT 1 FROM film_genres fg JOIN genres g ON g.id = fg.genre_id "
                          "WHERE fg.film_id = f.id AND lower(g.nom) = lower(%s))")
        parametres.append(genre)
    if support := request.args.get("support", "").strip():
        if support not in SUPPORTS:
            raise ErreurAPI(400, "Le paramètre « support » doit valoir « physique » ou « numerique ».")
        conditions.append("f.support = %s")
        parametres.append(support)
    if request.args.get("annee"):
        conditions.append("f.annee = %s")
        parametres.append(_entier("annee", None, 1888, 2100))
    if (vu := _booleen("vu")) is not None:
        conditions.append("f.vu = %s")
        parametres.append(vu)
    if (disponible := _booleen("disponible")) is not None:
        conditions.append(("NOT " if disponible else "") +
                          "EXISTS (SELECT 1 FROM prets p WHERE p.film_id = f.id AND p.date_retour IS NULL)")

    tri = request.args.get("tri", "titre")
    ordre = request.args.get("ordre", "asc").lower()
    if tri not in TRIS or ordre not in ("asc", "desc"):
        raise ErreurAPI(400, f"Tri invalide : tri parmi {sorted(TRIS)}, ordre « asc » ou « desc ».")
    page = _entier("page", 1, 1, 1_000_000)
    par_page = _entier("par_page", 20, 1, 100)

    ou = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    db = get_db()
    total = db.execute("SELECT count(*) AS n FROM films f" + ou, parametres).fetchone()["n"]
    films = db.execute(
        f"{SELECT_FILM}{ou} ORDER BY {TRIS[tri]} {ordre} NULLS LAST, f.id LIMIT %s OFFSET %s",
        [*parametres, par_page, (page - 1) * par_page],
    ).fetchall()
    return {
        "films": films,
        "pagination": {"page": page, "par_page": par_page, "total": total,
                       "pages": max(1, -(-total // par_page))},
    }


@bp.post("/films")
@connexion_requise
def creer_film():
    valeurs, genres = valider_film(corps_json())
    valeurs["ajoute_par"] = g.utilisateur["id"]
    colonnes = list(valeurs)
    db = get_db()
    film_id = db.execute(
        f"INSERT INTO films ({', '.join(colonnes)}) "
        f"VALUES ({', '.join(['%s'] * len(colonnes))}) RETURNING id",
        [valeurs[c] for c in colonnes],
    ).fetchone()["id"]
    enregistrer_genres(film_id, genres)
    db.commit()
    return ({"film": lire_film(film_id)}, 201,
            {"Location": f"{request.path.rstrip('/')}/{film_id}"})


@bp.get("/films/<int:film_id>")
def detail_film(film_id):
    return {"film": lire_film(film_id)}


@bp.route("/films/<int:film_id>", methods=["PUT", "PATCH"])
@connexion_requise
def modifier_film(film_id):
    """PUT remplace le film entier, PATCH ne modifie que les champs fournis."""
    lire_film(film_id)
    valeurs, genres = valider_film(corps_json(), partiel=request.method == "PATCH")
    db = get_db()
    if valeurs:
        db.execute(
            f"UPDATE films SET {', '.join(c + ' = %s' for c in valeurs)} WHERE id = %s",
            [*valeurs.values(), film_id],
        )
    if genres is not None:
        enregistrer_genres(film_id, genres)
    db.commit()
    return {"film": lire_film(film_id)}


@bp.delete("/films/<int:film_id>")
@connexion_requise
def supprimer_film(film_id):
    db = get_db()
    if db.execute("DELETE FROM films WHERE id = %s", (film_id,)).rowcount == 0:
        raise ErreurAPI(404, f"Film {film_id} introuvable.")
    db.commit()
    return "", 204
