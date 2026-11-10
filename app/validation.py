"""Contrôle des données reçues : champs autorisés, types, longueurs, valeurs."""
import unicodedata
from datetime import date
from urllib.parse import urlsplit

from flask import request

from .erreurs import ErreurAPI


def _controle_interdit(caractere, multiligne):
    if multiligne and caractere in "\n\t":
        return False
    return unicodedata.category(caractere) == "Cc"   # caractères de contrôle, dont NUL


class Validateur:
    """Lit les champs d'un objet JSON et accumule les erreurs, champ par champ.

    Seuls les champs listés dans ``champs`` sont acceptés : un client ne peut
    donc pas fixer une colonne qu'il n'est pas censé modifier (identifiant,
    rôle, auteur...).
    """

    def __init__(self, donnees, champs):
        self.donnees = donnees
        self.erreurs = {str(champ)[:50]: "Champ inconnu ou non modifiable."
                        for champ in donnees if champ not in champs}

    def __contains__(self, champ):
        return champ in self.donnees

    def erreur(self, champ, message):
        self.erreurs[champ] = message
        return None

    def _absent(self, champ, obligatoire):
        if obligatoire:
            self.erreurs[champ] = "Obligatoire."
        return None

    def texte(self, champ, maxi, obligatoire=False, multiligne=False):
        valeur = self.donnees.get(champ)
        if valeur is None:
            return self._absent(champ, obligatoire)
        if not isinstance(valeur, str):
            return self.erreur(champ, "Doit être une chaîne de caractères.")
        if multiligne:
            valeur = valeur.replace("\r\n", "\n").replace("\r", "\n").strip()
        else:
            valeur = " ".join(valeur.split())       # une seule ligne, espaces normalisés
        if any(_controle_interdit(c, multiligne) for c in valeur):
            return self.erreur(champ, "Contient des caractères non autorisés.")
        if not valeur:
            return self._absent(champ, obligatoire)
        if len(valeur) > maxi:
            return self.erreur(champ, f"{maxi} caractères au plus.")
        return valeur

    def entier(self, champ, mini, maxi, obligatoire=False):
        valeur = self.donnees.get(champ)
        if valeur is None:
            return self._absent(champ, obligatoire)
        if isinstance(valeur, bool) or not isinstance(valeur, int) or not mini <= valeur <= maxi:
            return self.erreur(champ, f"Doit être un entier entre {mini} et {maxi}.")
        return valeur

    def booleen(self, champ, obligatoire=False):
        valeur = self.donnees.get(champ)
        if valeur is None:
            return self._absent(champ, obligatoire)
        if not isinstance(valeur, bool):
            return self.erreur(champ, "Doit être un booléen (true ou false).")
        return valeur

    def choix(self, champ, valeurs, obligatoire=False):
        valeur = self.donnees.get(champ)
        if valeur is None:
            return self._absent(champ, obligatoire)
        if not isinstance(valeur, str) or valeur not in valeurs:
            return self.erreur(champ, "Doit valoir " + " ou ".join(f"« {v} »" for v in valeurs) + ".")
        return valeur

    def date(self, champ, obligatoire=False):
        valeur = self.donnees.get(champ)
        if valeur is None or valeur == "":
            return self._absent(champ, obligatoire)
        if isinstance(valeur, str) and len(valeur) == 10:
            try:
                return date.fromisoformat(valeur)
            except ValueError:
                pass
        return self.erreur(champ, "Date attendue au format AAAA-MM-JJ.")

    def url_https(self, champ, maxi):
        valeur = self.texte(champ, maxi)
        if valeur is None:
            return None
        try:
            morceaux = urlsplit(valeur)
            correcte = morceaux.scheme == "https" and bool(morceaux.hostname) and " " not in valeur
        except ValueError:
            correcte = False
        if not correcte:
            return self.erreur(champ, "Doit être une adresse commençant par https://")
        return valeur

    def liste_textes(self, champ, longueur_maxi, nombre_maxi):
        """Liste de chaînes non vides, sans doublon (casse ignorée)."""
        valeur = self.donnees.get(champ)
        if valeur is None:
            return []
        message = (f"Doit être une liste d'au plus {nombre_maxi} noms "
                   f"({longueur_maxi} caractères au plus chacun).")
        if not isinstance(valeur, list) or len(valeur) > nombre_maxi:
            return self.erreur(champ, message)
        resultat, vus = [], set()
        for element in valeur:
            if not isinstance(element, str):
                return self.erreur(champ, message)
            texte = " ".join(element.split())
            if (not texte or len(texte) > longueur_maxi
                    or any(_controle_interdit(c, False) for c in texte)):
                return self.erreur(champ, message)
            if texte.lower() not in vus:
                vus.add(texte.lower())
                resultat.append(texte)
        return resultat

    def verifier(self):
        if self.erreurs:
            raise ErreurAPI(400, "Données invalides.", self.erreurs)


# --- paramètres passés dans l'URL -------------------------------------

def parametre_entier(nom, defaut, mini, maxi):
    brut = request.args.get(nom)
    if brut is None or brut == "":
        return defaut
    try:
        valeur = int(brut)
    except ValueError:
        raise ErreurAPI(400, f"Le paramètre « {nom} » doit être un entier.")
    if not mini <= valeur <= maxi:
        raise ErreurAPI(400, f"Le paramètre « {nom} » doit être entre {mini} et {maxi}.")
    return valeur


def parametre_booleen(nom):
    brut = request.args.get(nom, "").lower()
    if brut == "":
        return None
    if brut in ("1", "true", "oui"):
        return True
    if brut in ("0", "false", "non"):
        return False
    raise ErreurAPI(400, f"Le paramètre « {nom} » doit valoir true ou false.")


def pagination(par_page_defaut=20):
    """Renvoie (page, par_page, décalage) à partir de ?page= et ?par_page=."""
    page = parametre_entier("page", 1, 1, 100_000)
    par_page = parametre_entier("par_page", par_page_defaut, 1, 100)
    return page, par_page, (page - 1) * par_page


def bloc_pagination(page, par_page, total):
    return {"page": page, "par_page": par_page, "total": total,
            "pages": max(1, -(-total // par_page))}


def echapper_like(texte):
    """Neutralise les jokers de LIKE (% et _) dans un texte saisi."""
    return texte.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
