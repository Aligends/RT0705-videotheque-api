"""Erreurs de l'API : toutes les réponses d'erreur sont au format JSON."""
import psycopg
from flask import jsonify, request
from werkzeug.exceptions import HTTPException

MESSAGES_HTTP = {
    400: "Requête invalide.",
    404: "Ressource introuvable.",
    405: "Méthode non autorisée.",
    413: "Requête trop volumineuse.",
    415: "Type de contenu non pris en charge : envoyez du JSON.",
}


class ErreurAPI(Exception):
    def __init__(self, code, message, details=None, entetes=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.entetes = entetes


def reponse_erreur(code, message, details=None, entetes=None):
    erreur = {"code": code, "message": message}
    if details:
        erreur["details"] = details
    reponse = jsonify({"erreur": erreur})
    reponse.status_code = code
    reponse.headers.update(entetes or {})
    return reponse


def corps_json():
    """Renvoie le corps JSON de la requête, qui doit être un objet."""
    donnees = request.get_json(silent=True)
    if not isinstance(donnees, dict):
        raise ErreurAPI(400, "Le corps de la requête doit être un objet JSON "
                             "(en-tête Content-Type: application/json).")
    return donnees


def init_app(app):
    @app.errorhandler(ErreurAPI)
    def erreur_api(e):
        return reponse_erreur(e.code, e.message, e.details, e.entetes)

    @app.errorhandler(HTTPException)
    def erreur_http(e):
        return reponse_erreur(e.code, MESSAGES_HTTP.get(e.code, e.description))

    @app.errorhandler(psycopg.DataError)
    def donnee_refusee(e):
        # Filet de sécurité : valeur que la validation a laissée passer mais
        # que la base refuse (trop longue, hors bornes...).
        app.logger.warning("Donnée refusée par la base : %s", e)
        return reponse_erreur(400, "Données invalides.")

    @app.errorhandler(psycopg.OperationalError)
    def base_indisponible(e):
        # Base injoignable, ou requête interrompue par le délai maximal.
        app.logger.error("Base de données indisponible : %s", e)
        return reponse_erreur(503, "Base de données indisponible.", entetes={"Retry-After": "5"})

    @app.errorhandler(Exception)
    def erreur_interne(e):
        # Le détail part dans les journaux du serveur, jamais dans la réponse.
        app.logger.exception(e)
        return reponse_erreur(500, "Erreur interne du serveur.")
