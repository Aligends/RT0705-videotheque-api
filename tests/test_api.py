"""Tests de l'API sur une vraie base PostgreSQL.

La base désignée par DATABASE_URL_TEST doit contenir le schéma
(init/01_schema.sql du dépôt de la base). ATTENTION : ses tables sont vidées.
"""
import os
from datetime import date, timedelta

import psycopg
import pytest

from app import create_app

URL = os.environ.get("DATABASE_URL_TEST")
pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL_TEST non définie")

FILM = {"titre": "Alien", "annee": 1979, "realisateur": "Ridley Scott", "duree_min": 117,
        "support": "physique", "format": "DVD", "genres": ["Science-fiction", "Horreur"]}


@pytest.fixture
def client():
    with psycopg.connect(URL) as connexion:
        connexion.execute(
            "TRUNCATE utilisateurs, genres, films, film_genres, prets RESTART IDENTITY CASCADE")
    app = create_app({"DATABASE_URL": URL, "TESTING": True})
    return app.test_client()


@pytest.fixture
def auth(client):
    reponse = client.post("/api/v1/auth/inscription", json={
        "nom": "Test", "email": "Test@Exemple.fr", "mot_de_passe": "motdepasse"})
    assert reponse.status_code == 201
    return {"Authorization": "Bearer " + reponse.json["jeton"]}


def creer(client, auth, **champs):
    reponse = client.post("/api/v1/films", json={**FILM, **champs}, headers=auth)
    assert reponse.status_code == 201, reponse.json
    return reponse.json["film"]


def test_sante(client):
    assert client.get("/api/v1/sante").json == {"statut": "ok"}


def test_erreurs_en_json(client):
    reponse = client.get("/api/v1/inconnu")
    assert reponse.status_code == 404 and reponse.json["erreur"]["code"] == 404
    assert client.get("/api/v1/films/999").json["erreur"]["message"] == "Film 999 introuvable."
    assert client.delete("/api/v1/films").status_code == 405


def test_authentification(client, auth):
    assert client.get("/api/v1/auth/moi", headers=auth).json["utilisateur"]["email"] == "test@exemple.fr"
    assert client.get("/api/v1/auth/moi").status_code == 401
    assert client.get("/api/v1/auth/moi", headers={"Authorization": "Bearer faux"}).status_code == 401

    identifiants = {"email": "test@exemple.fr", "mot_de_passe": "motdepasse"}
    reponse = client.post("/api/v1/auth/connexion", json=identifiants)
    assert reponse.status_code == 200 and "mot_de_passe" not in reponse.json["utilisateur"]
    assert client.post("/api/v1/auth/connexion",
                       json={**identifiants, "mot_de_passe": "mauvais"}).status_code == 401
    # e-mail déjà utilisé, puis données invalides
    assert client.post("/api/v1/auth/inscription",
                       json={"nom": "Bis", **identifiants}).status_code == 409
    reponse = client.post("/api/v1/auth/inscription", json={"nom": "", "email": "x", "mot_de_passe": "a"})
    assert reponse.status_code == 400
    assert set(reponse.json["erreur"]["details"]) == {"nom", "email", "mot_de_passe"}


def test_ecritures_protegees(client):
    assert client.post("/api/v1/films", json=FILM).status_code == 401
    assert client.put("/api/v1/films/1", json=FILM).status_code == 401
    assert client.delete("/api/v1/films/1").status_code == 401
    assert client.post("/api/v1/genres", json={"nom": "X"}).status_code == 401
    assert client.post("/api/v1/films/1/prets", json={"emprunteur": "X"}).status_code == 401


def test_cycle_de_vie_film(client, auth):
    film = creer(client, auth)
    assert film["genres"] == ["Horreur", "Science-fiction"]
    assert film["vu"] is False and film["disponible"] is True and film["ajoute_par"] == 1
    assert client.get(f"/api/v1/films/{film['id']}").json["film"] == film

    # PATCH : seuls les champs fournis changent
    reponse = client.patch(f"/api/v1/films/{film['id']}", json={"vu": True, "note": 9}, headers=auth)
    assert reponse.status_code == 200
    modifie = reponse.json["film"]
    assert (modifie["vu"], modifie["note"], modifie["annee"]) == (True, 9, 1979)
    assert modifie["genres"] == film["genres"]

    # PUT : remplacement complet, les champs absents sont vidés
    reponse = client.put(f"/api/v1/films/{film['id']}",
                         json={"titre": "Aliens", "support": "numerique"}, headers=auth)
    remplace = reponse.json["film"]
    assert (remplace["titre"], remplace["support"], remplace["annee"]) == ("Aliens", "numerique", None)
    assert remplace["genres"] == [] and remplace["vu"] is False

    assert client.delete(f"/api/v1/films/{film['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/films/{film['id']}").status_code == 404
    assert client.delete(f"/api/v1/films/{film['id']}", headers=auth).status_code == 404


def test_validation_film(client, auth):
    reponse = client.post("/api/v1/films", headers=auth, json={
        "titre": " ", "support": "betamax", "annee": "1979", "note": 11,
        "vu": "oui", "genres": "SF", "id": 5})
    assert reponse.status_code == 400
    assert set(reponse.json["erreur"]["details"]) == {
        "titre", "support", "annee", "note", "vu", "genres", "id"}
    assert client.post("/api/v1/films", headers=auth, data="pas du json").status_code == 400
    assert client.post("/api/v1/films", headers=auth, json=["liste"]).status_code == 400
    film = creer(client, auth)
    assert client.patch(f"/api/v1/films/{film['id']}", json={"titre": None},
                        headers=auth).status_code == 400


def test_recherche_filtres_pagination(client, auth):
    creer(client, auth)
    creer(client, auth, titre="Amélie", annee=2001, realisateur="Jean-Pierre Jeunet",
          genres=["Comédie"], vu=True, note=8)
    creer(client, auth, titre="Inception", annee=2010, realisateur="Christopher Nolan",
          support="numerique", genres=["science-fiction"], note=9)

    def titres(requete):
        reponse = client.get("/api/v1/films?" + requete)
        assert reponse.status_code == 200, reponse.json
        return [f["titre"] for f in reponse.json["films"]]

    assert titres("") == ["Alien", "Amélie", "Inception"]
    assert titres("q=nolan") == ["Inception"]
    assert titres("q=AMÉ") == ["Amélie"]
    assert titres("genre=Science-fiction") == ["Alien", "Inception"]  # genre réutilisé sans doublon
    assert titres("support=numerique") == ["Inception"]
    assert titres("vu=true") == ["Amélie"]
    assert titres("annee=1979") == ["Alien"]
    assert titres("tri=annee&ordre=desc") == ["Inception", "Amélie", "Alien"]
    assert titres("tri=note&ordre=desc") == ["Inception", "Amélie", "Alien"]  # sans note en dernier

    reponse = client.get("/api/v1/films?par_page=2&page=2").json
    assert [f["titre"] for f in reponse["films"]] == ["Inception"]
    assert reponse["pagination"] == {"page": 2, "par_page": 2, "total": 3, "pages": 2}

    for requete in ("tri=mot_de_passe", "page=0", "par_page=abc", "support=x", "vu=peut-etre"):
        assert client.get("/api/v1/films?" + requete).status_code == 400, requete


def test_genres(client, auth):
    creer(client, auth)
    assert client.post("/api/v1/genres", json={"nom": "Western"}, headers=auth).status_code == 201
    assert client.post("/api/v1/genres", json={"nom": "western"}, headers=auth).status_code == 409
    assert client.post("/api/v1/genres", json={"nom": ""}, headers=auth).status_code == 400
    genres = client.get("/api/v1/genres").json["genres"]
    assert [(g["nom"], g["nb_films"]) for g in genres] == [
        ("Horreur", 1), ("Science-fiction", 1), ("Western", 0)]

    horreur = genres[0]["id"]
    assert client.delete(f"/api/v1/genres/{horreur}", headers=auth).status_code == 204
    assert client.delete(f"/api/v1/genres/{horreur}", headers=auth).status_code == 404
    assert client.get("/api/v1/films/1").json["film"]["genres"] == ["Science-fiction"]


def test_prets(client, auth):
    film = creer(client, auth)
    url = f"/api/v1/films/{film['id']}/prets"
    hier = (date.today() - timedelta(days=1)).isoformat()

    assert client.post(url, json={}, headers=auth).status_code == 400
    assert client.post(url, json={"emprunteur": "Léa", "date_pret": "hier"},
                       headers=auth).status_code == 400
    assert client.post(url, json={"emprunteur": "Léa", "date_retour_prevue": hier},
                       headers=auth).status_code == 400

    reponse = client.post(url, json={"emprunteur": "Léa", "date_pret": "2020-01-01",
                                     "date_retour_prevue": "2020-01-15"}, headers=auth)
    assert reponse.status_code == 201
    pret = reponse.json["pret"]
    assert (pret["film_titre"], pret["en_cours"], pret["en_retard"]) == ("Alien", True, True)
    assert pret["date_pret"] == "2020-01-01"

    # le film n'est plus disponible et ne peut pas être prêté deux fois
    assert client.get(f"/api/v1/films/{film['id']}").json["film"]["disponible"] is False
    assert client.post(url, json={"emprunteur": "Tom"}, headers=auth).status_code == 409
    assert [f["titre"] for f in client.get("/api/v1/films?disponible=false").json["films"]] == ["Alien"]
    assert client.get("/api/v1/films?disponible=true").json["films"] == []
    assert len(client.get("/api/v1/prets?en_cours=true").json["prets"]) == 1

    retour = f"/api/v1/prets/{pret['id']}/retour"
    assert client.post(retour, json={"date_retour": "2019-12-31"}, headers=auth).status_code == 400
    reponse = client.post(retour, headers=auth)
    assert reponse.status_code == 200
    assert reponse.json["pret"]["date_retour"] == date.today().isoformat()
    assert reponse.json["pret"]["en_retard"] is False
    assert client.post(retour, headers=auth).status_code == 409

    assert client.get(f"/api/v1/films/{film['id']}").json["film"]["disponible"] is True
    assert client.get("/api/v1/prets?en_cours=true").json["prets"] == []
    assert len(client.get(url).json["prets"]) == 1
    assert client.get("/api/v1/films/999/prets").status_code == 404

    numerique = creer(client, auth, titre="Fichier", support="numerique")
    assert client.post(f"/api/v1/films/{numerique['id']}/prets",
                       json={"emprunteur": "Léa"}, headers=auth).status_code == 409

    assert client.delete(f"/api/v1/prets/{pret['id']}", headers=auth).status_code == 204
    assert client.get("/api/v1/prets").json["prets"] == []


def test_statistiques(client, auth):
    vide = client.get("/api/v1/statistiques").json["statistiques"]
    assert (vide["nb_films"], vide["duree_totale_min"], vide["note_moyenne"]) == (0, 0, None)

    creer(client, auth, note=8, vu=True)
    creer(client, auth, titre="Inception", support="numerique", duree_min=148, note=9,
          genres=["Science-fiction"])
    client.post("/api/v1/films/1/prets", json={"emprunteur": "Léa"}, headers=auth)

    stats = client.get("/api/v1/statistiques").json["statistiques"]
    assert stats == {
        "nb_films": 2, "nb_physiques": 1, "nb_numeriques": 1, "nb_vus": 1, "nb_a_voir": 1,
        "duree_totale_min": 265, "note_moyenne": 8.5, "nb_prets_en_cours": 1,
        "films_par_genre": [{"genre": "Science-fiction", "nb_films": 2},
                            {"genre": "Horreur", "nb_films": 1}],
    }
