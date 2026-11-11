"""Configuration de gunicorn, le serveur WSGI qui exécute l'API dans le conteneur."""
import logging

bind = "0.0.0.0:5000"
workers = 2
threads = 4
# Le système de fichiers du conteneur est en lecture seule : les fichiers de
# travail de gunicorn vont en mémoire et son canal de commande est désactivé.
worker_tmp_dir = "/dev/shm"
control_socket_disable = True
# Journal des requêtes sur la sortie standard (docker compose logs api).
accesslog = "-"


class _SansControleDeSante(logging.Filter):
    """Le contrôle de santé de Docker passe toutes les dix secondes : il n'est pas journalisé."""

    def filter(self, record):
        return " /api/v1/sante " not in record.getMessage()


logging.getLogger("gunicorn.access").addFilter(_SansControleDeSante())
