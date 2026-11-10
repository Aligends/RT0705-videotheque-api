"""Comptes, authentification par jeton signé et contrôle des rôles."""
import hashlib
import math
import re
import secrets
from functools import wraps

import psycopg
from flask import Blueprint, current_app, g, request
from itsdangerous import BadData, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from .audit import journaliser
from .db import get_db
from .erreurs import ErreurAPI, corps_json
from .validation import Validateur

bp = Blueprint("auth", __name__)

CHAMPS_UTILISATEUR = "id, nom, email, role, actif, date_creation, derniere_connexion"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOT_DE_PASSE_MIN, MOT_DE_PASSE_MAX = 10, 128
MOTS_DE_PASSE_REFUSES = frozenset({
    "motdepasse", "motdepasse1", "motdepasse123", "password12", "password123",
    "azertyuiop", "qwertyuiop", "1234567890", "0123456789", "0987654321",
    "videotheque", "administrateur", "admin12345", "bonjour123", "iloveyou123",
})
# Ces deux routes servent justement à obtenir un jeton : un ancien jeton
# envoyé avec la requête y est ignoré.
ROUTES_SANS_JETON = frozenset({"auth.inscription", "auth.connexion"})
DEMANDE_JETON = {"WWW-Authenticate": 'Bearer realm="videotheque"'}

_empreinte_factice = None


# --- jetons -------------------------------------------------------------

def _serialiseur():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"], salt="jeton-api",
        signer_kwargs={"key_derivation": "hmac", "digest_method": hashlib.sha256},
    )


def creer_jeton(utilisateur_id, version):
    """Jeton signé (HMAC-SHA256) et horodaté : identifiant + version du compte."""
    return _serialiseur().dumps({"id": utilisateur_id, "v": version})


def identifier_utilisateur():
    """Avant chaque requête : lit le jeton éventuel et charge l'utilisateur.

    Sans en-tête Authorization, la requête est anonyme (g.utilisateur = None).
    Un jeton présent mais invalide, expiré, révoqué ou lié à un compte
    désactivé est toujours refusé (401), même sur une route publique.
    """
    g.utilisateur = None
    entete = request.headers.get("Authorization")
    if entete is None or request.endpoint in ROUTES_SANS_JETON:
        return
    if not entete.startswith("Bearer "):
        raise ErreurAPI(401, "En-tête Authorization invalide : « Bearer <jeton> » attendu.",
                        entetes=DEMANDE_JETON)
    try:
        contenu = _serialiseur().loads(entete[len("Bearer "):].strip(),
                                       max_age=current_app.config["DUREE_JETON_S"])
    except BadData:   # signature fausse, jeton altéré ou expiré
        contenu = None
    ligne = None
    if isinstance(contenu, dict) and isinstance(contenu.get("id"), int):
        ligne = get_db().execute(
            f"SELECT {CHAMPS_UTILISATEUR}, version_jeton FROM utilisateurs WHERE id = %s",
            (contenu["id"],),
        ).fetchone()
    if ligne is None or not ligne["actif"] or ligne.pop("version_jeton") != contenu.get("v"):
        raise ErreurAPI(401, "Jeton invalide ou expiré.", entetes=DEMANDE_JETON)
    g.utilisateur = ligne


def connexion_requise(vue):
    """Réserve la route aux utilisateurs connectés (401 sinon)."""

    @wraps(vue)
    def enveloppe(*args, **kwargs):
        if g.utilisateur is None:
            raise ErreurAPI(401, "Authentification requise (en-tête Authorization: Bearer <jeton>).",
                            entetes=DEMANDE_JETON)
        return vue(*args, **kwargs)

    return enveloppe


def admin_requis(vue):
    """Réserve la route aux administrateurs (401 sans jeton, 403 sinon)."""

    @wraps(vue)
    @connexion_requise
    def enveloppe(*args, **kwargs):
        if g.utilisateur["role"] != "admin":
            raise ErreurAPI(403, "Action réservée aux administrateurs.")
        return vue(*args, **kwargs)

    return enveloppe


# --- mots de passe ------------------------------------------------------

def controler_mot_de_passe(mot_de_passe, email="", nom=""):
    """Renvoie un message si le mot de passe est refusé, None s'il est accepté."""
    if not isinstance(mot_de_passe, str) or len(mot_de_passe) < MOT_DE_PASSE_MIN:
        return f"{MOT_DE_PASSE_MIN} caractères au minimum."
    if len(mot_de_passe) > MOT_DE_PASSE_MAX:
        return f"{MOT_DE_PASSE_MAX} caractères au plus."
    if "\x00" in mot_de_passe:
        return "Contient des caractères non autorisés."
    bas = mot_de_passe.lower()
    if (bas in MOTS_DE_PASSE_REFUSES or len(set(bas)) < 5
            or bas in (email.lower(), nom.lower())):
        return "Mot de passe trop simple ou trop courant."
    return None


def _verifier_mot_de_passe(empreinte, mot_de_passe):
    """Compare le mot de passe à l'empreinte du compte.

    Si le compte n'existe pas (empreinte None), une empreinte factice est
    tout de même calculée : le temps de réponse ne révèle pas quelles
    adresses ont un compte.
    """
    global _empreinte_factice
    if empreinte is None:
        if _empreinte_factice is None:
            _empreinte_factice = generate_password_hash(secrets.token_hex(16))
        check_password_hash(_empreinte_factice, mot_de_passe)
        return False
    return check_password_hash(empreinte, mot_de_passe)


def _reponse_session(utilisateur, version):
    return {
        "jeton": creer_jeton(utilisateur["id"], version),
        "expire_dans_s": current_app.config["DUREE_JETON_S"],
        "utilisateur": utilisateur,
    }


# --- routes -------------------------------------------------------------

@bp.post("/auth/inscription")
def inscription():
    """Crée un compte « membre ». Selon la configuration, le compte est
    utilisable tout de suite ou doit être activé par un administrateur."""
    mode = current_app.config["INSCRIPTION"]
    if mode == "fermee":
        raise ErreurAPI(403, "Les inscriptions sont fermées.")

    v = Validateur(corps_json(), ("nom", "email", "mot_de_passe"))
    nom = v.texte("nom", 100, obligatoire=True)
    email = (v.texte("email", 255, obligatoire=True) or "").lower()
    if email and not EMAIL.match(email):
        v.erreur("email", "Adresse e-mail invalide.")
    mot_de_passe = v.donnees.get("mot_de_passe")
    if message := controler_mot_de_passe(mot_de_passe, email, nom or ""):
        v.erreur("mot_de_passe", message)
    v.verifier()

    actif = mode == "ouverte"
    db = get_db()
    try:
        utilisateur = db.execute(
            f"INSERT INTO utilisateurs (nom, email, mot_de_passe, actif) VALUES (%s, %s, %s, %s) "
            f"RETURNING {CHAMPS_UTILISATEUR}",
            (nom, email, generate_password_hash(mot_de_passe), actif),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise ErreurAPI(409, "Un compte existe déjà avec cette adresse e-mail.")
    journaliser("inscription", cible=email, utilisateur=utilisateur,
                details=None if actif else "en attente de validation")
    db.commit()
    if not actif:
        return {"utilisateur": utilisateur, "en_attente": True}, 201
    return {**_reponse_session(utilisateur, 0), "en_attente": False}, 201


@bp.post("/auth/connexion")
def connexion():
    """Vérifie les identifiants et renvoie un jeton.

    Après MAX_ECHECS_CONNEXION échecs en FENETRE_ECHECS_S secondes pour une
    même adresse, les tentatives sont refusées (429) jusqu'à ce que la plus
    ancienne sorte de la fenêtre. Le comptage porte sur l'adresse saisie,
    qu'un compte existe ou non, pour ne rien révéler.
    """
    refus = ErreurAPI(401, "Adresse e-mail ou mot de passe incorrect.")
    donnees = corps_json()
    email, mot_de_passe = donnees.get("email"), donnees.get("mot_de_passe")
    if not isinstance(email, str) or not isinstance(mot_de_passe, str):
        raise refus
    email = email.strip().lower()
    if len(email) > 255 or not EMAIL.match(email) or len(mot_de_passe) > MOT_DE_PASSE_MAX:
        raise refus

    db = get_db()
    fenetre = current_app.config["FENETRE_ECHECS_S"]
    db.execute("DELETE FROM tentatives_connexion "
               "WHERE date_tentative < now() - make_interval(secs => %s)", (fenetre,))
    etat = db.execute(
        "SELECT count(*) AS echecs, "
        "       extract(epoch FROM min(date_tentative) + make_interval(secs => %s) - now()) AS attente "
        "FROM tentatives_connexion WHERE email = %s", (fenetre, email),
    ).fetchone()
    if etat["echecs"] >= current_app.config["MAX_ECHECS_CONNEXION"]:
        db.commit()
        attente = max(1, math.ceil(etat["attente"]))
        raise ErreurAPI(429, f"Trop de tentatives. Réessayez dans {math.ceil(attente / 60)} min.",
                        entetes={"Retry-After": str(attente)})

    ligne = db.execute(
        f"SELECT {CHAMPS_UTILISATEUR}, mot_de_passe, version_jeton FROM utilisateurs "
        f"WHERE email = %s", (email,),
    ).fetchone()
    if not _verifier_mot_de_passe(ligne and ligne["mot_de_passe"], mot_de_passe):
        db.execute("INSERT INTO tentatives_connexion (email) VALUES (%s)", (email,))
        journaliser("connexion_echec", cible=email, utilisateur=None)
        db.commit()
        raise refus
    if not ligne["actif"]:
        raise ErreurAPI(403, "Ce compte est en attente de validation ou a été désactivé.")

    del ligne["mot_de_passe"]
    version = ligne.pop("version_jeton")
    db.execute("DELETE FROM tentatives_connexion WHERE email = %s", (email,))
    ligne["derniere_connexion"] = db.execute(
        "UPDATE utilisateurs SET derniere_connexion = now() WHERE id = %s "
        "RETURNING derniere_connexion", (ligne["id"],),
    ).fetchone()["derniere_connexion"]
    journaliser("connexion", utilisateur=ligne)
    db.commit()
    return _reponse_session(ligne, version)


@bp.get("/auth/moi")
@connexion_requise
def moi():
    return {"utilisateur": g.utilisateur}


@bp.patch("/auth/moi")
@connexion_requise
def modifier_profil():
    v = Validateur(corps_json(), ("nom",))
    nom = v.texte("nom", 100, obligatoire=True)
    v.verifier()
    db = get_db()
    utilisateur = db.execute(
        f"UPDATE utilisateurs SET nom = %s WHERE id = %s RETURNING {CHAMPS_UTILISATEUR}",
        (nom, g.utilisateur["id"]),
    ).fetchone()
    db.commit()
    return {"utilisateur": utilisateur}


@bp.post("/auth/mot-de-passe")
@connexion_requise
def changer_mot_de_passe():
    """Change le mot de passe, révoque tous les jetons émis et en renvoie un nouveau."""
    donnees = corps_json()
    v = Validateur(donnees, ("ancien", "nouveau"))
    ancien, nouveau = donnees.get("ancien"), donnees.get("nouveau")
    db = get_db()
    empreinte = db.execute("SELECT mot_de_passe FROM utilisateurs WHERE id = %s",
                           (g.utilisateur["id"],)).fetchone()["mot_de_passe"]
    if (not isinstance(ancien, str) or len(ancien) > MOT_DE_PASSE_MAX
            or not check_password_hash(empreinte, ancien)):
        v.erreur("ancien", "Mot de passe actuel incorrect.")
    if message := controler_mot_de_passe(nouveau, g.utilisateur["email"], g.utilisateur["nom"]):
        v.erreur("nouveau", message)
    elif nouveau == ancien:
        v.erreur("nouveau", "Le nouveau mot de passe doit être différent de l'ancien.")
    v.verifier()

    version = db.execute(
        "UPDATE utilisateurs SET mot_de_passe = %s, version_jeton = version_jeton + 1 "
        "WHERE id = %s RETURNING version_jeton",
        (generate_password_hash(nouveau), g.utilisateur["id"]),
    ).fetchone()["version_jeton"]
    journaliser("mot_de_passe_modifie")
    db.commit()
    return _reponse_session(g.utilisateur, version)


@bp.post("/auth/deconnexion")
@connexion_requise
def deconnexion():
    """Révoque tous les jetons du compte : le jeton présenté cesse de fonctionner."""
    db = get_db()
    db.execute("UPDATE utilisateurs SET version_jeton = version_jeton + 1 WHERE id = %s",
               (g.utilisateur["id"],))
    journaliser("deconnexion")
    db.commit()
    return "", 204
