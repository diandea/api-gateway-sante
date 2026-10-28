"""
Tests unitaires des trois API métier (chacune testée isolément).
Lancement : pytest -v tests/test_services.py
"""

from fastapi.testclient import TestClient

from conftest import load_app_module

structures = TestClient(load_app_module("services/structures/main.py", "structures_main").app)
patients = TestClient(load_app_module("services/patients/main.py", "patients_main").app)
indicateurs = TestClient(load_app_module("services/indicateurs/main.py", "indicateurs_main").app)


# --- API Structures ---------------------------------------------------------
def test_structure_existante():
    r = structures.get("/api/v1/structures/1")
    assert r.status_code == 200
    assert r.json()["code"] == "CHU-YO"


def test_structure_inexistante_renvoie_404():
    r = structures.get("/api/v1/structures/999")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "STRUCTURE_NOT_FOUND"


def test_filtre_par_region():
    r = structures.get("/api/v1/structures", params={"region": "Centre"})
    assert r.json()["count"] == 3


# --- API Patients -----------------------------------------------------------
def test_stats_patients():
    body = patients.get("/api/v1/patients/stats", params={"structure_id": 1}).json()
    assert body["total"] == 25
    assert sum(body["par_sexe"].values()) == 25


def test_structure_sans_patient_donne_un_zero_reel():
    """Structure 5 : aucun patient. Le service répond 200 avec total = 0."""
    r = patients.get("/api/v1/patients/stats", params={"structure_id": 5})
    assert r.status_code == 200
    assert r.json()["total"] == 0


# --- API Indicateurs --------------------------------------------------------
def test_indicateurs_derniere_periode_par_defaut():
    body = indicateurs.get("/api/v1/indicateurs/structures/2").json()
    assert body["periode"] == "2026-09"


def test_null_metier_accompagne_de_sa_raison():
    body = indicateurs.get("/api/v1/indicateurs/structures/4").json()
    assert body["taux_occupation_lits"] is None
    assert body["valeurs_nulles"]["taux_occupation_lits"].startswith("NON_APPLICABLE")
    assert body["deces"] == 0  # zéro réel, pas un null


def test_structure_sans_indicateur_renvoie_404():
    r = indicateurs.get("/api/v1/indicateurs/structures/5")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "INDICATORS_NOT_FOUND"


# --- Observabilité commune --------------------------------------------------
def test_correlation_id_renvoye_ou_genere():
    r = structures.get("/api/v1/structures/1", headers={"X-Correlation-ID": "abc-123"})
    assert r.headers["X-Correlation-ID"] == "abc-123"
    r = structures.get("/api/v1/structures/1")
    assert len(r.headers["X-Correlation-ID"]) == 36  # UUID généré


def test_mode_chaos_error():
    patients.post("/_chaos", json={"mode": "error"})
    try:
        assert patients.get("/api/v1/patients/stats", params={"structure_id": 1}).status_code == 500
        assert patients.get("/health").status_code == 200  # routes techniques épargnées
    finally:
        patients.post("/_chaos", json={"mode": "normal"})
