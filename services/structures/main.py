"""
API 1 — Structures sanitaires.

Responsabilité unique : le référentiel des structures (identité, localisation,
capacité). Elle ne sait rien des patients ni des indicateurs.
"""

from typing import Optional

from fastapi import FastAPI, HTTPException

from common.data import load_data
from common.observability import setup_observability

app = FastAPI(
    title="API Structures sanitaires",
    version="1.0.0",
    description="Référentiel des structures de santé (données fictives).",
)
logger = setup_observability(app, "structures-api")

STRUCTURES = load_data("structures")
BY_ID = {s["id"]: s for s in STRUCTURES}


@app.get("/api/v1/structures")
async def list_structures(region: Optional[str] = None, type: Optional[str] = None):
    result = STRUCTURES
    if region:
        result = [s for s in result if s["region"].lower() == region.lower()]
    if type:
        result = [s for s in result if s["type"].lower() == type.lower()]
    return {"count": len(result), "items": result}


@app.get("/api/v1/structures/{structure_id}")
async def get_structure(structure_id: int):
    structure = BY_ID.get(structure_id)
    if structure is None:
        logger.info("structure_not_found", extra={"fields": {"structure_id": structure_id}})
        raise HTTPException(
            status_code=404,
            detail={"error": "STRUCTURE_NOT_FOUND", "structure_id": structure_id},
        )
    return structure
