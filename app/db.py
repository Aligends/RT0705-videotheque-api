"""Connexion à la base PostgreSQL : une connexion par requête HTTP."""
import psycopg
from flask import current_app, g
from psycopg.rows import dict_row


def get_db():
    """Renvoie la connexion de la requête courante (ouverte à la demande).

    Les lignes sont renvoyées sous forme de dictionnaires. Les écritures
    doivent être validées explicitement par ``commit()`` ; tout ce qui n'est
    pas validé est annulé à la fin de la requête.
    """
    if "db" not in g:
        g.db = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)
    return g.db


def fermer_db(_exception=None):
    connexion = g.pop("db", None)
    if connexion is not None:
        connexion.rollback()
        connexion.close()


def init_app(app):
    app.teardown_appcontext(fermer_db)
