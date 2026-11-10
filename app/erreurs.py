"""Erreurs de l'API : toutes les réponses d'erreur sont au format JSON."""
import psycopg
from flask import jsonify, request
from werkzeug.exceptions import HTTPException


class ErreurAPI(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def reponse_erreur(code, message, details=None):
    erreur = {"code": code, "message": message}
    if details:
        erreur["details"] = details
    return jsonify({"erreur": erreur}), code


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
        return reponse_erreur(e.code, e.message, e.details)

    @app.errorhandler(HTTPException)
    def erreur_http(e):
        messages = {404: "Ressource introuvable.", 405: "Méthode non autorisée."}
        return reponse_erreur(e.code, messages.get(e.code, e.description))

    @app.errorhandler(psycopg.OperationalError)
    def base_indisponible(e):
        app.logger.error("Base de données injoignable : %s", e)
        return reponse_erreur(503, "Base de données indisponible.")

    @app.errorhandler(Exception)
    def erreur_interne(e):
        app.logger.exception(e)
        return reponse_erreur(500, "Erreur interne du serveur.")
