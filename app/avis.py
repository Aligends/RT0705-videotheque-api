"""Ressource « avis » : chaque utilisateur indique les films qu'il a vus,
avec une note et un commentaire facultatifs."""
from flask import Blueprint, g

from .audit import journaliser
from .auth import admin_requis, connexion_requise
from .db import get_db
from .erreurs import ErreurAPI, corps_json
from .films import lire_film
from .validation import Validateur

bp = Blueprint("avis", __name__)


@bp.get("/films/<int:film_id>/avis")
def lister_avis(film_id):
    """Avis de tous les utilisateurs sur le film, du plus récent au plus ancien."""
    lire_film(film_id)
    avis = get_db().execute(
        "SELECT a.utilisateur_id, u.nom AS auteur, a.note, a.commentaire, a.date_avis "
        "FROM avis a JOIN utilisateurs u ON u.id = a.utilisateur_id "
        "WHERE a.film_id = %s ORDER BY a.date_avis DESC, a.utilisateur_id", (film_id,),
    ).fetchall()
    return {"avis": avis}


@bp.put("/films/<int:film_id>/avis")
@connexion_requise
def enregistrer_avis(film_id):
    """Crée ou remplace l'avis de l'utilisateur connecté : « j'ai vu ce film »."""
    lire_film(film_id)
    v = Validateur(corps_json(), ("note", "commentaire"))
    note = v.entier("note", 0, 10)
    commentaire = v.texte("commentaire", 2000, multiligne=True)
    v.verifier()

    db = get_db()
    cle = (film_id, g.utilisateur["id"])
    existait = db.execute(
        "SELECT 1 FROM avis WHERE film_id = %s AND utilisateur_id = %s", cle).fetchone()
    avis = db.execute(
        "INSERT INTO avis (film_id, utilisateur_id, note, commentaire) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (film_id, utilisateur_id) DO UPDATE "
        "SET note = EXCLUDED.note, commentaire = EXCLUDED.commentaire, date_avis = now() "
        "RETURNING note, commentaire, date_avis", (*cle, note, commentaire),
    ).fetchone()
    db.commit()
    return {"avis": avis}, 200 if existait else 201


@bp.delete("/films/<int:film_id>/avis")
@connexion_requise
def supprimer_mon_avis(film_id):
    """Retire son propre avis : le film redevient « à voir »."""
    db = get_db()
    if db.execute("DELETE FROM avis WHERE film_id = %s AND utilisateur_id = %s",
                  (film_id, g.utilisateur["id"])).rowcount == 0:
        raise ErreurAPI(404, "Vous n'avez pas d'avis sur ce film.")
    db.commit()
    return "", 204


@bp.delete("/films/<int:film_id>/avis/<int:utilisateur_id>")
@admin_requis
def moderer_avis(film_id, utilisateur_id):
    """Modération : un administrateur supprime l'avis d'un utilisateur."""
    db = get_db()
    ligne = db.execute(
        "DELETE FROM avis a USING utilisateurs u, films f "
        "WHERE a.film_id = %s AND a.utilisateur_id = %s "
        "  AND u.id = a.utilisateur_id AND f.id = a.film_id "
        "RETURNING u.nom AS auteur, f.titre", (film_id, utilisateur_id),
    ).fetchone()
    if ligne is None:
        raise ErreurAPI(404, "Avis introuvable.")
    journaliser("avis_supprime", cible=f"avis de {ligne['auteur']} sur « {ligne['titre']} »")
    db.commit()
    return "", 204
