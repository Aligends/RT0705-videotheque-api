"""Comptes utilisateurs et authentification par jeton (Authorization: Bearer)."""
import re
from functools import wraps

import psycopg
from flask import Blueprint, current_app, g, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .erreurs import ErreurAPI, corps_json

bp = Blueprint("auth", __name__)

CHAMPS_UTILISATEUR = "id, nom, email, date_creation"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _serialiseur():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="jeton-api")


def creer_jeton(utilisateur_id):
    return _serialiseur().dumps({"id": utilisateur_id})


def connexion_requise(vue):
    """Refuse la requête (401) si elle ne porte pas un jeton valide."""

    @wraps(vue)
    def enveloppe(*args, **kwargs):
        entete = request.headers.get("Authorization", "")
        if not entete.startswith("Bearer "):
            raise ErreurAPI(401, "Authentification requise (en-tête Authorization: Bearer <jeton>).")
        try:
            contenu = _serialiseur().loads(
                entete[len("Bearer "):].strip(),
                max_age=current_app.config["DUREE_JETON_S"],
            )
        except BadSignature:  # couvre aussi les jetons expirés
            raise ErreurAPI(401, "Jeton invalide ou expiré.")
        utilisateur = get_db().execute(
            f"SELECT {CHAMPS_UTILISATEUR} FROM utilisateurs WHERE id = %s", (contenu["id"],)
        ).fetchone()
        if utilisateur is None:
            raise ErreurAPI(401, "Ce compte n'existe plus.")
        g.utilisateur = utilisateur
        return vue(*args, **kwargs)

    return enveloppe


def _reponse_session(utilisateur):
    return {
        "jeton": creer_jeton(utilisateur["id"]),
        "expire_dans_s": current_app.config["DUREE_JETON_S"],
        "utilisateur": utilisateur,
    }


@bp.post("/auth/inscription")
def inscription():
    donnees = corps_json()
    nom = str(donnees.get("nom") or "").strip()
    email = str(donnees.get("email") or "").strip().lower()
    mot_de_passe = donnees.get("mot_de_passe")

    details = {}
    if not nom or len(nom) > 100:
        details["nom"] = "Obligatoire (100 caractères au plus)."
    if not EMAIL.match(email) or len(email) > 255:
        details["email"] = "Adresse e-mail invalide."
    if not isinstance(mot_de_passe, str) or len(mot_de_passe) < 8:
        details["mot_de_passe"] = "8 caractères au minimum."
    if details:
        raise ErreurAPI(400, "Données invalides.", details)

    db = get_db()
    try:
        utilisateur = db.execute(
            f"INSERT INTO utilisateurs (nom, email, mot_de_passe) VALUES (%s, %s, %s) "
            f"RETURNING {CHAMPS_UTILISATEUR}",
            (nom, email, generate_password_hash(mot_de_passe)),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise ErreurAPI(409, "Un compte existe déjà avec cette adresse e-mail.")
    db.commit()
    return _reponse_session(utilisateur), 201


@bp.post("/auth/connexion")
def connexion():
    donnees = corps_json()
    email = str(donnees.get("email") or "").strip().lower()
    mot_de_passe = donnees.get("mot_de_passe")

    ligne = get_db().execute(
        f"SELECT {CHAMPS_UTILISATEUR}, mot_de_passe FROM utilisateurs WHERE email = %s", (email,)
    ).fetchone()
    if (ligne is None or not isinstance(mot_de_passe, str)
            or not check_password_hash(ligne["mot_de_passe"], mot_de_passe)):
        raise ErreurAPI(401, "Adresse e-mail ou mot de passe incorrect.")
    del ligne["mot_de_passe"]
    return _reponse_session(ligne)


@bp.get("/auth/moi")
@connexion_requise
def moi():
    return {"utilisateur": g.utilisateur}
