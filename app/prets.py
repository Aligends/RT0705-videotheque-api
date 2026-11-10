"""Ressource « prêts » : prêt d'un film sur support physique, puis retour."""
from datetime import date

import psycopg
from flask import Blueprint, request

from .auth import connexion_requise
from .db import get_db
from .erreurs import ErreurAPI, corps_json
from .films import lire_film

bp = Blueprint("prets", __name__)

SELECT_PRET = """
    SELECT p.id, p.film_id, f.titre AS film_titre, p.emprunteur, p.date_pret,
           p.date_retour_prevue, p.date_retour, p.commentaire,
           (p.date_retour IS NULL) AS en_cours,
           (p.date_retour IS NULL AND p.date_retour_prevue < CURRENT_DATE) AS en_retard
    FROM prets p JOIN films f ON f.id = p.film_id
"""


def _date(donnees, champ):
    valeur = donnees.get(champ)
    if valeur is None or valeur == "":
        return None
    try:
        return date.fromisoformat(valeur)
    except (TypeError, ValueError):
        raise ErreurAPI(400, "Données invalides.", {champ: "Date attendue au format AAAA-MM-JJ."})


def _lire_pret(pret_id):
    pret = get_db().execute(SELECT_PRET + " WHERE p.id = %s", (pret_id,)).fetchone()
    if pret is None:
        raise ErreurAPI(404, f"Prêt {pret_id} introuvable.")
    return pret


@bp.get("/prets")
def lister_prets():
    """Tous les prêts ; ?en_cours=true ne garde que les films non rendus."""
    en_cours = request.args.get("en_cours", "").lower()
    ou = ""
    if en_cours in ("1", "true", "oui"):
        ou = " WHERE p.date_retour IS NULL"
    elif en_cours in ("0", "false", "non"):
        ou = " WHERE p.date_retour IS NOT NULL"
    prets = get_db().execute(SELECT_PRET + ou + " ORDER BY p.date_pret DESC, p.id DESC").fetchall()
    return {"prets": prets}


@bp.get("/films/<int:film_id>/prets")
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
    donnees = corps_json()
    emprunteur = donnees.get("emprunteur")
    if not isinstance(emprunteur, str) or not emprunteur.strip() or len(emprunteur.strip()) > 100:
        raise ErreurAPI(400, "Données invalides.",
                        {"emprunteur": "Obligatoire (100 caractères au plus)."})
    commentaire = donnees.get("commentaire")
    if commentaire is not None and not isinstance(commentaire, str):
        raise ErreurAPI(400, "Données invalides.", {"commentaire": "Doit être une chaîne."})
    date_pret = _date(donnees, "date_pret") or date.today()
    retour_prevu = _date(donnees, "date_retour_prevue")
    if retour_prevu and retour_prevu < date_pret:
        raise ErreurAPI(400, "Données invalides.",
                        {"date_retour_prevue": "Ne peut pas précéder la date du prêt."})

    if film["support"] != "physique":
        raise ErreurAPI(409, "Seuls les films sur support physique peuvent être prêtés.")
    db = get_db()
    try:
        pret_id = db.execute(
            "INSERT INTO prets (film_id, emprunteur, date_pret, date_retour_prevue, commentaire) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (film_id, emprunteur.strip(), date_pret, retour_prevu, commentaire or None),
        ).fetchone()["id"]
    except psycopg.errors.UniqueViolation:  # index unique : un seul prêt en cours par film
        raise ErreurAPI(409, "Ce film est déjà prêté.")
    db.commit()
    return {"pret": _lire_pret(pret_id)}, 201


@bp.post("/prets/<int:pret_id>/retour")
@connexion_requise
def retour_pret(pret_id):
    """Enregistre le retour du film (aujourd'hui, ou à la date fournie)."""
    pret = _lire_pret(pret_id)
    if not pret["en_cours"]:
        raise ErreurAPI(409, "Ce film a déjà été rendu.")
    donnees = request.get_json(silent=True)
    date_retour = _date(donnees if isinstance(donnees, dict) else {}, "date_retour") or date.today()
    if date_retour < pret["date_pret"]:
        raise ErreurAPI(400, "Données invalides.",
                        {"date_retour": "Ne peut pas précéder la date du prêt."})
    db = get_db()
    db.execute("UPDATE prets SET date_retour = %s WHERE id = %s", (date_retour, pret_id))
    db.commit()
    return {"pret": _lire_pret(pret_id)}


@bp.delete("/prets/<int:pret_id>")
@connexion_requise
def supprimer_pret(pret_id):
    db = get_db()
    if db.execute("DELETE FROM prets WHERE id = %s", (pret_id,)).rowcount == 0:
        raise ErreurAPI(404, f"Prêt {pret_id} introuvable.")
    db.commit()
    return "", 204
