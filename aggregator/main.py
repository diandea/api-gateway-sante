"""
Composant d'agrégation — tableau de bord d'une structure sanitaire.

    GET /api/v1/dashboard/structures/{id}

Il appelle EN PARALLÈLE les trois API (structures, indicateurs, patients),
puis assemble une réponse unique. Il ne contient AUCUNE règle métier propre
aux structures, aux patients ou aux indicateurs : il orchestre seulement.

Stratégie d'erreurs partielles — chaque section porte un "statut" :
  DISPONIBLE   le service a répondu ; "donnees" contient sa réponse.
               Un 0 ou un null DANS les données est une valeur réelle.
  ABSENT       le service a répondu "il n'existe rien" (HTTP 404).
               C'est une donnée réellement nulle, pas une panne.
  INDISPONIBLE le service n'a pas pu répondre (délai dépassé, service
               injoignable, erreur 5xx, réponse invalide). "donnees" vaut
               null et "erreur" explique pourquoi : on NE SAIT PAS.

Règles de composition :
  - structure = donnée PRINCIPALE : ABSENT -> HTTP 404 ; INDISPONIBLE -> HTTP 503.
  - indicateurs, patients = données SECONDAIRES : leur indisponibilité donne
    HTTP 200 avec statut_agregation = "PARTIEL".
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from common.observability import CORRELATION_HEADER, correlation_id_var, setup_observability


# ---------------------------------------------------------------------------
# Contrat de réponse (documentation OpenAPI ; la réponse est construite à la main)
# ---------------------------------------------------------------------------
class Erreur(BaseModel):
    code: str = Field(description="TIMEOUT | SERVICE_UNREACHABLE | UPSTREAM_ERROR | "
                                  "INVALID_RESPONSE | STRUCTURE_NOT_FOUND | PRIMARY_SOURCE_UNAVAILABLE")
    message: str


class Section(BaseModel):
    statut: Literal["DISPONIBLE", "ABSENT", "INDISPONIBLE"] = Field(
        description="DISPONIBLE : le service a répondu (un 0 ou un null dans les données est réel). "
                    "ABSENT : le service a répondu 404, donnée réellement nulle. "
                    "INDISPONIBLE : le service n'a pas pu répondre, valeur inconnue.")
    donnees: Optional[Any] = Field(description="Réponse du service, null si ABSENT ou INDISPONIBLE")
    motif: Optional[Any] = Field(None, description="Présent si ABSENT : détail du 404")
    erreur: Optional[Erreur] = Field(None, description="Présent si INDISPONIBLE")


class Source(BaseModel):
    service: str
    statut: Literal["DISPONIBLE", "ABSENT", "INDISPONIBLE"]
    http_status: Optional[int]
    duree_ms: Optional[float]


class Dashboard(BaseModel):
    structure_id: int
    statut_agregation: Literal["COMPLET", "PARTIEL", "ECHEC"]
    correlation_id: str
    genere_le: str = Field(description="Horodatage ISO 8601 (UTC)")
    structure: Section
    indicateurs: Section
    patients: Section
    sources: list[Source]
    erreur: Optional[Erreur] = Field(None, description="Présent si statut_agregation = ECHEC")

# ---------------------------------------------------------------------------
# Configuration (variables d'environnement, valeurs par défaut pour le local)
# ---------------------------------------------------------------------------
STRUCTURES_URL = os.getenv("STRUCTURES_URL", "http://localhost:9001")
INDICATEURS_URL = os.getenv("INDICATEURS_URL", "http://localhost:9003")
PATIENTS_URL = os.getenv("PATIENTS_URL", "http://localhost:9002")

# Délai maximal accordé à CHAQUE service (secondes).
UPSTREAM_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "2.0"))
# Budget global de l'agrégation : filet de sécurité au-dessus des délais
# individuels, et toujours INFÉRIEUR au read_timeout de Kong (5 s).
GLOBAL_TIMEOUT = float(os.getenv("GLOBAL_TIMEOUT", "3.0"))

DISPONIBLE, ABSENT, INDISPONIBLE = "DISPONIBLE", "ABSENT", "INDISPONIBLE"

http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Un seul client HTTP réutilisé : connexions gardées ouvertes (keep-alive).
    global http_client
    http_client = httpx.AsyncClient()
    yield
    await http_client.aclose()


app = FastAPI(
    title="Composant d'agrégation — Dashboard santé",
    version="1.0.0",
    description="Rassemble structures, indicateurs et patients en une réponse unique.",
    lifespan=lifespan,
)
logger = setup_observability(app, "aggregator")


# ---------------------------------------------------------------------------
# Appel d'un service en aval
# ---------------------------------------------------------------------------
async def call_upstream(service: str, url: str, params: dict | None = None) -> dict:
    """
    Appelle un service et renvoie TOUJOURS un résultat décrit (jamais
    d'exception) : {"statut", "donnees", "erreur", "http_status", "duree_ms"}.
    """
    start = time.perf_counter()
    headers = {CORRELATION_HEADER: correlation_id_var.get()}  # propagation
    result = {"service": service, "statut": INDISPONIBLE, "donnees": None,
              "erreur": None, "http_status": None}
    try:
        # wait_for borne la durée TOTALE de l'appel (connexion + lecture).
        resp = await asyncio.wait_for(
            http_client.get(url, params=params, headers=headers),
            timeout=UPSTREAM_TIMEOUT,
        )
        result["http_status"] = resp.status_code
        if resp.status_code == 200:
            result["statut"], result["donnees"] = DISPONIBLE, resp.json()
        elif resp.status_code == 404:
            result["statut"] = ABSENT
            result["motif"] = _detail(resp)
        else:
            result["erreur"] = {"code": "UPSTREAM_ERROR",
                                "message": f"Le service a répondu HTTP {resp.status_code}"}
    except (asyncio.TimeoutError, httpx.TimeoutException):
        result["erreur"] = {"code": "TIMEOUT",
                            "message": f"Pas de réponse en moins de {UPSTREAM_TIMEOUT} s"}
    except httpx.TransportError as exc:  # connexion refusée, DNS, réseau...
        result["erreur"] = {"code": "SERVICE_UNREACHABLE",
                            "message": f"Service injoignable ({type(exc).__name__})"}
    except ValueError:  # corps non JSON
        result["erreur"] = {"code": "INVALID_RESPONSE",
                            "message": "Réponse illisible (JSON invalide)"}

    result["duree_ms"] = round((time.perf_counter() - start) * 1000, 1)
    log = logger.info if result["statut"] != INDISPONIBLE else logger.warning
    log("upstream_call", extra={"fields": {
        "upstream": service, "url": url, "params": params,
        "outcome": result["statut"], "http_status": result["http_status"],
        "error_code": (result["erreur"] or {}).get("code"),
        "duration_ms": result["duree_ms"],
    }})
    return result


def _detail(resp: httpx.Response):
    try:
        return resp.json().get("detail")
    except ValueError:
        return None


def _section(r: dict) -> dict:
    """Forme publique d'une section du tableau de bord."""
    section = {"statut": r["statut"], "donnees": r["donnees"]}
    if r["statut"] == ABSENT:
        section["motif"] = r.get("motif")
    if r["statut"] == INDISPONIBLE:
        section["erreur"] = r["erreur"]
    return section


# ---------------------------------------------------------------------------
# Endpoint d'agrégation
# ---------------------------------------------------------------------------
@app.get(
    "/api/v1/dashboard/structures/{structure_id}",
    summary="Tableau de bord d'une structure sanitaire",
    response_model=None,
    responses={
        200: {"model": Dashboard, "description": "COMPLET, ou PARTIEL si indicateurs et/ou patients sont INDISPONIBLE"},
        404: {"model": Dashboard, "description": "ECHEC : structure inconnue (STRUCTURE_NOT_FOUND)"},
        503: {"model": Dashboard, "description": "ECHEC : API structures indisponible (PRIMARY_SOURCE_UNAVAILABLE)"},
    },
)
async def dashboard_structure(structure_id: int):
    start = time.perf_counter()
    calls = {
        "structure": call_upstream(
            "structures", f"{STRUCTURES_URL}/api/v1/structures/{structure_id}"),
        "indicateurs": call_upstream(
            "indicateurs", f"{INDICATEURS_URL}/api/v1/indicateurs/structures/{structure_id}"),
        "patients": call_upstream(
            "patients", f"{PATIENTS_URL}/api/v1/patients/stats", {"structure_id": structure_id}),
    }
    tasks = {name: asyncio.create_task(coro) for name, coro in calls.items()}

    # Les trois appels partent en même temps : la durée totale ≈ le plus lent,
    # pas la somme. Le budget global coupe tout ce qui dépasse.
    done, pending = await asyncio.wait(tasks.values(), timeout=GLOBAL_TIMEOUT)
    for t in pending:
        t.cancel()

    results = {}
    for name, task in tasks.items():
        if task in done:
            results[name] = task.result()
        else:
            results[name] = {"service": name, "statut": INDISPONIBLE, "donnees": None,
                             "http_status": None, "duree_ms": None,
                             "erreur": {"code": "TIMEOUT",
                                        "message": f"Budget global de {GLOBAL_TIMEOUT} s dépassé"}}

    # --- Composition de la réponse -----------------------------------------
    struct = results["structure"]
    if struct["statut"] == ABSENT:
        http_status, statut = 404, "ECHEC"
    elif struct["statut"] == INDISPONIBLE:
        http_status, statut = 503, "ECHEC"
    elif any(r["statut"] == INDISPONIBLE for r in results.values()):
        http_status, statut = 200, "PARTIEL"
    else:
        http_status, statut = 200, "COMPLET"

    body = {
        "structure_id": structure_id,
        "statut_agregation": statut,
        "correlation_id": correlation_id_var.get(),
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "structure": _section(struct),
        "indicateurs": _section(results["indicateurs"]),
        "patients": _section(results["patients"]),
        "sources": [
            {"service": r["service"], "statut": r["statut"],
             "http_status": r["http_status"], "duree_ms": r["duree_ms"]}
            for r in results.values()
        ],
    }
    if http_status == 404:
        body["erreur"] = {"code": "STRUCTURE_NOT_FOUND",
                          "message": f"Aucune structure avec l'identifiant {structure_id}"}
    elif http_status == 503:
        body["erreur"] = {"code": "PRIMARY_SOURCE_UNAVAILABLE",
                          "message": "Le service des structures est indisponible"}

    logger.info("aggregation_completed", extra={"fields": {
        "structure_id": structure_id, "statut_agregation": statut,
        "http_status": http_status,
        "sources": {n: r["statut"] for n, r in results.items()},
        "duration_ms": round((time.perf_counter() - start) * 1000, 1),
    }})
    return JSONResponse(status_code=http_status, content=body,
                        headers={"X-Aggregation-Status": statut})
