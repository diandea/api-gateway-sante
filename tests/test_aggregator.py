"""
Tests du composant d'agrégation.

Les trois API sont SIMULÉES par un transport HTTP factice (httpx.MockTransport) :
on peut ainsi provoquer à volonté une réponse normale, un 404, une erreur 500,
un service lent ou un service arrêté, sans rien démarrer.

Lancement : pytest -v tests/test_aggregator.py
"""

import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import load_app_module

agg = load_app_module("aggregator/main.py", "aggregator_main")

STRUCTURE = {"id": 1, "code": "CHU-YO", "nom": "CHU Yalgado Ouédraogo", "capacite_lits": 750}
INDICATEURS = {"structure_id": 1, "periode": "2026-09", "consultations": 9655, "deces": 0,
               "taux_couverture_vaccinale": None,
               "valeurs_nulles": {"taux_couverture_vaccinale": "NON_APPLICABLE"}}
PATIENTS = {"structure_id": 1, "total": 0, "par_sexe": {"F": 0, "M": 0}}

SERVICE_OF_PORT = {9001: "structures", 9002: "patients", 9003: "indicateurs"}
PAYLOAD = {"structures": STRUCTURE, "indicateurs": INDICATEURS, "patients": PATIENTS}


class FakeUpstreams:
    """Comportement de chaque service simulé : ok | absent | error | slow | down | badjson."""

    def __init__(self):
        self.mode = {"structures": "ok", "indicateurs": "ok", "patients": "ok"}
        self.delay = 5.0
        self.seen_headers = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen_headers.append(dict(request.headers))
        service = SERVICE_OF_PORT[request.url.port]
        mode = self.mode[service]
        if mode == "down":
            raise httpx.ConnectError("Connection refused", request=request)
        if mode == "slow":
            await asyncio.sleep(self.delay)
        if mode == "error":
            return httpx.Response(500, json={"error": "INTERNAL_ERROR"})
        if mode == "absent":
            return httpx.Response(404, json={"detail": {"error": "NOT_FOUND"}})
        if mode == "badjson":
            return httpx.Response(200, text="<html>pas du JSON</html>")
        return httpx.Response(200, json=PAYLOAD[service])


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(agg, "STRUCTURES_URL", "http://fake:9001")
    monkeypatch.setattr(agg, "PATIENTS_URL", "http://fake:9002")
    monkeypatch.setattr(agg, "INDICATEURS_URL", "http://fake:9003")
    monkeypatch.setattr(agg, "UPSTREAM_TIMEOUT", 0.5)   # tests rapides
    monkeypatch.setattr(agg, "GLOBAL_TIMEOUT", 1.0)
    fake = FakeUpstreams()
    with TestClient(agg.app) as client:
        agg.http_client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
        yield client, fake


def get_dashboard(client, sid=1, **headers):
    return client.get(f"/api/v1/dashboard/structures/{sid}", headers=headers)


# --- 1. Réponse complète ----------------------------------------------------
def test_reponse_complete(setup):
    client, _ = setup
    r = get_dashboard(client)
    body = r.json()
    assert r.status_code == 200
    assert body["statut_agregation"] == "COMPLET"
    assert r.headers["X-Aggregation-Status"] == "COMPLET"
    for section in ("structure", "indicateurs", "patients"):
        assert body[section]["statut"] == "DISPONIBLE"
    assert body["structure"]["donnees"]["code"] == "CHU-YO"


# --- 2. Données réellement nulles : conservées, pas confondues avec une panne
def test_valeurs_reellement_nulles_conservees(setup):
    client, _ = setup
    body = get_dashboard(client).json()
    assert body["statut_agregation"] == "COMPLET"
    assert body["patients"]["donnees"]["total"] == 0                       # zéro réel
    assert body["indicateurs"]["donnees"]["deces"] == 0                    # zéro réel
    assert body["indicateurs"]["donnees"]["taux_couverture_vaccinale"] is None  # null métier
    assert "erreur" not in body["indicateurs"]


def test_indicateurs_absents_ne_sont_pas_une_panne(setup):
    client, fake = setup
    fake.mode["indicateurs"] = "absent"            # 404 : rien n'a été publié
    body = get_dashboard(client).json()
    assert body["statut_agregation"] == "COMPLET"
    assert body["indicateurs"]["statut"] == "ABSENT"
    assert body["indicateurs"]["donnees"] is None


# --- 3. Erreurs partielles --------------------------------------------------
def test_erreur_partielle_service_en_erreur_500(setup):
    client, fake = setup
    fake.mode["patients"] = "error"
    r = get_dashboard(client)
    body = r.json()
    assert r.status_code == 200
    assert body["statut_agregation"] == "PARTIEL"
    assert body["patients"]["statut"] == "INDISPONIBLE"
    assert body["patients"]["donnees"] is None
    assert body["patients"]["erreur"]["code"] == "UPSTREAM_ERROR"
    assert body["indicateurs"]["statut"] == "DISPONIBLE"   # le reste est servi


def test_reponse_invalide(setup):
    client, fake = setup
    fake.mode["indicateurs"] = "badjson"
    body = get_dashboard(client).json()
    assert body["indicateurs"]["erreur"]["code"] == "INVALID_RESPONSE"


# --- 4. Délais dépassés -----------------------------------------------------
def test_delai_depasse(setup):
    client, fake = setup
    fake.mode["indicateurs"] = "slow"              # répondrait en 5 s
    start = time.perf_counter()
    body = get_dashboard(client).json()
    elapsed = time.perf_counter() - start
    assert body["statut_agregation"] == "PARTIEL"
    assert body["indicateurs"]["erreur"]["code"] == "TIMEOUT"
    assert elapsed < 1.0                           # coupé à 0,5 s, on n'attend pas 5 s


def test_budget_global(setup, monkeypatch):
    client, fake = setup
    monkeypatch.setattr(agg, "UPSTREAM_TIMEOUT", 10.0)  # délai individuel trop large...
    monkeypatch.setattr(agg, "GLOBAL_TIMEOUT", 0.3)     # ...le budget global coupe
    fake.mode["patients"] = "slow"
    body = get_dashboard(client).json()
    assert body["patients"]["erreur"]["code"] == "TIMEOUT"
    assert "Budget global" in body["patients"]["erreur"]["message"]


def test_appels_en_parallele(setup):
    """3 services lents de 0,3 s chacun : total ≈ 0,3 s (parallèle), pas 0,9 s (séquentiel)."""
    client, fake = setup
    fake.delay = 0.3
    fake.mode = {k: "slow" for k in fake.mode}
    start = time.perf_counter()
    assert get_dashboard(client).json()["statut_agregation"] == "COMPLET"
    assert time.perf_counter() - start < 0.7


# --- 5. Indisponibilité de services -----------------------------------------
def test_service_secondaire_injoignable(setup):
    client, fake = setup
    fake.mode["indicateurs"] = "down"
    body = get_dashboard(client).json()
    assert body["statut_agregation"] == "PARTIEL"
    assert body["indicateurs"]["erreur"]["code"] == "SERVICE_UNREACHABLE"


def test_tous_les_secondaires_indisponibles(setup):
    client, fake = setup
    fake.mode["indicateurs"] = "down"
    fake.mode["patients"] = "slow"
    r = get_dashboard(client)
    assert r.status_code == 200
    assert r.json()["structure"]["statut"] == "DISPONIBLE"


def test_service_principal_indisponible_503(setup):
    client, fake = setup
    fake.mode["structures"] = "down"
    r = get_dashboard(client)
    assert r.status_code == 503
    assert r.json()["erreur"]["code"] == "PRIMARY_SOURCE_UNAVAILABLE"


def test_structure_inexistante_404(setup):
    client, fake = setup
    fake.mode["structures"] = "absent"
    r = get_dashboard(client, 999)
    assert r.status_code == 404
    assert r.json()["erreur"]["code"] == "STRUCTURE_NOT_FOUND"


# --- 6. Identifiant de corrélation ------------------------------------------
def test_correlation_id_propage_aux_trois_services(setup):
    client, fake = setup
    r = get_dashboard(client, **{"X-Correlation-ID": "demo-42"})
    assert r.headers["X-Correlation-ID"] == "demo-42"
    assert r.json()["correlation_id"] == "demo-42"
    assert len(fake.seen_headers) == 3
    assert all(h["x-correlation-id"] == "demo-42" for h in fake.seen_headers)
