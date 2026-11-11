# Image Flask du tiers d'accès aux données (API REST).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Compte sans privilège : le serveur ne tourne jamais en root.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin appli

# Le code est copié dans l'image ; docker-compose monte en plus le dossier app/
# de l'hôte par-dessus, en lecture seule (volume partagé demandé par le sujet).
COPY demarrage.sh gunicorn.conf.py ./
COPY app/ app/

USER appli
EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/v1/sante', timeout=2)"]

# Serveur WSGI de production (le serveur de développement de Flask, avec son
# débogueur, n'est utilisé que par docker-compose.dev.yml).
ENTRYPOINT ["sh", "/srv/demarrage.sh"]
CMD ["gunicorn", "--config", "/srv/gunicorn.conf.py", "app:create_app()"]
