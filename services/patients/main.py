"""
API 2 — Patients fictifs.

Responsabilité unique : les dossiers patients (fictifs) et leurs statistiques
de base. Elle ne connaît des structures que leur identifiant (structure_id).
"""

from collections import Counter
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from common.data import load_data
from common.observability import setup_observability

app = FastAPI(
    title="API Patients fictifs",
    version="1.0.0",
    description="Patients FICTIFS générés pour le projet (aucune donnée réelle).",
)
logger = setup_observability(app, "patients-api")

PATIENTS = load_data("patients")
REFERENCE_DATE = date(2026, 10, 1)


def _age(p: dict) -> int:
    born = date.fromisoformat(p["date_naissance"])
    return REFERENCE_DATE.year - born.year - (
        (REFERENCE_DATE.month, REFERENCE_DATE.day) < (born.month, born.day)
    )


def _tranche(age: int) -> str:
    if age < 5:
        return "0-4"
    if age < 15:
        return "5-14"
    if age < 50:
        return "15-49"
    return "50+"


@app.get("/api/v1/patients")
async def list_patients(
    structure_id: Optional[int] = None,
    statut: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
):
    result = PATIENTS
    if structure_id is not None:
        result = [p for p in result if p["structure_id"] == structure_id]
    if statut:
        result = [p for p in result if p["statut"] == statut]
    return {"count": len(result), "items": result[:limit]}


# Déclarée AVANT /{patient_id} pour que "stats" ne soit pas pris pour un identifiant.
@app.get("/api/v1/patients/stats")
async def patient_stats(structure_id: int):
    """
    Statistiques des patients d'une structure.
    Une structure sans patient renvoie total = 0 : c'est une valeur
    réellement nulle, pas une absence de données.
    """
    subset = [p for p in PATIENTS if p["structure_id"] == structure_id]
    return {
        "structure_id": structure_id,
        "total": len(subset),
        "par_sexe": {"F": 0, "M": 0, **Counter(p["sexe"] for p in subset)},
        "par_statut": {
            "ambulatoire": 0, "hospitalise": 0, "sorti": 0,
            **Counter(p["statut"] for p in subset),
        },
        "par_tranche_age": {
            "0-4": 0, "5-14": 0, "15-49": 0, "50+": 0,
            **Counter(_tranche(_age(p)) for p in subset),
        },
    }


@app.get("/api/v1/patients/{patient_id}")
async def get_patient(patient_id: str):
    for p in PATIENTS:
        if p["id"] == patient_id:
            return p
    raise HTTPException(status_code=404, detail={"error": "PATIENT_NOT_FOUND", "patient_id": patient_id})
