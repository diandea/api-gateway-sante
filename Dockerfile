# Image unique pour les 4 services Python.
# Le service à embarquer est choisi au build : --build-arg SERVICE_DIR=services/patients
FROM python:3.12-slim

ARG SERVICE_DIR
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common ./common
# Copie des bases de test : valeur par défaut, remplacée par le volume
# ./data monté dans docker-compose.yml.
COPY data ./data
COPY ${SERVICE_DIR} ./svc

WORKDIR /app/svc
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"

# --no-access-log : nos propres journaux JSON remplacent ceux d'uvicorn.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
