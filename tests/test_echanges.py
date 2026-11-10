"""Export et import du catalogue au format JSON."""
from conftest import FILM, creer_film, sql


def test_export(client, membre):
    creer_film(client, membre)
    creer_film(client, membre, titre="Amélie", annee=2001, genres=["Comédie"])
    assert client.get("/api/v1/export").status_code == 401

    export = client.get("/api/v1/export", headers=membre).json
    assert (export["format"], export["version"]) == ("videotheque-rt0705", 1)
    assert [f["titre"] for f in export["films"]] == ["Alien", "Amélie"]
    # uniquement le catalogue : ni identifiants, ni comptes, ni avis, ni prêts
    assert set(export["films"][0]) == {
        "titre", "titre_original", "annee", "realisateur", "duree_min", "synopsis",
        "support", "format", "emplacement", "affiche_url", "genres"}
    assert export["films"][0]["genres"] == ["Horreur", "Science-fiction"]


def test_import_reserve_aux_administrateurs(client, membre):
    assert client.post("/api/v1/import", json={"films": [FILM]}).status_code == 401
    assert client.post("/api/v1/import", json={"films": [FILM]}, headers=membre).status_code == 403
    assert sql("SELECT count(*) AS n FROM films")[0]["n"] == 0


def test_aller_retour_export_import(client, membre, admin):
    creer_film(client, membre)
    creer_film(client, membre, titre="Amélie", annee=2001, genres=["Comédie"],
               synopsis="Une serveuse de Montmartre.")
    export = client.get("/api/v1/export", headers=membre).json

    # réimporté tel quel : tout est déjà présent, rien n'est dupliqué
    reponse = client.post("/api/v1/import", json=export, headers=admin)
    assert reponse.status_code == 200
    assert reponse.json == {"importes": 0, "ignores": ["Alien", "Amélie"]}

    # dans une vidéothèque vidée : le catalogue est reconstitué à l'identique
    sql("TRUNCATE films, genres RESTART IDENTITY CASCADE")
    reponse = client.post("/api/v1/import", json=export, headers=admin)
    assert reponse.json == {"importes": 2, "ignores": []}
    assert client.get("/api/v1/export", headers=membre).json["films"] == export["films"]
    assert client.get("/api/v1/films/1").json["film"]["ajoute_par_nom"] == "Admin"


def test_import_tout_ou_rien(client, admin):
    films = [FILM, {"titre": "", "support": "betamax"}, "pas un objet",
             {**FILM, "titre": "Autre", "id": 12}]
    reponse = client.post("/api/v1/import", json={"films": films}, headers=admin)
    assert reponse.status_code == 400
    assert set(reponse.json["erreur"]["details"]) == {
        "films[1].titre", "films[1].support", "films[2]", "films[3].id"}
    assert sql("SELECT count(*) AS n FROM films")[0]["n"] == 0

    for corps in ({}, {"films": []}, {"films": "tous"}, {"films": [FILM] * 501}):
        assert client.post("/api/v1/import", json=corps, headers=admin).status_code == 400
    # doublons à l'intérieur d'un même fichier : un seul est gardé
    reponse = client.post("/api/v1/import", headers=admin,
                          json={"films": [FILM, {**FILM, "titre": "ALIEN"}]})
    assert reponse.json == {"importes": 1, "ignores": ["ALIEN"]}
