"""API REST de la vidéothèque (tiers d'accès aux données)."""
import logging
import os
import secrets
from datetime import date, datetime

from flask import Flask
from flask.json.provider import DefaultJSONProvider

from . import (auth, avis, cli, db, echanges, erreurs, films, genres, journal, prets,
               statistiques, utilisateurs)

PREFIXE = "/api/v1"
MODES_INSCRIPTION = ("ouverte", "validation", "fermee")
LONGUEUR_MIN_CLE = 32


class FournisseurJSON(DefaultJSONProvider):
    """Dates au format ISO 8601 et accents conservés tels quels."""

    ensure_ascii = False
    sort_keys = False

    def default(self, o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return super().default(o)


def _verifier_configuration(app):
    """Refuse de démarrer avec une configuration dangereuse ou incomplète."""
    if not app.config["DATABASE_URL"]:
        raise RuntimeError("La variable DATABASE_URL doit être définie.")
    if app.config["INSCRIPTION"] not in MODES_INSCRIPTION:
        raise RuntimeError(f"INSCRIPTION doit valoir l'une de : {', '.join(MODES_INSCRIPTION)}.")
    if len(app.config["SECRET_KEY"] or "") < LONGUEUR_MIN_CLE:
        if not (app.debug or app.testing):
            raise RuntimeError(
                f"SECRET_KEY doit contenir au moins {LONGUEUR_MIN_CLE} caractères aléatoires : "
                "sans elle, n'importe qui pourrait fabriquer des jetons.")
        # En développement seulement : clé jetable, les jetons ne survivent pas au redémarrage.
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning("SECRET_KEY absente : clé temporaire générée (mode développement).")


def create_app(config=None):
    app = Flask(__name__)
    app.json = FournisseurJSON(app)
    app.config.update(
        DATABASE_URL=os.environ.get("DATABASE_URL", ""),
        SECRET_KEY=os.environ.get("SECRET_KEY", ""),
        # Durée de validité d'un jeton, en secondes (4 h par défaut).
        DUREE_JETON_S=int(os.environ.get("DUREE_JETON_S", 4 * 3600)),
        # ouverte : compte utilisable tout de suite ; validation : un administrateur
        # doit l'activer ; fermee : aucune inscription.
        INSCRIPTION=os.environ.get("INSCRIPTION", "validation"),
        # Verrouillage : nombre d'échecs tolérés par adresse, sur une fenêtre glissante.
        MAX_ECHECS_CONNEXION=int(os.environ.get("MAX_ECHECS_CONNEXION", 5)),
        FENETRE_ECHECS_S=int(os.environ.get("FENETRE_ECHECS_S", 15 * 60)),
        # Taille maximale d'une requête : au-delà, réponse 413.
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if config:
        app.config.update(config)
    app.logger.setLevel(logging.INFO)
    _verifier_configuration(app)

    db.init_app(app)
    erreurs.init_app(app)
    cli.init_app(app)
    app.before_request(auth.identifier_utilisateur)
    for module in (auth, avis, echanges, films, genres, journal, prets, statistiques,
                   utilisateurs):
        app.register_blueprint(module.bp, url_prefix=PREFIXE)

    @app.get(PREFIXE + "/sante")
    def sante():
        """Vérifie que l'API répond et que la base est joignable."""
        db.get_db().execute("SELECT 1")
        return {"statut": "ok"}

    @app.after_request
    def entetes_de_securite(reponse):
        # Les réponses sont des données : ni mise en cache, ni interprétation
        # comme une page par un navigateur.
        reponse.headers.setdefault("Cache-Control", "no-store")
        reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
        reponse.headers.setdefault("Content-Security-Policy",
                                   "default-src 'none'; frame-ancestors 'none'")
        return reponse

    return app
