"""API REST de la vidéothèque (tiers d'accès aux données)."""
import os
from datetime import date, datetime

from flask import Flask
from flask.json.provider import DefaultJSONProvider

from . import auth, db, erreurs, films, genres, prets, statistiques

PREFIXE = "/api/v1"


class FournisseurJSON(DefaultJSONProvider):
    """Dates au format ISO 8601 et accents conservés tels quels."""

    ensure_ascii = False
    sort_keys = False

    def default(self, o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return super().default(o)


def create_app(config=None):
    app = Flask(__name__)
    app.json = FournisseurJSON(app)
    app.config.update(
        DATABASE_URL=os.environ.get(
            "DATABASE_URL",
            "postgresql://videotheque:videotheque@localhost:5432/videotheque",
        ),
        SECRET_KEY=os.environ.get("SECRET_KEY", "cle-de-developpement-a-changer"),
        DUREE_JETON_S=int(os.environ.get("DUREE_JETON_S", 8 * 3600)),
    )
    if config:
        app.config.update(config)

    db.init_app(app)
    erreurs.init_app(app)
    for module in (auth, films, genres, prets, statistiques):
        app.register_blueprint(module.bp, url_prefix=PREFIXE)

    @app.get(PREFIXE + "/sante")
    def sante():
        """Vérifie que l'API répond et que la base est joignable."""
        db.get_db().execute("SELECT 1")
        return {"statut": "ok"}

    return app
