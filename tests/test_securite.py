"""Configuration, en-têtes, limites et format des erreurs."""
import pytest

from app import create_app
from conftest import creer_film, sql

BASE = {"DATABASE_URL": "postgresql://inutilise@localhost/inutilise", "SECRET_KEY": "c" * 32}


def test_demarrage_refuse_sans_cle_solide(monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    for cle in ("", "trop-courte"):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app({**BASE, "SECRET_KEY": cle})
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app({**BASE, "DATABASE_URL": ""})
    with pytest.raises(RuntimeError, match="INSCRIPTION"):
        create_app({**BASE, "INSCRIPTION": "libre"})
    # en développement seulement, une clé jetable est générée
    app = create_app({**BASE, "SECRET_KEY": "", "TESTING": True})
    assert len(app.config["SECRET_KEY"]) >= 32


def test_sante_et_entetes(client):
    reponse = client.get("/api/v1/sante")
    assert reponse.json == {"statut": "ok"}
    assert reponse.headers["X-Content-Type-Options"] == "nosniff"
    assert reponse.headers["Cache-Control"] == "no-store"
    assert "default-src 'none'" in reponse.headers["Content-Security-Policy"]
    assert "Access-Control-Allow-Origin" not in reponse.headers      # pas d'accès inter-sites


def test_erreurs_toujours_en_json(client, membre):
    reponse = client.get("/api/v1/inconnu")
    assert reponse.status_code == 404 and reponse.json["erreur"] == {
        "code": 404, "message": "Ressource introuvable."}
    assert client.delete("/api/v1/films").json["erreur"]["code"] == 405
    assert client.get("/api/v1/films/abc").json["erreur"]["code"] == 404
    # un formulaire HTML classique n'est pas accepté : seul le JSON l'est
    reponse = client.post("/api/v1/films", data={"titre": "X", "support": "physique"},
                          headers=membre)
    assert reponse.status_code == 400 and "JSON" in reponse.json["erreur"]["message"]


def test_json_trop_imbrique(client, membre):
    corps = "[" * 100_000 + "]" * 100_000
    reponse = client.post("/api/v1/films", data=corps, headers=membre,
                          content_type="application/json")
    assert reponse.status_code == 400


def test_requete_trop_volumineuse(client, membre):
    reponse = client.post("/api/v1/films", headers=membre,
                          json={"titre": "Gros", "support": "physique", "synopsis": "x" * 1_100_000})
    assert reponse.status_code == 413 and reponse.json["erreur"]["code"] == 413
    assert sql("SELECT count(*) AS n FROM films")[0]["n"] == 0


def test_erreur_interne_sans_detail(base, monkeypatch):
    app = create_app({**BASE, "TESTING": False, "PROPAGATE_EXCEPTIONS": False})

    @app.get("/boum")
    def boum():
        raise ValueError("détail interne à ne pas divulguer")

    reponse = app.test_client().get("/boum")
    assert reponse.status_code == 500
    assert reponse.json == {"erreur": {"code": 500, "message": "Erreur interne du serveur."}}
    # base injoignable : 503, sans message technique
    reponse = app.test_client().get("/api/v1/films")
    assert reponse.status_code == 503 and "inutilise" not in reponse.get_data(as_text=True)


def test_statistiques(client, membre, autre):
    vide = client.get("/api/v1/statistiques").json["statistiques"]
    assert (vide["nb_films"], vide["duree_totale_min"], vide["note_moyenne"]) == (0, 0, None)
    assert "mes_statistiques" not in vide

    alien = creer_film(client, membre)
    inception = creer_film(client, membre, titre="Inception", annee=2010, support="numerique",
                           duree_min=148, genres=["Science-fiction"])
    client.put(f"/api/v1/films/{alien['id']}/avis", json={"note": 8}, headers=membre)
    client.put(f"/api/v1/films/{inception['id']}/avis", json={"note": 9}, headers=autre)
    client.put(f"/api/v1/films/{alien['id']}/avis", json={"note": 7}, headers=autre)
    client.post(f"/api/v1/films/{alien['id']}/prets", json={"emprunteur": "Léa"}, headers=membre)

    stats = client.get("/api/v1/statistiques", headers=membre).json["statistiques"]
    assert stats == {
        "nb_films": 2, "nb_physiques": 1, "nb_numeriques": 1, "duree_totale_min": 265,
        "note_moyenne": 8.0, "nb_notes": 3, "nb_prets_en_cours": 1,
        "films_par_genre": [{"genre": "Science-fiction", "nb_films": 2},
                            {"genre": "Horreur", "nb_films": 1}],
        "films_par_decennie": [{"decennie": 1970, "nb_films": 1},
                               {"decennie": 2010, "nb_films": 1}],
        "mieux_notes": [{"id": 2, "titre": "Inception", "note_moyenne": 9.0, "nb_notes": 1},
                        {"id": 1, "titre": "Alien", "note_moyenne": 7.5, "nb_notes": 2}],
        "mes_statistiques": {"nb_vus": 1, "duree_vue_min": 117, "nb_a_voir": 1},
    }
