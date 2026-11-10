"""Inscription, connexion, jetons, verrouillage, mot de passe."""
from app.auth import creer_jeton
from conftest import MOT_DE_PASSE, nouvelle_app, sql

COMPTE = {"nom": "Test", "email": "Test@Exemple.fr", "mot_de_passe": MOT_DE_PASSE}
IDENTIFIANTS = {"email": "test@exemple.fr", "mot_de_passe": MOT_DE_PASSE}
MAUVAIS = {**IDENTIFIANTS, "mot_de_passe": "mauvais-mot-de-passe"}


def bearer(jeton):
    return {"Authorization": "Bearer " + jeton}


def test_inscription_ouverte(client):
    reponse = client.post("/api/v1/auth/inscription", json=COMPTE)
    assert reponse.status_code == 201
    utilisateur = reponse.json["utilisateur"]
    assert (utilisateur["email"], utilisateur["role"], utilisateur["actif"]) == (
        "test@exemple.fr", "membre", True)
    assert reponse.json["en_attente"] is False and "mot_de_passe" not in utilisateur
    assert client.get("/api/v1/auth/moi", headers=bearer(reponse.json["jeton"])).status_code == 200
    # le mot de passe n'est jamais stocké en clair
    assert MOT_DE_PASSE not in sql("SELECT mot_de_passe FROM utilisateurs")[0]["mot_de_passe"]
    # adresse déjà utilisée (casse ignorée)
    assert client.post("/api/v1/auth/inscription", json=COMPTE).status_code == 409


def test_inscription_avec_validation(base):
    client = nouvelle_app(INSCRIPTION="validation").test_client()
    reponse = client.post("/api/v1/auth/inscription", json=COMPTE)
    assert reponse.status_code == 201
    assert reponse.json["en_attente"] is True and "jeton" not in reponse.json
    # tant qu'un administrateur n'a pas activé le compte, la connexion est refusée
    assert client.post("/api/v1/auth/connexion", json=IDENTIFIANTS).status_code == 403
    sql("UPDATE utilisateurs SET actif = TRUE")
    assert client.post("/api/v1/auth/connexion", json=IDENTIFIANTS).status_code == 200


def test_inscription_fermee(base):
    client = nouvelle_app(INSCRIPTION="fermee").test_client()
    assert client.post("/api/v1/auth/inscription", json=COMPTE).status_code == 403
    assert sql("SELECT count(*) AS n FROM utilisateurs")[0]["n"] == 0


def test_inscription_donnees_invalides(client):
    reponse = client.post("/api/v1/auth/inscription",
                          json={"nom": " ", "email": "pas-une-adresse", "mot_de_passe": "court"})
    assert reponse.status_code == 400
    assert set(reponse.json["erreur"]["details"]) == {"nom", "email", "mot_de_passe"}

    def mot_de_passe_refuse(mot_de_passe):
        r = client.post("/api/v1/auth/inscription", json={**COMPTE, "mot_de_passe": mot_de_passe})
        return r.status_code == 400 and "mot_de_passe" in r.json["erreur"]["details"]

    assert mot_de_passe_refuse("azertyuiop")          # trop courant
    assert mot_de_passe_refuse("aaaaaaaaaaaa")        # trop simple
    assert mot_de_passe_refuse("test@exemple.fr")     # identique à l'adresse
    assert mot_de_passe_refuse("x" * 129)             # trop long
    assert mot_de_passe_refuse(1234567890)            # pas une chaîne
    # un client ne peut pas choisir son rôle ni s'activer lui-même
    reponse = client.post("/api/v1/auth/inscription",
                          json={**COMPTE, "role": "admin", "actif": True})
    assert reponse.status_code == 400
    assert set(reponse.json["erreur"]["details"]) == {"role", "actif"}
    assert sql("SELECT count(*) AS n FROM utilisateurs")[0]["n"] == 0


def test_connexion(client):
    client.post("/api/v1/auth/inscription", json=COMPTE)
    reponse = client.post("/api/v1/auth/connexion",
                          json={**IDENTIFIANTS, "email": " TEST@exemple.fr "})
    assert reponse.status_code == 200 and reponse.json["expire_dans_s"] == 4 * 3600
    assert "mot_de_passe" not in reponse.json["utilisateur"]
    assert reponse.json["utilisateur"]["derniere_connexion"] is not None
    moi = client.get("/api/v1/auth/moi", headers=bearer(reponse.json["jeton"]))
    assert moi.json["utilisateur"]["email"] == "test@exemple.fr"

    # même réponse que le compte existe ou non : rien ne révèle les adresses inscrites
    mauvais = client.post("/api/v1/auth/connexion", json=MAUVAIS)
    inconnu = client.post("/api/v1/auth/connexion",
                          json={"email": "personne@exemple.fr", "mot_de_passe": MOT_DE_PASSE})
    assert mauvais.status_code == inconnu.status_code == 401
    assert mauvais.json == inconnu.json
    for corps in ({}, {"email": 12, "mot_de_passe": []}, {"email": "x", "mot_de_passe": "y"}):
        assert client.post("/api/v1/auth/connexion", json=corps).status_code == 401


def test_verrouillage_apres_echecs(client):
    client.post("/api/v1/auth/inscription", json=COMPTE)
    for _ in range(5):
        assert client.post("/api/v1/auth/connexion", json=MAUVAIS).status_code == 401
    # verrouillé : même le bon mot de passe est refusé
    reponse = client.post("/api/v1/auth/connexion", json=IDENTIFIANTS)
    assert reponse.status_code == 429
    assert 0 < int(reponse.headers["Retry-After"]) <= 15 * 60
    assert sql("SELECT count(*) AS n FROM tentatives_connexion")[0]["n"] == 5

    # une adresse sans compte se verrouille de la même façon
    inconnu = {"email": "personne@exemple.fr", "mot_de_passe": "mauvais-mot-de-passe"}
    codes = [client.post("/api/v1/auth/connexion", json=inconnu).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]

    # 15 minutes plus tard, les échecs sont oubliés
    sql("UPDATE tentatives_connexion SET date_tentative = now() - INTERVAL '16 minutes'")
    assert client.post("/api/v1/auth/connexion", json=IDENTIFIANTS).status_code == 200
    assert sql("SELECT count(*) AS n FROM tentatives_connexion")[0]["n"] == 0


def test_une_connexion_reussie_remet_le_compteur_a_zero(client):
    client.post("/api/v1/auth/inscription", json=COMPTE)
    for _ in range(4):
        client.post("/api/v1/auth/connexion", json=MAUVAIS)
    assert client.post("/api/v1/auth/connexion", json=IDENTIFIANTS).status_code == 200
    for _ in range(4):
        assert client.post("/api/v1/auth/connexion", json=MAUVAIS).status_code == 401
    assert client.post("/api/v1/auth/connexion", json=IDENTIFIANTS).status_code == 200


def test_jetons_refuses(client):
    jeton = client.post("/api/v1/auth/inscription", json=COMPTE).json["jeton"]
    sans_jeton = client.get("/api/v1/auth/moi")
    assert sans_jeton.status_code == 401
    assert sans_jeton.headers["WWW-Authenticate"].startswith("Bearer")
    for entete in ("Bearer faux", "Bearer " + jeton[:-2] + "xx", "Basic abc", jeton):
        reponse = client.get("/api/v1/auth/moi", headers={"Authorization": entete})
        assert reponse.status_code == 401, entete
    # un jeton invalide est refusé même sur une route publique
    assert client.get("/api/v1/films", headers=bearer("faux")).status_code == 401

    # jeton signé avec une autre clé
    autre_app = nouvelle_app(SECRET_KEY="d" * 32)
    with autre_app.app_context():
        contrefait = creer_jeton(1, 0)
    assert client.get("/api/v1/auth/moi", headers=bearer(contrefait)).status_code == 401
    assert autre_app.test_client().get(
        "/api/v1/auth/moi", headers=bearer(contrefait)).status_code == 200

    # jeton expiré
    expire = nouvelle_app(DUREE_JETON_S=-1).test_client()
    assert expire.get("/api/v1/auth/moi", headers=bearer(jeton)).status_code == 401

    # compte désactivé, puis supprimé
    sql("UPDATE utilisateurs SET actif = FALSE")
    assert client.get("/api/v1/auth/moi", headers=bearer(jeton)).status_code == 401
    sql("DELETE FROM utilisateurs")
    assert client.get("/api/v1/auth/moi", headers=bearer(jeton)).status_code == 401


def test_ancien_jeton_ignore_a_la_connexion(client):
    client.post("/api/v1/auth/inscription", json=COMPTE)
    reponse = client.post("/api/v1/auth/connexion", json=IDENTIFIANTS, headers=bearer("perime"))
    assert reponse.status_code == 200


def test_deconnexion_revoque_le_jeton(client):
    jeton = client.post("/api/v1/auth/inscription", json=COMPTE).json["jeton"]
    autre_session = client.post("/api/v1/auth/connexion", json=IDENTIFIANTS).json["jeton"]
    assert client.post("/api/v1/auth/deconnexion", headers=bearer(jeton)).status_code == 204
    # tous les jetons du compte cessent de fonctionner
    assert client.get("/api/v1/auth/moi", headers=bearer(jeton)).status_code == 401
    assert client.get("/api/v1/auth/moi", headers=bearer(autre_session)).status_code == 401
    nouveau = client.post("/api/v1/auth/connexion", json=IDENTIFIANTS).json["jeton"]
    assert client.get("/api/v1/auth/moi", headers=bearer(nouveau)).status_code == 200


def test_changement_de_mot_de_passe(client):
    jeton = client.post("/api/v1/auth/inscription", json=COMPTE).json["jeton"]
    url, nouveau = "/api/v1/auth/mot-de-passe", "nouvelle-phrase-secrete"

    def details(corps):
        reponse = client.post(url, json=corps, headers=bearer(jeton))
        assert reponse.status_code == 400, reponse.json
        return set(reponse.json["erreur"]["details"])

    assert details({"ancien": "mauvais-mot-de-passe", "nouveau": nouveau}) == {"ancien"}
    assert details({"ancien": MOT_DE_PASSE, "nouveau": "court"}) == {"nouveau"}
    assert details({"ancien": MOT_DE_PASSE, "nouveau": MOT_DE_PASSE}) == {"nouveau"}
    assert details({}) == {"ancien", "nouveau"}
    assert client.post(url, json={"ancien": MOT_DE_PASSE, "nouveau": nouveau}).status_code == 401

    reponse = client.post(url, json={"ancien": MOT_DE_PASSE, "nouveau": nouveau},
                          headers=bearer(jeton))
    assert reponse.status_code == 200
    # l'ancien jeton est révoqué, le nouveau fonctionne
    assert client.get("/api/v1/auth/moi", headers=bearer(jeton)).status_code == 401
    assert client.get("/api/v1/auth/moi",
                      headers=bearer(reponse.json["jeton"])).status_code == 200
    assert client.post("/api/v1/auth/connexion", json=IDENTIFIANTS).status_code == 401
    assert client.post("/api/v1/auth/connexion",
                       json={**IDENTIFIANTS, "mot_de_passe": nouveau}).status_code == 200


def test_modification_du_profil(client, membre):
    reponse = client.patch("/api/v1/auth/moi", json={"nom": "  Nouveau   nom "}, headers=membre)
    assert reponse.status_code == 200 and reponse.json["utilisateur"]["nom"] == "Nouveau nom"
    for corps in ({"nom": ""}, {"nom": "x" * 101}, {"nom": "Ok", "role": "admin"},
                  {"email": "a@b.fr"}):
        assert client.patch("/api/v1/auth/moi", json=corps, headers=membre).status_code == 400
    assert client.patch("/api/v1/auth/moi", json={"nom": "X"}).status_code == 401
    assert sql("SELECT role FROM utilisateurs")[0]["role"] == "membre"
