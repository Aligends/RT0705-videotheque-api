# Image Flask du tiers d'accès aux données (API REST).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Le code est copié dans l'image ; en développement, docker-compose monte
# le dossier app/ de l'hôte par-dessus (volume partagé, rechargement à chaud).
COPY app/ app/

EXPOSE 5000
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
