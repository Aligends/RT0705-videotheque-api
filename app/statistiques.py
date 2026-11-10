"""Chiffres clés de la vidéothèque."""
from flask import Blueprint

from .db import get_db

bp = Blueprint("statistiques", __name__)


@bp.get("/statistiques")
def statistiques():
    db = get_db()
    stats = db.execute("""
        SELECT count(*)                                    AS nb_films,
               count(*) FILTER (WHERE support = 'physique')  AS nb_physiques,
               count(*) FILTER (WHERE support = 'numerique') AS nb_numeriques,
               count(*) FILTER (WHERE vu)                    AS nb_vus,
               count(*) FILTER (WHERE NOT vu)                AS nb_a_voir,
               COALESCE(sum(duree_min), 0)::int              AS duree_totale_min,
               round(avg(note), 1)::float                    AS note_moyenne
        FROM films
    """).fetchone()
    stats["nb_prets_en_cours"] = db.execute(
        "SELECT count(*) AS n FROM prets WHERE date_retour IS NULL"
    ).fetchone()["n"]
    stats["films_par_genre"] = db.execute(
        "SELECT g.nom AS genre, count(*) AS nb_films "
        "FROM genres g JOIN film_genres fg ON fg.genre_id = g.id "
        "GROUP BY g.nom ORDER BY nb_films DESC, lower(g.nom)"
    ).fetchall()
    return {"statistiques": stats}
