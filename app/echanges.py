"""Export et import du catalogue sous forme d'un fichier JSON.

Le fichier ne contient que le catalogue (films et genres) : ni comptes,
ni avis, ni prêts, donc aucune donnée personnelle.
"""
from datetime import datetime, timezone

from flask import Blueprint

from .audit import journaliser
from .auth import admin_requis, connexion_requise
from .db import get_db
from .erreurs import ErreurAPI, corps_json
from .films import COLONNES, inserer_film, valider_film

bp = Blueprint("echanges", __name__)

FORMAT = "videotheque-rt0705"
MAX_FILMS_IMPORT = 500


def _pluriel(nombre, mot):
    """1 film, 2 films."""
    return f"{nombre} {mot}{'s' if nombre > 1 else ''}"


@bp.get("/export")
@connexion_requise
def exporter():
    db = get_db()
    films = db.execute(
        f"SELECT {', '.join('f.' + c for c in COLONNES)}, "
        "       ARRAY(SELECT ge.nom FROM film_genres fg JOIN genres ge ON ge.id = fg.genre_id "
        "             WHERE fg.film_id = f.id ORDER BY lower(ge.nom)) AS genres "
        "FROM films f ORDER BY lower(f.titre), f.id"
    ).fetchall()
    journaliser("export", details=_pluriel(len(films), "film"))
    db.commit()
    return {"format": FORMAT, "version": 1,
            "exporte_le": datetime.now(timezone.utc).replace(microsecond=0),
            "films": films}


@bp.post("/import")
@admin_requis
def importer():
    """Ajoute les films d'un fichier d'export.

    Tout ou rien : si un seul film est invalide, rien n'est ajouté et la
    réponse liste toutes les erreurs. Un film déjà présent (même titre, même
    année, même support) est ignoré.
    """
    films = corps_json().get("films")
    if not isinstance(films, list) or not films:
        raise ErreurAPI(400, "Données invalides.",
                        {"films": "Doit être une liste non vide de films."})
    if len(films) > MAX_FILMS_IMPORT:
        raise ErreurAPI(400, "Données invalides.",
                        {"films": f"{MAX_FILMS_IMPORT} films au plus par import."})

    valides, erreurs = [], {}
    for indice, brut in enumerate(films):
        if not isinstance(brut, dict):
            erreurs[f"films[{indice}]"] = "Doit être un objet JSON."
            continue
        try:
            valides.append(valider_film(brut))
        except ErreurAPI as e:
            for champ, message in e.details.items():
                erreurs[f"films[{indice}].{champ}"] = message
    if erreurs:
        raise ErreurAPI(400, "Import refusé : aucun film n'a été ajouté.", erreurs)

    def cle(titre, annee, support):
        return titre.lower(), annee, support

    db = get_db()
    connus = {cle(f["titre"], f["annee"], f["support"])
              for f in db.execute("SELECT titre, annee, support FROM films")}
    ignores = []
    for valeurs, genres in valides:
        identite = cle(valeurs["titre"], valeurs["annee"], valeurs["support"])
        if identite in connus:
            ignores.append(valeurs["titre"])
            continue
        connus.add(identite)
        inserer_film(valeurs, genres)
    importes = len(valides) - len(ignores)
    journaliser("import", details=f"{_pluriel(importes, 'film')} ajouté{'s' if importes > 1 else ''}, "
                                  f"{len(ignores)} déjà présent{'s' if len(ignores) > 1 else ''}")
    db.commit()
    return {"importes": importes, "ignores": ignores}
