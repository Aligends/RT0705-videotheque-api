"""Ressource « genres »."""
import psycopg
from flask import Blueprint

from .auth import connexion_requise
from .db import get_db
from .erreurs import ErreurAPI, corps_json

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
    nom = corps_json().get("nom")
    if not isinstance(nom, str) or not nom.strip() or len(nom.strip()) > 50:
        raise ErreurAPI(400, "Données invalides.",
                        {"nom": "Obligatoire (50 caractères au plus)."})
    db = get_db()
    try:
        genre = db.execute(
            "INSERT INTO genres (nom) VALUES (%s) RETURNING id, nom, 0 AS nb_films",
            (nom.strip(),),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise ErreurAPI(409, "Ce genre existe déjà.")
    db.commit()
    return {"genre": genre}, 201


@bp.delete("/genres/<int:genre_id>")
@connexion_requise
def supprimer_genre(genre_id):
    """Supprime le genre ; les films concernés sont conservés."""
    db = get_db()
    if db.execute("DELETE FROM genres WHERE id = %s", (genre_id,)).rowcount == 0:
        raise ErreurAPI(404, f"Genre {genre_id} introuvable.")
    db.commit()
    return "", 204
