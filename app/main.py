import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

logger = logging.getLogger(__name__)

from app.agents import (
    AgricultureAgent,
    AnalysisAgent,
    EconomyAgent,
    EducationAgent,
    EnergyAgent,
    EnvironmentAgent,
    HealthAgent,
    MarketsAgent,
    TransportAgent,
)
from app.agents.ds_insights import (
    compute_cross_sector_correlations,
    compute_freshness_scores,
    compute_seasonal_anomalies,
    compute_spatial_coverage,
)
from app.config import settings
from app.security import require_analysis_rate_limit, require_collection_access, require_collection_rate_limit
from app.services.export import observations_to_csv, observations_to_json, observations_to_parquet, observations_to_xml
from app.services.scheduler import scheduler_service
from app.services.storage import ObservationRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Start the automated background data harvester on application startup
    scheduler_service.start()
    yield
    # Stop background harvester on shutdown
    scheduler_service.stop()


app = FastAPI(
    title="FreeDatatd API",
    version="0.2.0",
    description="Open socioeconomic data infrastructure for Chad with automated data harvesting.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class NoCacheJSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/js/") or path.startswith("/static/css/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

repository = ObservationRepository()
STATIC_DIR = Path(__file__).parent / "static"
DASHBOARD = STATIC_DIR / "index.html"

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(NoCacheJSMiddleware)


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})



@app.get("/api/v1/health")
def health() -> dict:
    return {
        "status": "ok",
        "project": "FreeDatatd",
        "storage_backend": repository.backend,
        "scheduler": scheduler_service.get_status(),
    }


@app.get("/api/v1/observations")
def observations(sector: str | None = None, region: str | None = None, limit: int = Query(default=200, ge=1, le=5000)) -> list[dict]:
    return repository.list_observations(sector=sector, region=region, limit=limit)


@app.get("/api/v1/catalog")
def catalog() -> list[dict]:
    return repository.catalog()


@app.get("/api/v1/regions")
def regions() -> list[str]:
    """Distinct regions actually present in the data — lets the frontend
    build a real, always-current region filter instead of a hardcoded list."""
    return repository.list_regions()


@app.get("/api/v1/studies")
def list_studies(sector: str | None = None, limit: int = Query(default=20, ge=1, le=100)) -> dict:
    """Public, read-only report library — no LLM call, safe to fetch on every page load.

    For each study, also reports the *live* observation count for its sector so the
    frontend can flag whether new data has arrived since the report was generated,
    without ever triggering a regeneration automatically.
    """
    studies = repository.list_studies(sector=sector, limit=limit)
    live_counts: dict[str, int] = {}
    for study in studies:
        study_sector = study.get("sector") or "all"
        if study_sector not in live_counts:
            live_counts[study_sector] = repository.count_observations(
                sector=None if study_sector == "all" else study_sector
            )
        study["live_observations_count"] = live_counts[study_sector]
        study["is_stale"] = live_counts[study_sector] > (study.get("observations_used") or 0)
    return {"studies": studies}


@app.get("/api/v1/pipeline/audit")
def pipeline_audit() -> dict:
    return repository.get_pipeline_audit()



def _safe_filename_part(sector: str | None) -> str:
    """Sanitize a query param before it goes into an HTTP header value
    (Content-Disposition filename) - strips anything that isn't alphanumeric,
    hyphen or underscore, preventing header-value/quote injection."""
    if not sector:
        return "all"
    cleaned = "".join(c for c in sector if c.isalnum() or c in "-_")
    return cleaned or "all"


@app.get("/api/v1/export/csv", response_class=PlainTextResponse)
def export_csv(sector: str | None = None, region: str | None = None) -> PlainTextResponse:
    rows = repository.list_observations(sector=sector, region=region, limit=5000)
    content = observations_to_csv(rows)
    name_parts = _safe_filename_part(sector)
    if region:
        name_parts += f"-{_safe_filename_part(region)}"
    filename = f"freedatatd-{name_parts}-export.csv"
    return PlainTextResponse(
        content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="text/csv",
    )


@app.get("/api/v1/export/json")
def export_json(sector: str | None = None, region: str | None = None) -> JSONResponse:
    rows = repository.list_observations(sector=sector, region=region, limit=5000)
    name_parts = _safe_filename_part(sector)
    if region:
        name_parts += f"-{_safe_filename_part(region)}"
    filename = f"freedatatd-{name_parts}-export.json"
    return JSONResponse(
        content=rows,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/v1/export/xml", response_class=PlainTextResponse)
def export_xml(sector: str | None = None, region: str | None = None) -> PlainTextResponse:
    rows = repository.list_observations(sector=sector, region=region, limit=5000)
    content = observations_to_xml(rows)
    name_parts = _safe_filename_part(sector)
    if region:
        name_parts += f"-{_safe_filename_part(region)}"
    filename = f"freedatatd-{name_parts}-export.xml"
    return PlainTextResponse(
        content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="application/xml",
    )


@app.get("/api/v1/export/parquet")
def export_parquet(sector: str | None = None, region: str | None = None) -> Response:
    rows = repository.list_observations(sector=sector, region=region, limit=5000)
    try:
        content = observations_to_parquet(rows)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    name_parts = _safe_filename_part(sector)
    if region:
        name_parts += f"-{_safe_filename_part(region)}"
    filename = f"freedatatd-{name_parts}-export.parquet"
    return Response(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="application/octet-stream",
    )


@app.post("/api/v1/collection/agriculture", status_code=202, dependencies=[Depends(require_collection_rate_limit)])
async def collect_agriculture(source: str = "all") -> dict:
    try:
        return (await AgricultureAgent(repository).run(source)).model_dump(mode="json")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/environment", status_code=202, dependencies=[Depends(require_collection_rate_limit)])
async def collect_environment(source: str = "all") -> dict:
    try:
        return (await EnvironmentAgent(repository).run(source)).model_dump(mode="json")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/markets", status_code=202, dependencies=[Depends(require_collection_rate_limit)])
async def collect_markets(source: str = "all") -> dict:
    try:
        return (await MarketsAgent(repository).run(source)).model_dump(mode="json")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/economy", status_code=202, dependencies=[Depends(require_collection_rate_limit)])
async def collect_economy(source: str = "all") -> dict:
    try:
        return (await EconomyAgent(repository).run(source)).model_dump(mode="json")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/health", status_code=202, dependencies=[Depends(require_collection_rate_limit)])
async def collect_health(source: str = "all") -> dict:
    try:
        return (await HealthAgent(repository).run(source)).model_dump(mode="json")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/energy", status_code=202, dependencies=[Depends(require_collection_rate_limit)])
async def collect_energy(source: str = "all") -> dict:
    try:
        return (await EnergyAgent(repository).run(source)).model_dump(mode="json")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/transport", status_code=202, dependencies=[Depends(require_collection_access)])
async def collect_transport(source: str = "all") -> dict:
    try:
        return (await TransportAgent(repository).run(source)).model_dump(mode="json")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/education", status_code=202, dependencies=[Depends(require_collection_access)])
async def collect_education(source: str = "all") -> dict:
    try:
        return (await EducationAgent(repository).run(source)).model_dump(mode="json")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/collection/scheduler-status")
def scheduler_status() -> dict:
    return scheduler_service.get_status()


@app.post("/api/v1/collection/run-scheduled-harvest", dependencies=[Depends(require_collection_access)])
async def trigger_harvest() -> dict:
    return await scheduler_service.run_harvest_job()


@app.post("/api/v1/studies", dependencies=[Depends(require_analysis_rate_limit)])
async def generate_study(sector: str | None = None) -> dict:
    try:
        result = await AnalysisAgent(repository).study(sector)
        return result.model_dump(mode="json")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/insights/cross-sector")
def cross_sector_insights() -> dict:
    """Analyse DS multi-secteurs : fraîcheur, corrélations, couverture spatiale, anomalies saisonnières.

    Toutes les métriques sont calculées en Python pur sur les observations déjà publiées.
    Aucun appel LLM — sûr à appeler à chaque chargement de page.
    """
    try:
        observations = repository.list_observations(sector=None, limit=2000)
        return {
            "freshness": compute_freshness_scores(observations),
            "correlations": compute_cross_sector_correlations(observations),
            "spatial_coverage": compute_spatial_coverage(observations),
            "seasonal_anomalies": compute_seasonal_anomalies(observations),
            "total_observations_analyzed": len(observations),
        }
    except Exception as exc:
        logger.warning("cross_sector_insights failed: %s", exc)
        return {
            "freshness": {},
            "correlations": [],
            "spatial_coverage": {},
            "seasonal_anomalies": [],
            "total_observations_analyzed": 0,
        }


# Mount static assets (css, js, images) to serve static directory
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=False), name="static")

