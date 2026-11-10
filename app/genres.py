"""Ressource « genres »."""
import psycopg
from flask import Blueprint

from .audit import journaliser
from .auth import admin_requis, connexion_requise
from .db import get_db
from .erreurs import ErreurAPI, corps_json
from .validation import Validateur

bp = Blueprint("genres", __name__)


@bp.get("/genres")
def lister_genres():
    genres = get_db().execute(
        "SELECT g.id, g.nom, count(fg.film_id) AS nb_films "
        "FROM genres g LEFT JOIN film_genres fg ON fg.genre_id = g.id "
        "GROUP BY g.id ORDER BY lower(g.nom)"
    ).fetchall()
    return {"genres": genres}


@bp.post("/genres")
@connexion_requise
def creer_genre():
    v = Validateur(corps_json(), ("nom",))
    nom = v.texte("nom", 50, obligatoire=True)
    v.verifier()
    db = get_db()
    try:
        genre = db.execute(
            "INSERT INTO genres (nom) VALUES (%s) RETURNING id, nom, 0 AS nb_films", (nom,),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise ErreurAPI(409, "Ce genre existe déjà.")
    journaliser("genre_cree", cible=nom)
    db.commit()
    return {"genre": genre}, 201


@bp.delete("/genres/<int:genre_id>")
@admin_requis
def supprimer_genre(genre_id):
    """Supprime le genre ; les films concernés sont conservés."""
    db = get_db()
    ligne = db.execute("DELETE FROM genres WHERE id = %s RETURNING nom", (genre_id,)).fetchone()
    if ligne is None:
        raise ErreurAPI(404, f"Genre {genre_id} introuvable.")
    journaliser("genre_supprime", cible=ligne["nom"])
    db.commit()
    return "", 204
