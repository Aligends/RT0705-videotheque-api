"""Tests de l'API sur une vraie base PostgreSQL.

La base désignée par DATABASE_URL_TEST doit contenir le schéma
(init/01_schema.sql du dépôt de la base). ATTENTION : ses tables sont vidées
avant chaque test.
"""
import os

import psycopg
import pytest
from psycopg.rows import dict_row

from app import create_app

URL = os.environ.get("DATABASE_URL_TEST")
MOT_DE_PASSE = "correct-cheval-pile"
FILM = {"titre": "Alien", "annee": 1979, "realisateur": "Ridley Scott", "duree_min": 117,
        "support": "physique", "format": "DVD", "genres": ["Science-fiction", "Horreur"]}
TABLES = "utilisateurs, tentatives_connexion, genres, films, film_genres, avis, prets, journal"


def nouvelle_app(**config):
    return create_app({"DATABASE_URL": URL, "TESTING": True, "SECRET_KEY": "c" * 32,
                       "INSCRIPTION": "ouverte", **config})


def sql(requete, parametres=()):
    """Exécute une requête directement dans la base (préparation ou vérification)."""
    with psycopg.connect(URL, row_factory=dict_row, autocommit=True) as connexion:
        curseur = connexion.execute(requete, parametres)
        return curseur.fetchall() if curseur.description else None


def creer_film(client, entetes, **champs):
    reponse = client.post("/api/v1/films", json={**FILM, **champs}, headers=entetes)
    assert reponse.status_code == 201, reponse.json
    return reponse.json["film"]


@pytest.fixture
def base():
    """Base de test vidée."""
    if not URL:
        pytest.skip("DATABASE_URL_TEST non définie")
    sql(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")


@pytest.fixture
def client(base):
    return nouvelle_app().test_client()


@pytest.fixture
def comptes(client):
    """Fabrique de comptes : renvoie les en-têtes d'authentification du compte créé."""
    def creer(nom, role="membre"):
        email = f"{nom.lower()}@exemple.fr"
        reponse = client.post("/api/v1/auth/inscription", json={
            "nom": nom, "email": email, "mot_de_passe": MOT_DE_PASSE})
        assert reponse.status_code == 201, reponse.json
        if role == "admin":
            sql("UPDATE utilisateurs SET role = 'admin' WHERE email = %s", (email,))
        return {"Authorization": "Bearer " + reponse.json["jeton"]}
    return creer


@pytest.fixture
def membre(comptes):
    return comptes("Membre")


@pytest.fixture
def autre(comptes):
    return comptes("Autre")


@pytest.fixture
def admin(comptes):
    return comptes("Admin", role="admin")
