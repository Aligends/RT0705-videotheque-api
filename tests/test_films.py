"""Films : lecture publique, écritures protégées, propriété, validation, recherche."""
from conftest import FILM, creer_film, sql


def test_lecture_publique_et_ecritures_protegees(client, membre):
    film = creer_film(client, membre)
    assert client.get("/api/v1/films").status_code == 200
    assert client.get(f"/api/v1/films/{film['id']}").status_code == 200
    assert client.post("/api/v1/films", json=FILM).status_code == 401
    assert client.put(f"/api/v1/films/{film['id']}", json=FILM).status_code == 401
    assert client.patch(f"/api/v1/films/{film['id']}", json={"annee": 1980}).status_code == 401
    assert client.delete(f"/api/v1/films/{film['id']}").status_code == 401
    assert client.get("/api/v1/films/999").json["erreur"]["message"] == "Film 999 introuvable."


def test_cycle_de_vie(client, membre):
    reponse = client.post("/api/v1/films", json=FILM, headers=membre)
    assert reponse.status_code == 201 and reponse.headers["Location"].endswith("/api/v1/films/1")
    film = reponse.json["film"]
    assert film["genres"] == ["Horreur", "Science-fiction"]
    assert (film["ajoute_par"], film["ajoute_par_nom"], film["disponible"]) == (1, "Membre", True)
    assert (film["note_moyenne"], film["nb_notes"], film["mon_avis"]) == (None, 0, None)
    assert film["modifiable"] is True
    # un visiteur voit le même film, sans droit de modification
    public = client.get("/api/v1/films/1").json["film"]
    assert public == {**film, "modifiable": False}

    # PATCH : seuls les champs fournis changent
    reponse = client.patch("/api/v1/films/1", json={"format": "Blu-ray"}, headers=membre)
    assert reponse.status_code == 200
    modifie = reponse.json["film"]
    assert (modifie["format"], modifie["annee"], modifie["genres"]) == (
        "Blu-ray", 1979, film["genres"])

    # PUT : remplacement complet, les champs absents sont vidés
    reponse = client.put("/api/v1/films/1", json={"titre": "Aliens", "support": "numerique"},
                         headers=membre)
    remplace = reponse.json["film"]
    assert (remplace["titre"], remplace["support"], remplace["annee"], remplace["genres"]) == (
        "Aliens", "numerique", None, [])

    assert client.delete("/api/v1/films/1", headers=membre).status_code == 204
    assert client.get("/api/v1/films/1").status_code == 404
    assert client.delete("/api/v1/films/1", headers=membre).status_code == 404


def test_seuls_le_proprietaire_et_les_administrateurs_modifient(client, membre, autre, admin):
    film = creer_film(client, membre)
    url = f"/api/v1/films/{film['id']}"
    assert client.get(url, headers=autre).json["film"]["modifiable"] is False
    assert client.patch(url, json={"annee": 1980}, headers=autre).status_code == 403
    assert client.put(url, json=FILM, headers=autre).status_code == 403
    assert client.delete(url, headers=autre).status_code == 403
    assert client.get(url).json["film"]["annee"] == 1979

    assert client.get(url, headers=admin).json["film"]["modifiable"] is True
    assert client.patch(url, json={"annee": 1980}, headers=admin).status_code == 200
    assert client.delete(url, headers=admin).status_code == 204


def test_validation(client, membre):
    reponse = client.post("/api/v1/films", headers=membre, json={
        "titre": " ", "support": "betamax", "annee": "1979", "duree_min": 0,
        "affiche_url": "http://exemple.fr/a.jpg", "genres": "SF",
        "id": 5, "ajoute_par": 2, "note": 9})
    assert reponse.status_code == 400
    assert set(reponse.json["erreur"]["details"]) == {
        "titre", "support", "annee", "duree_min", "affiche_url", "genres",
        "id", "ajoute_par", "note"}

    def refuse(**champs):
        return client.post("/api/v1/films", headers=membre,
                           json={**FILM, **champs}).status_code == 400

    assert refuse(titre="x" * 256)
    assert refuse(titre="nul\x00dans le titre")
    assert refuse(annee=True) and refuse(annee=1887) and refuse(annee=19.5)
    assert refuse(affiche_url="javascript:alert(1)") and refuse(affiche_url="https://")
    assert refuse(genres=[str(i) for i in range(11)])     # plus de 10 genres
    assert refuse(genres=["x" * 51]) and refuse(genres=[1])
    assert client.post("/api/v1/films", headers=membre, data="pas du json").status_code == 400
    assert client.post("/api/v1/films", headers=membre, json=["liste"]).status_code == 400
    assert sql("SELECT count(*) AS n FROM films")[0]["n"] == 0

    film = creer_film(client, membre, titre="  Le   Titre ", synopsis="Ligne 1\r\nLigne 2",
                      affiche_url="https://exemple.fr/affiche.jpg",
                      genres=["Drame", " drame ", "DRAME"])
    assert (film["titre"], film["synopsis"], film["genres"]) == (
        "Le Titre", "Ligne 1\nLigne 2", ["Drame"])
    assert client.patch(f"/api/v1/films/{film['id']}", json={"titre": None},
                        headers=membre).status_code == 400


def test_recherche_filtres_pagination(client, membre, autre):
    creer_film(client, membre)
    creer_film(client, membre, titre="Amélie", annee=2001, realisateur="Jean-Pierre Jeunet",
               genres=["Comédie"])
    creer_film(client, autre, titre="Inception", annee=2010, realisateur="Christopher Nolan",
               support="numerique", genres=["science-fiction"])
    creer_film(client, autre, titre="100% Cachemire", annee=2013, genres=[])

    def titres(requete, entetes=None):
        reponse = client.get("/api/v1/films?" + requete, headers=entetes)
        assert reponse.status_code == 200, reponse.json
        return [f["titre"] for f in reponse.json["films"]]

    assert titres("") == ["100% Cachemire", "Alien", "Amélie", "Inception"]
    assert titres("q=nolan") == ["Inception"]
    assert titres("q=AMELIE") == ["Amélie"]                  # casse et accents ignorés
    assert titres("q=%25") == ["100% Cachemire"]             # « % » est cherché tel quel
    assert titres("q=_") == []
    assert titres("genre=Science-fiction") == ["Alien", "Inception"]   # genre réutilisé
    assert titres("support=numerique") == ["Inception"]
    assert titres("annee=1979") == ["Alien"]
    assert titres("tri=annee&ordre=desc") == ["100% Cachemire", "Inception", "Amélie", "Alien"]
    assert titres("mes_ajouts=true", membre) == ["Alien", "Amélie"]

    reponse = client.get("/api/v1/films?par_page=3&page=2").json
    assert [f["titre"] for f in reponse["films"]] == ["Inception"]
    assert reponse["pagination"] == {"page": 2, "par_page": 3, "total": 4, "pages": 2}

    for requete in ("tri=mot_de_passe", "ordre=;drop", "page=0", "par_page=abc", "par_page=101",
                    "support=x", "disponible=peut-etre", "annee=abc"):
        assert client.get("/api/v1/films?" + requete).status_code == 400, requete
    # les filtres personnels demandent un jeton
    assert client.get("/api/v1/films?vu=true").status_code == 401
    assert client.get("/api/v1/films?mes_ajouts=true").status_code == 401


def test_tentatives_d_injection_sql(client, membre):
    creer_film(client, membre)
    for charge in ("' OR '1'='1", "'; DROP TABLE films; --", "\\", "%' UNION SELECT 1 --"):
        reponse = client.get("/api/v1/films", query_string={"q": charge, "genre": charge})
        assert reponse.status_code == 200 and reponse.json["films"] == []
    film = creer_film(client, membre, titre="Robert'); DROP TABLE films;--")
    assert film["titre"] == "Robert'); DROP TABLE films;--"
    assert sql("SELECT count(*) AS n FROM films")[0]["n"] == 2
