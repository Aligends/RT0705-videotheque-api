"""Chiffres clés de la vidéothèque."""
from flask import Blueprint, g

from .db import get_db

bp = Blueprint("statistiques", __name__)


@bp.get("/statistiques")
def statistiques():
    """Chiffres publics, complétés par ceux de l'utilisateur s'il est connecté."""
    db = get_db()
    stats = db.execute("""
        SELECT count(*)                                      AS nb_films,
               count(*) FILTER (WHERE support = 'physique')  AS nb_physiques,
               count(*) FILTER (WHERE support = 'numerique') AS nb_numeriques,
               COALESCE(sum(duree_min), 0)::int              AS duree_totale_min
        FROM films
    """).fetchone()
    stats.update(db.execute(
        "SELECT round(avg(note), 1)::float AS note_moyenne, count(note) AS nb_notes FROM avis"
    ).fetchone())
    stats["nb_prets_en_cours"] = db.execute(
        "SELECT count(*) AS n FROM prets WHERE date_retour IS NULL"
    ).fetchone()["n"]
    stats["films_par_genre"] = db.execute(
        "SELECT ge.nom AS genre, count(*) AS nb_films "
        "FROM genres ge JOIN film_genres fg ON fg.genre_id = ge.id "
        "GROUP BY ge.nom ORDER BY nb_films DESC, lower(ge.nom)"
    ).fetchall()
    stats["films_par_decennie"] = db.execute(
        "SELECT (annee / 10) * 10 AS decennie, count(*) AS nb_films "
        "FROM films WHERE annee IS NOT NULL GROUP BY 1 ORDER BY 1"
    ).fetchall()
    stats["mieux_notes"] = db.execute(
        "SELECT f.id, f.titre, round(avg(a.note), 1)::float AS note_moyenne, "
        "       count(a.note) AS nb_notes "
        "FROM films f JOIN avis a ON a.film_id = f.id WHERE a.note IS NOT NULL "
        "GROUP BY f.id ORDER BY avg(a.note) DESC, count(a.note) DESC, lower(f.titre) LIMIT 5"
    ).fetchall()

    if g.utilisateur:
        moi = db.execute(
            "SELECT count(*) AS nb_vus, COALESCE(sum(f.duree_min), 0)::int AS duree_vue_min "
            "FROM avis a JOIN films f ON f.id = a.film_id WHERE a.utilisateur_id = %s",
            (g.utilisateur["id"],),
        ).fetchone()
        moi["nb_a_voir"] = stats["nb_films"] - moi["nb_vus"]
        stats["mes_statistiques"] = moi
    return {"statistiques": stats}
