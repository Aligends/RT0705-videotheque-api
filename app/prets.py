"""Ressource « prêts » : prêt d'un film sur support physique, puis retour.

Les prêts contiennent le nom des emprunteurs : toutes ces routes sont
réservées aux utilisateurs connectés.
"""
from datetime import date

import psycopg
from flask import Blueprint, request

from .audit import journaliser
from .auth import admin_requis, connexion_requise
from .db import get_db
from .erreurs import ErreurAPI, corps_json
from .films import lire_film
from .validation import Validateur, bloc_pagination, pagination, parametre_booleen

bp = Blueprint("prets", __name__)

SELECT_PRET = """
    SELECT p.id, p.film_id, f.titre AS film_titre, p.emprunteur, p.date_pret,
           p.date_retour_prevue, p.date_retour, p.commentaire,
           (p.date_retour IS NULL) AS en_cours,
           (p.date_retour IS NULL AND p.date_retour_prevue < CURRENT_DATE) AS en_retard
    FROM prets p JOIN films f ON f.id = p.film_id
"""


def _lire_pret(pret_id):
    pret = get_db().execute(SELECT_PRET + " WHERE p.id = %s", (pret_id,)).fetchone()
    if pret is None:
        raise ErreurAPI(404, f"Prêt {pret_id} introuvable.")
    return pret


@bp.get("/prets")
@connexion_requise
def lister_prets():
    """Liste paginée ; ?en_cours=true ne garde que les films non rendus."""
    en_cours = parametre_booleen("en_cours")
    ou = ""
    if en_cours is not None:
        ou = " WHERE p.date_retour IS " + ("NULL" if en_cours else "NOT NULL")
    page, par_page, decalage = pagination(50)
    db = get_db()
    total = db.execute("SELECT count(*) AS n FROM prets p" + ou).fetchone()["n"]
    prets = db.execute(
        SELECT_PRET + ou + " ORDER BY p.date_pret DESC, p.id DESC LIMIT %s OFFSET %s",
        (par_page, decalage),
    ).fetchall()
    return {"prets": prets, "pagination": bloc_pagination(page, par_page, total)}


@bp.get("/films/<int:film_id>/prets")
@connexion_requise
def prets_du_film(film_id):
    """Historique des prêts d'un film."""
    lire_film(film_id)
    prets = get_db().execute(
        SELECT_PRET + " WHERE p.film_id = %s ORDER BY p.date_pret DESC, p.id DESC", (film_id,)
    ).fetchall()
    return {"prets": prets}


@bp.post("/films/<int:film_id>/prets")
@connexion_requise
def preter_film(film_id):
    film = lire_film(film_id)
    v = Validateur(corps_json(), ("emprunteur", "date_pret", "date_retour_prevue", "commentaire"))
    emprunteur = v.texte("emprunteur", 100, obligatoire=True)
    commentaire = v.texte("commentaire", 500, multiligne=True)
    date_pret = v.date("date_pret") or date.today()
    retour_prevu = v.date("date_retour_prevue")
    if date_pret > date.today():
        v.erreur("date_pret", "Ne peut pas être dans le futur.")
    if retour_prevu and retour_prevu < date_pret:
        v.erreur("date_retour_prevue", "Ne peut pas précéder la date du prêt.")
    v.verifier()

    if film["support"] != "physique":
        raise ErreurAPI(409, "Seuls les films sur support physique peuvent être prêtés.")
    db = get_db()
    try:
        pret_id = db.execute(
            "INSERT INTO prets (film_id, emprunteur, date_pret, date_retour_prevue, commentaire) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (film_id, emprunteur, date_pret, retour_prevu, commentaire),
        ).fetchone()["id"]
    except psycopg.errors.UniqueViolation:  # index unique : un seul prêt en cours par film
        raise ErreurAPI(409, "Ce film est déjà prêté.")
    journaliser("pret_cree", cible=f"« {film['titre']} » prêté à {emprunteur}")
    db.commit()
    return {"pret": _lire_pret(pret_id)}, 201


@bp.post("/prets/<int:pret_id>/retour")
@connexion_requise
def retour_pret(pret_id):
    """Enregistre le retour du film (aujourd'hui, ou à la date fournie)."""
    pret = _lire_pret(pret_id)
    if not pret["en_cours"]:
        raise ErreurAPI(409, "Ce film a déjà été rendu.")
    donnees = request.get_json(silent=True)     # corps facultatif
    v = Validateur(donnees if isinstance(donnees, dict) else {}, ("date_retour",))
    date_retour = v.date("date_retour") or date.today()
    if date_retour < pret["date_pret"]:
        v.erreur("date_retour", "Ne peut pas précéder la date du prêt.")
    elif date_retour > date.today():
        v.erreur("date_retour", "Ne peut pas être dans le futur.")
    v.verifier()

    db = get_db()
    db.execute("UPDATE prets SET date_retour = %s WHERE id = %s", (date_retour, pret_id))
    journaliser("pret_retour", cible=f"« {pret['film_titre']} » rendu par {pret['emprunteur']}")
    db.commit()
    return {"pret": _lire_pret(pret_id)}


@bp.delete("/prets/<int:pret_id>")
@admin_requis
def supprimer_pret(pret_id):
    """Retire un prêt de l'historique (administrateur)."""
    pret = _lire_pret(pret_id)
    db = get_db()
    db.execute("DELETE FROM prets WHERE id = %s", (pret_id,))
    journaliser("pret_supprime",
                cible=f"prêt de « {pret['film_titre']} » à {pret['emprunteur']}")
    db.commit()
    return "", 204
