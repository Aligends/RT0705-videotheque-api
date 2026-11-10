"""Administration des comptes (réservée aux administrateurs)."""
from flask import Blueprint, g

from .audit import journaliser
from .auth import CHAMPS_UTILISATEUR, admin_requis
from .db import get_db
from .erreurs import ErreurAPI, corps_json
from .validation import Validateur, bloc_pagination, pagination, parametre_booleen

bp = Blueprint("utilisateurs", __name__)

ROLES = ("admin", "membre")


def _autre_compte(utilisateur_id):
    """Un administrateur ne peut pas changer ses propres droits ni se supprimer :
    il reste ainsi toujours au moins un administrateur actif."""
    if utilisateur_id == g.utilisateur["id"]:
        raise ErreurAPI(409, "Vous ne pouvez pas modifier ni supprimer votre propre compte ici.")


@bp.get("/utilisateurs")
@admin_requis
def lister_utilisateurs():
    """Liste paginée ; ?actif=false ne garde que les comptes en attente ou désactivés."""
    actif = parametre_booleen("actif")
    ou, parametres = ("", [])
    if actif is not None:
        ou, parametres = " WHERE actif = %s", [actif]
    page, par_page, decalage = pagination(50)
    db = get_db()
    total = db.execute("SELECT count(*) AS n FROM utilisateurs" + ou, parametres).fetchone()["n"]
    utilisateurs = db.execute(
        f"SELECT {CHAMPS_UTILISATEUR} FROM utilisateurs{ou} "
        f"ORDER BY actif, lower(nom), id LIMIT %s OFFSET %s",
        [*parametres, par_page, decalage],
    ).fetchall()
    return {"utilisateurs": utilisateurs, "pagination": bloc_pagination(page, par_page, total)}


@bp.patch("/utilisateurs/<int:utilisateur_id>")
@admin_requis
def modifier_utilisateur(utilisateur_id):
    """Change le rôle d'un compte ou l'active / le désactive.

    Tous les jetons du compte sont révoqués : le nouveau niveau de droits
    s'applique immédiatement.
    """
    _autre_compte(utilisateur_id)
    v = Validateur(corps_json(), ("role", "actif"))
    role, actif = v.choix("role", ROLES), v.booleen("actif")
    if role is None and actif is None and not v.erreurs:
        v.erreur("role", "Indiquez « role » ou « actif ».")
    v.verifier()

    db = get_db()
    avant = db.execute("SELECT nom, email, role, actif FROM utilisateurs WHERE id = %s",
                       (utilisateur_id,)).fetchone()
    if avant is None:
        raise ErreurAPI(404, f"Utilisateur {utilisateur_id} introuvable.")
    apres = db.execute(
        f"UPDATE utilisateurs SET role = coalesce(%s, role), actif = coalesce(%s, actif), "
        f"version_jeton = version_jeton + 1 WHERE id = %s RETURNING {CHAMPS_UTILISATEUR}",
        (role, actif, utilisateur_id),
    ).fetchone()
    changements = []
    if apres["role"] != avant["role"]:
        changements.append(f"rôle : {avant['role']} → {apres['role']}")
    if apres["actif"] != avant["actif"]:
        changements.append("compte activé" if apres["actif"] else "compte désactivé")
    journaliser("utilisateur_modifie", cible=avant["email"],
                details=", ".join(changements) or "aucun changement")
    db.commit()
    return {"utilisateur": apres}


@bp.delete("/utilisateurs/<int:utilisateur_id>")
@admin_requis
def supprimer_utilisateur(utilisateur_id):
    """Supprime le compte et ses avis ; les films qu'il a ajoutés sont conservés."""
    _autre_compte(utilisateur_id)
    db = get_db()
    ligne = db.execute("DELETE FROM utilisateurs WHERE id = %s RETURNING email",
                       (utilisateur_id,)).fetchone()
    if ligne is None:
        raise ErreurAPI(404, f"Utilisateur {utilisateur_id} introuvable.")
    journaliser("utilisateur_supprime", cible=ligne["email"])
    db.commit()
    return "", 204
