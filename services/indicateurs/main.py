"""
API 3 — Indicateurs agrégés.

Responsabilité unique : les indicateurs mensuels déjà agrégés par structure
(consultations, hospitalisations, taux d'occupation...).

Distinction importante pour l'agrégateur :
  - un indicateur à 0 (ex. deces = 0) est une valeur RÉELLE ;
  - un indicateur à null est accompagné de sa raison dans "valeurs_nulles"
    (ex. NON_APPLICABLE pour un CSPS qui n'a pas de lits) ;
  - une structure sans aucun indicateur publié renvoie 404 INDICATORS_NOT_FOUND.
Aucun de ces cas ne signifie "service indisponible".
"""

from typing import Optional

from fastapi import FastAPI, HTTPException

from common.data import load_data
from common.observability import setup_observability

app = FastAPI(
    title="API Indicateurs agrégés",
    version="1.0.0",
    description="Indicateurs mensuels de santé par structure (données fictives).",
)
logger = setup_observability(app, "indicateurs-api")

INDICATEURS = load_data("indicateurs")

# Raison métier de chaque valeur null connue.
NULL_REASONS = {
    "taux_occupation_lits": "NON_APPLICABLE: structure sans lits d'hospitalisation",
    "duree_moyenne_sejour_jours": "NON_APPLICABLE: structure sans hospitalisation",
    "taux_couverture_vaccinale": "NON_APPLICABLE: vaccination non réalisée dans cette structure",
}


def _with_null_reasons(record: dict) -> dict:
    nulls = {k: NULL_REASONS.get(k, "NON_RENSEIGNE") for k, v in record.items() if v is None}
    return {**record, "valeurs_nulles": nulls}


@app.get("/api/v1/indicateurs")
async def list_indicateurs(periode: Optional[str] = None):
    items = [i for i in INDICATEURS if periode is None or i["periode"] == periode]
    return {"count": len(items), "items": [_with_null_reasons(i) for i in items]}


@app.get("/api/v1/indicateurs/structures/{structure_id}")
async def indicateurs_structure(structure_id: int, periode: Optional[str] = None):
    records = [i for i in INDICATEURS if i["structure_id"] == structure_id]
    if not records:
        logger.info("indicators_not_found", extra={"fields": {"structure_id": structure_id}})
        raise HTTPException(
            status_code=404,
            detail={"error": "INDICATORS_NOT_FOUND", "structure_id": structure_id},
        )
    if periode:
        records = [i for i in records if i["periode"] == periode]
        if not records:
            raise HTTPException(
                status_code=404,
                detail={"error": "PERIOD_NOT_FOUND", "structure_id": structure_id, "periode": periode},
            )
    latest = max(records, key=lambda r: r["periode"])
    return _with_null_reasons(latest)
