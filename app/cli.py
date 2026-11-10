"""Commandes d'administration : flask --app app <commande>."""
import os
import time

import click
import psycopg
from werkzeug.security import generate_password_hash

from .audit import journaliser
from .auth import EMAIL, controler_mot_de_passe
from .db import fermer_db, get_db


def _attendre_la_base(essais=30):
    """La base peut démarrer après l'API : on patiente jusqu'à 30 secondes."""
    for essai in range(essais):
        try:
            return get_db()
        except psycopg.OperationalError:
            fermer_db()
            if essai == essais - 1:
                raise
            time.sleep(1)


@click.command("init-admin")
def init_admin():
    """Crée le premier administrateur à partir de ADMIN_EMAIL et ADMIN_MOT_DE_PASSE.

    Sans effet si ces variables sont absentes ou si le compte existe déjà :
    la commande peut donc être relancée à chaque démarrage du conteneur, et
    un mot de passe changé depuis le site n'est jamais écrasé.
    """
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    mot_de_passe = os.environ.get("ADMIN_MOT_DE_PASSE", "")
    if not email or not mot_de_passe:
        click.echo("ADMIN_EMAIL ou ADMIN_MOT_DE_PASSE absent : aucun administrateur créé.")
        return
    if not EMAIL.match(email):
        raise click.ClickException("ADMIN_EMAIL n'est pas une adresse e-mail valide.")
    if message := controler_mot_de_passe(mot_de_passe, email):
        raise click.ClickException(f"ADMIN_MOT_DE_PASSE refusé : {message}")

    db = _attendre_la_base()
    cree = db.execute(
        "INSERT INTO utilisateurs (nom, email, mot_de_passe, role, actif) "
        "VALUES ('Administrateur', %s, %s, 'admin', TRUE) "
        "ON CONFLICT (email) DO NOTHING RETURNING id, nom",
        (email, generate_password_hash(mot_de_passe)),
    ).fetchone()
    if cree:
        journaliser("inscription", cible=email, utilisateur=cree,
                    details="administrateur créé au démarrage")
        db.commit()
        click.echo(f"Administrateur {email} créé.")
    else:
        click.echo(f"Le compte {email} existe déjà : rien n'est modifié.")


@click.command("mot-de-passe")
@click.argument("email")
def reinitialiser_mot_de_passe(email):
    """Remplace le mot de passe du compte EMAIL (mot de passe oublié).

    Le compte est réactivé et tous ses jetons sont révoqués.
    """
    email = email.strip().lower()
    db = get_db()
    compte = db.execute("SELECT id, nom FROM utilisateurs WHERE email = %s", (email,)).fetchone()
    if compte is None:
        raise click.ClickException(f"Aucun compte pour {email}.")
    mot_de_passe = click.prompt("Nouveau mot de passe", hide_input=True, confirmation_prompt=True)
    if message := controler_mot_de_passe(mot_de_passe, email, compte["nom"]):
        raise click.ClickException(message)
    db.execute(
        "UPDATE utilisateurs SET mot_de_passe = %s, version_jeton = version_jeton + 1, "
        "actif = TRUE WHERE id = %s", (generate_password_hash(mot_de_passe), compte["id"]))
    db.execute("DELETE FROM tentatives_connexion WHERE email = %s", (email,))
    journaliser("mot_de_passe_modifie", cible=email, utilisateur=None,
                details="réinitialisé en ligne de commande")
    db.commit()
    click.echo(f"Mot de passe de {email} modifié.")


def init_app(app):
    app.cli.add_command(init_admin)
    app.cli.add_command(reinitialiser_mot_de_passe)
