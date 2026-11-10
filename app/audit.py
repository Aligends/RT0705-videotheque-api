"""Écriture dans le journal d'audit."""
from flask import g

from .db import get_db

_UTILISATEUR_COURANT = object()


def journaliser(action, cible=None, details=None, utilisateur=_UTILISATEUR_COURANT):
    """Ajoute une ligne au journal, dans la transaction en cours.

    La ligne n'est donc conservée que si l'opération qu'elle décrit est
    validée. Par défaut l'auteur est l'utilisateur de la requête.
    """
    if utilisateur is _UTILISATEUR_COURANT:
        utilisateur = g.get("utilisateur")
    get_db().execute(
        "INSERT INTO journal (utilisateur_id, utilisateur_nom, action, cible, details) "
        "VALUES (%s, %s, %s, %s, %s)",
        (utilisateur["id"] if utilisateur else None,
         utilisateur["nom"] if utilisateur else None,
         action, cible[:300] if cible else None, details),
    )
