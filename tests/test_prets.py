"""Prêts : réservés aux utilisateurs connectés, un seul prêt en cours par film."""
from datetime import date, timedelta

from conftest import creer_film

HIER = (date.today() - timedelta(days=1)).isoformat()
DEMAIN = (date.today() + timedelta(days=1)).isoformat()


def test_les_prets_ne_sont_pas_publics(client, membre):
    film = creer_film(client, membre)
    client.post(f"/api/v1/films/{film['id']}/prets", json={"emprunteur": "Léa"}, headers=membre)
    assert client.get("/api/v1/prets").status_code == 401
    assert client.get(f"/api/v1/films/{film['id']}/prets").status_code == 401
    assert client.post(f"/api/v1/films/{film['id']}/prets",
                       json={"emprunteur": "Tom"}).status_code == 401
    assert client.post("/api/v1/prets/1/retour").status_code == 401
    assert client.delete("/api/v1/prets/1").status_code == 401
    # le public sait seulement que le film n'est pas disponible
    public = client.get(f"/api/v1/films/{film['id']}").json["film"]
    assert public["disponible"] is False and "emprunteur" not in str(public)


def test_pret_puis_retour(client, membre, autre, admin):
    film = creer_film(client, membre)
    url = f"/api/v1/films/{film['id']}/prets"

    def details(corps):
        reponse = client.post(url, json=corps, headers=membre)
        assert reponse.status_code == 400, reponse.json
        return set(reponse.json["erreur"]["details"])

    assert details({}) == {"emprunteur"}
    assert details({"emprunteur": "Léa", "date_pret": "hier"}) == {"date_pret"}
    assert details({"emprunteur": "Léa", "date_pret": DEMAIN}) == {"date_pret"}
    assert details({"emprunteur": "Léa", "date_retour_prevue": HIER}) == {"date_retour_prevue"}
    assert details({"emprunteur": "Léa", "film_id": 2}) == {"film_id"}

    # n'importe quel membre peut prêter un film de la vidéothèque
    reponse = client.post(url, json={"emprunteur": " Léa ", "date_pret": "2020-01-01",
                                     "date_retour_prevue": "2020-01-15"}, headers=autre)
    assert reponse.status_code == 201
    pret = reponse.json["pret"]
    assert (pret["film_titre"], pret["emprunteur"], pret["en_cours"], pret["en_retard"]) == (
        "Alien", "Léa", True, True)
    assert pret["date_pret"] == "2020-01-01"

    # le film n'est plus disponible et ne peut pas être prêté deux fois
    assert client.post(url, json={"emprunteur": "Tom"}, headers=membre).status_code == 409
    assert [f["titre"] for f in client.get("/api/v1/films?disponible=false").json["films"]] == ["Alien"]
    assert client.get("/api/v1/films?disponible=true").json["films"] == []
    assert len(client.get("/api/v1/prets?en_cours=true", headers=membre).json["prets"]) == 1
    assert client.get("/api/v1/prets?en_cours=false", headers=membre).json["prets"] == []

    retour = f"/api/v1/prets/{pret['id']}/retour"
    assert client.post(retour, json={"date_retour": "2019-12-31"}, headers=membre).status_code == 400
    assert client.post(retour, json={"date_retour": DEMAIN}, headers=membre).status_code == 400
    reponse = client.post(retour, headers=membre)
    assert reponse.status_code == 200
    assert reponse.json["pret"]["date_retour"] == date.today().isoformat()
    assert reponse.json["pret"]["en_retard"] is False
    assert client.post(retour, headers=membre).status_code == 409

    assert client.get(f"/api/v1/films/{film['id']}").json["film"]["disponible"] is True
    liste = client.get("/api/v1/prets", headers=membre).json
    assert len(liste["prets"]) == 1 and liste["pagination"]["total"] == 1
    assert len(client.get(url, headers=membre).json["prets"]) == 1
    assert client.get("/api/v1/films/999/prets", headers=membre).status_code == 404
    assert client.post("/api/v1/prets/999/retour", headers=membre).status_code == 404

    numerique = creer_film(client, membre, titre="Fichier", support="numerique")
    assert client.post(f"/api/v1/films/{numerique['id']}/prets",
                       json={"emprunteur": "Léa"}, headers=membre).status_code == 409

    # seul un administrateur efface une ligne de l'historique
    assert client.delete(f"/api/v1/prets/{pret['id']}", headers=membre).status_code == 403
    assert client.delete(f"/api/v1/prets/{pret['id']}", headers=admin).status_code == 204
    assert client.delete(f"/api/v1/prets/{pret['id']}", headers=admin).status_code == 404
    assert client.get("/api/v1/prets", headers=membre).json["prets"] == []
