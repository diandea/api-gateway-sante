"""
Outils d'observabilité partagés par les 4 services Python.

Ce module fournit :
  1. Des journaux structurés au format JSON (une ligne JSON par événement).
  2. Un middleware qui lit ou génère l'identifiant de corrélation
     (en-tête X-Correlation-ID), le rend disponible partout dans la requête
     et le renvoie dans la réponse.
  3. Un "mode chaos" activable à chaud (POST /_chaos) pour simuler
     des pannes pendant les tests et la démonstration :
       - normal : le service répond normalement
       - slow   : le service attend N secondes avant de répondre (timeout)
       - error  : le service répond 500 (panne applicative)
"""

import asyncio
import contextvars
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

CORRELATION_HEADER = "X-Correlation-ID"

# Variable de contexte : chaque requête (même traitée en parallèle avec
# d'autres) possède sa propre valeur d'identifiant de corrélation.
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)


# ---------------------------------------------------------------------------
# 1. Journaux structurés (JSON)
# ---------------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    """Transforme chaque enregistrement de log en une ligne JSON."""

    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self.service_name,
            "correlation_id": correlation_id_var.get(),
            "event": record.getMessage(),
        }
        # Les champs passés via logger.info("...", extra={"fields": {...}})
        fields = getattr(record, "fields", None)
        if fields:
            entry.update(fields)
        return json.dumps(entry, ensure_ascii=False)


def get_logger(service_name: str) -> logging.Logger:
    logger = logging.getLogger(service_name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter(service_name))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# 2 & 3. Middleware (corrélation + journal d'accès) et mode chaos
# ---------------------------------------------------------------------------
class ChaosConfig(BaseModel):
    mode: str = "normal"  # normal | slow | error
    delay: float = 5.0    # secondes, utilisé en mode "slow"


def setup_observability(app: FastAPI, service_name: str) -> logging.Logger:
    logger = get_logger(service_name)
    chaos = ChaosConfig()

    @app.middleware("http")
    async def correlation_and_access_log(request: Request, call_next):
        # Kong ajoute l'en-tête ; s'il manque (appel direct), on en génère un.
        cid = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        token = correlation_id_var.set(cid)
        start = time.perf_counter()
        try:
            # Le mode chaos ne s'applique pas aux routes techniques.
            if not request.url.path.startswith(("/_chaos", "/health")):
                if chaos.mode == "slow":
                    await asyncio.sleep(chaos.delay)
                elif chaos.mode == "error":
                    response = JSONResponse(
                        status_code=500,
                        content={"error": "INTERNAL_ERROR", "detail": "Panne simulée"},
                    )
                    response.headers[CORRELATION_HEADER] = cid
                    _log_access(logger, request, 500, start)
                    return response

            response = await call_next(request)
            response.headers[CORRELATION_HEADER] = cid
            _log_access(logger, request, response.status_code, start)
            return response
        finally:
            correlation_id_var.reset(token)

    @app.get("/health", tags=["technique"])
    async def health():
        return {"status": "up", "service": service_name}

    @app.get("/_chaos", tags=["technique"])
    async def get_chaos():
        return chaos

    @app.post("/_chaos", tags=["technique"])
    async def set_chaos(cfg: ChaosConfig):
        chaos.mode, chaos.delay = cfg.mode, cfg.delay
        logger.warning("chaos_mode_changed", extra={"fields": cfg.model_dump()})
        return chaos

    return logger


def _log_access(logger: logging.Logger, request: Request, status: int, start: float):
    # Les sondes /health de Docker (toutes les 10 s) noieraient les journaux utiles.
    if request.url.path == "/health":
        return
    logger.info(
        "http_request",
        extra={
            "fields": {
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query) or None,
                "status": status,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            }
        },
    )
