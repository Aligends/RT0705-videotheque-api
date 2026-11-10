"""Avis : « vu », note et commentaire propres à chaque utilisateur."""
from conftest import creer_film


def test_avis_personnel(client, membre, autre):
    film = creer_film(client, membre)
    url = f"/api/v1/films/{film['id']}/avis"

    assert client.put(url, json={"note": 8}).status_code == 401
    reponse = client.put(url, json={"note": 8, "commentaire": " Très bon.\r\nÀ revoir. "},
                         headers=membre)
    assert reponse.status_code == 201
    assert (reponse.json["avis"]["note"], reponse.json["avis"]["commentaire"]) == (
        8, "Très bon.\nÀ revoir.")
    # second envoi : l'avis est remplacé, pas dupliqué
    assert client.put(url, json={"note": 9}, headers=membre).status_code == 200
    # « vu » sans note ni commentaire
    assert client.put(url, json={}, headers=autre).status_code == 201

    vu_par_membre = client.get(f"/api/v1/films/{film['id']}", headers=membre).json["film"]
    assert (vu_par_membre["mon_avis"]["note"], vu_par_membre["mon_avis"]["commentaire"]) == (9, None)
    assert (vu_par_membre["note_moyenne"], vu_par_membre["nb_notes"]) == (9.0, 1)
    assert client.get(f"/api/v1/films/{film['id']}").json["film"]["mon_avis"] is None

    assert client.put(url, json={"note": 6}, headers=autre).status_code == 200
    public = client.get(f"/api/v1/films/{film['id']}").json["film"]
    assert (public["note_moyenne"], public["nb_notes"]) == (7.5, 2)

    avis = client.get(url).json["avis"]
    assert sorted((a["auteur"], a["note"]) for a in avis) == [("Autre", 6), ("Membre", 9)]

    for corps in ({"note": 11}, {"note": "8"}, {"note": -1}, {"commentaire": "x" * 2001},
                  {"note": 5, "utilisateur_id": 2}):
        assert client.put(url, json=corps, headers=membre).status_code == 400, corps
    assert client.put("/api/v1/films/999/avis", json={}, headers=membre).status_code == 404
    assert client.get("/api/v1/films/999/avis").status_code == 404


def test_filtre_vu_et_tri_par_note(client, membre, autre):
    alien = creer_film(client, membre)
    amelie = creer_film(client, membre, titre="Amélie")
    creer_film(client, membre, titre="Inception")
    client.put(f"/api/v1/films/{alien['id']}/avis", json={"note": 6}, headers=membre)
    client.put(f"/api/v1/films/{amelie['id']}/avis", json={"note": 9}, headers=autre)

    def titres(requete, entetes):
        return [f["titre"] for f in client.get("/api/v1/films?" + requete,
                                               headers=entetes).json["films"]]

    assert titres("vu=true", membre) == ["Alien"]
    assert titres("vu=false", membre) == ["Amélie", "Inception"]
    assert titres("vu=true", autre) == ["Amélie"]
    # tri par note moyenne, les films sans note en dernier
    assert titres("tri=note&ordre=desc", None) == ["Amélie", "Alien", "Inception"]


def test_suppression_et_moderation(client, membre, autre, admin):
    film = creer_film(client, membre)
    url = f"/api/v1/films/{film['id']}/avis"
    client.put(url, json={"note": 2, "commentaire": "Propos déplacés"}, headers=autre)
    client.put(url, json={"note": 8}, headers=membre)

    # chacun retire son propre avis
    assert client.delete(url).status_code == 401
    assert client.delete(url, headers=membre).status_code == 204
    assert client.delete(url, headers=membre).status_code == 404

    # seul un administrateur retire l'avis d'un autre
    auteur = client.get(url).json["avis"][0]["utilisateur_id"]
    assert client.delete(f"{url}/{auteur}", headers=membre).status_code == 403
    assert client.delete(f"{url}/{auteur}", headers=admin).status_code == 204
    assert client.delete(f"{url}/{auteur}", headers=admin).status_code == 404
    assert client.get(url).json["avis"] == []
