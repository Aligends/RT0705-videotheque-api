"""Administration : comptes, genres, journal d'audit."""
from conftest import MOT_DE_PASSE, creer_film, sql


def identifiant(email):
    return sql("SELECT id FROM utilisateurs WHERE email = %s", (email,))[0]["id"]


def test_gestion_des_comptes_reservee_aux_administrateurs(client, membre, autre, admin):
    assert client.get("/api/v1/utilisateurs").status_code == 401
    assert client.get("/api/v1/utilisateurs", headers=membre).status_code == 403
    cible = identifiant("autre@exemple.fr")
    assert client.patch(f"/api/v1/utilisateurs/{cible}", json={"role": "admin"},
                        headers=membre).status_code == 403
    assert client.delete(f"/api/v1/utilisateurs/{cible}", headers=membre).status_code == 403

    reponse = client.get("/api/v1/utilisateurs", headers=admin)
    assert reponse.status_code == 200
    assert [u["email"] for u in reponse.json["utilisateurs"]] == [
        "admin@exemple.fr", "autre@exemple.fr", "membre@exemple.fr"]
    assert all("mot_de_passe" not in u for u in reponse.json["utilisateurs"])
    assert reponse.json["pagination"]["total"] == 3


def test_changement_de_role_et_desactivation(client, membre, admin):
    cible = identifiant("membre@exemple.fr")
    url = f"/api/v1/utilisateurs/{cible}"

    for corps in ({}, {"role": "roi"}, {"actif": "non"}, {"email": "x@y.fr"}):
        assert client.patch(url, json=corps, headers=admin).status_code == 400, corps
    assert client.patch("/api/v1/utilisateurs/999", json={"actif": False},
                        headers=admin).status_code == 404

    # promotion : les anciens jetons sont révoqués, la reconnexion donne les nouveaux droits
    reponse = client.patch(url, json={"role": "admin"}, headers=admin)
    assert reponse.status_code == 200 and reponse.json["utilisateur"]["role"] == "admin"
    assert client.get("/api/v1/auth/moi", headers=membre).status_code == 401
    identifiants = {"email": "membre@exemple.fr", "mot_de_passe": MOT_DE_PASSE}
    jeton = client.post("/api/v1/auth/connexion", json=identifiants).json["jeton"]
    promu = {"Authorization": "Bearer " + jeton}
    assert client.get("/api/v1/utilisateurs", headers=promu).status_code == 200

    # désactivation : plus de connexion possible, les jetons cessent de fonctionner
    assert client.patch(url, json={"actif": False}, headers=admin).status_code == 200
    assert client.get("/api/v1/auth/moi", headers=promu).status_code == 401
    assert client.post("/api/v1/auth/connexion", json=identifiants).status_code == 403
    en_attente = client.get("/api/v1/utilisateurs?actif=false", headers=admin).json["utilisateurs"]
    assert [u["email"] for u in en_attente] == ["membre@exemple.fr"]
    assert client.patch(url, json={"actif": True}, headers=admin).status_code == 200
    assert client.post("/api/v1/auth/connexion", json=identifiants).status_code == 200


def test_un_administrateur_ne_se_retire_pas_ses_droits(client, admin):
    moi = identifiant("admin@exemple.fr")
    assert client.patch(f"/api/v1/utilisateurs/{moi}", json={"role": "membre"},
                        headers=admin).status_code == 409
    assert client.patch(f"/api/v1/utilisateurs/{moi}", json={"actif": False},
                        headers=admin).status_code == 409
    assert client.delete(f"/api/v1/utilisateurs/{moi}", headers=admin).status_code == 409
    assert client.get("/api/v1/auth/moi", headers=admin).json["utilisateur"]["role"] == "admin"


def test_suppression_d_un_compte(client, membre, admin):
    film = creer_film(client, membre)
    client.put(f"/api/v1/films/{film['id']}/avis", json={"note": 7}, headers=membre)
    cible = identifiant("membre@exemple.fr")

    assert client.delete(f"/api/v1/utilisateurs/{cible}", headers=admin).status_code == 204
    assert client.delete(f"/api/v1/utilisateurs/{cible}", headers=admin).status_code == 404
    assert client.get("/api/v1/auth/moi", headers=membre).status_code == 401
    # ses films restent dans le catalogue, ses avis disparaissent
    conserve = client.get(f"/api/v1/films/{film['id']}").json["film"]
    assert (conserve["ajoute_par"], conserve["ajoute_par_nom"], conserve["nb_notes"]) == (None, None, 0)
    # le journal garde son nom, même si le compte n'existe plus
    creation = sql("SELECT utilisateur_id, utilisateur_nom FROM journal WHERE action = 'film_cree'")
    assert creation == [{"utilisateur_id": None, "utilisateur_nom": "Membre"}]


def test_genres(client, membre, admin):
    creer_film(client, membre)
    assert client.post("/api/v1/genres", json={"nom": "X"}).status_code == 401
    assert client.post("/api/v1/genres", json={"nom": " Western "}, headers=membre).status_code == 201
    assert client.post("/api/v1/genres", json={"nom": "western"}, headers=membre).status_code == 409
    for corps in ({"nom": ""}, {"nom": "x" * 51}, {"nom": 3}, {"nom": "Ok", "id": 1}):
        assert client.post("/api/v1/genres", json=corps, headers=membre).status_code == 400
    genres = client.get("/api/v1/genres").json["genres"]
    assert [(g["nom"], g["nb_films"]) for g in genres] == [
        ("Horreur", 1), ("Science-fiction", 1), ("Western", 0)]

    # la suppression d'un genre touche tous les films : réservée aux administrateurs
    horreur = genres[0]["id"]
    assert client.delete(f"/api/v1/genres/{horreur}", headers=membre).status_code == 403
    assert client.delete(f"/api/v1/genres/{horreur}", headers=admin).status_code == 204
    assert client.delete(f"/api/v1/genres/{horreur}", headers=admin).status_code == 404
    assert client.get("/api/v1/films/1").json["film"]["genres"] == ["Science-fiction"]


def test_journal_d_audit(client, membre, admin):
    film = creer_film(client, membre)
    client.patch(f"/api/v1/films/{film['id']}", json={"annee": 1980}, headers=membre)
    client.post(f"/api/v1/films/{film['id']}/prets", json={"emprunteur": "Léa"}, headers=membre)
    client.post("/api/v1/auth/connexion",
                json={"email": "membre@exemple.fr", "mot_de_passe": "mauvais-mot-de-passe"})
    client.delete(f"/api/v1/films/{film['id']}", headers=admin)

    assert client.get("/api/v1/journal").status_code == 401
    assert client.get("/api/v1/journal", headers=membre).status_code == 403
    reponse = client.get("/api/v1/journal", headers=admin).json
    # du plus récent au plus ancien
    assert [e["action"] for e in reponse["journal"]] == [
        "film_supprime", "connexion_echec", "pret_cree", "film_modifie", "film_cree",
        "inscription", "inscription"]
    suppression, echec = reponse["journal"][0], reponse["journal"][1]
    assert (suppression["utilisateur_nom"], suppression["cible"]) == (
        "Admin", "film n° 1 « Alien »")
    assert (echec["utilisateur_nom"], echec["cible"]) == (None, "membre@exemple.fr")
    assert reponse["pagination"]["total"] == 7 and "film_cree" in reponse["actions"]

    filtre = client.get("/api/v1/journal?action=inscription&par_page=1", headers=admin).json
    assert len(filtre["journal"]) == 1 and filtre["pagination"] == {
        "page": 1, "par_page": 1, "total": 2, "pages": 2}
    # une opération refusée ne laisse aucune trace d'opération réussie
    client.delete("/api/v1/genres/1", headers=membre)
    assert sql("SELECT count(*) AS n FROM journal WHERE action = 'genre_supprime'")[0]["n"] == 0
