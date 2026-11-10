"""Consultation du journal d'audit (réservée aux administrateurs)."""
from flask import Blueprint, request

from .auth import admin_requis
from .db import get_db
from .validation import bloc_pagination, pagination

bp = Blueprint("journal", __name__)


@bp.get("/journal")
@admin_requis
def lire_journal():
    """Entrées de la plus récente à la plus ancienne ; ?action= filtre par type."""
    action = request.args.get("action", "").strip()
    ou, parametres = ("", [])
    if action:
        ou, parametres = " WHERE action = %s", [action[:40]]
    page, par_page, decalage = pagination(50)
    db = get_db()
    total = db.execute("SELECT count(*) AS n FROM journal" + ou, parametres).fetchone()["n"]
    entrees = db.execute(
        "SELECT id, date_action, utilisateur_id, utilisateur_nom, action, cible, details "
        f"FROM journal{ou} ORDER BY id DESC LIMIT %s OFFSET %s",
        [*parametres, par_page, decalage],
    ).fetchall()
    actions = [ligne["action"] for ligne in
               db.execute("SELECT DISTINCT action FROM journal ORDER BY action")]
    return {"journal": entrees, "actions": actions,
            "pagination": bloc_pagination(page, par_page, total)}
