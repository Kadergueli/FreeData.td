from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from app.agents import (
    AgricultureAgent,
    AnalysisAgent,
    EconomyAgent,
    EducationAgent,
    EnvironmentAgent,
    MarketsAgent,
    TransportAgent,
)
from app.config import settings
from app.services.export import observations_to_csv, observations_to_json
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

repository = ObservationRepository()
STATIC_DIR = Path(__file__).parent / "static"
DASHBOARD = STATIC_DIR / "index.html"


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
def observations(sector: str | None = None, limit: int = Query(default=200, ge=1, le=5000)) -> list[dict]:
    return repository.list_observations(sector=sector, limit=limit)


@app.get("/api/v1/catalog")
def catalog() -> list[dict]:
    return repository.catalog()


@app.get("/api/v1/pipeline/audit")
def pipeline_audit() -> dict:
    return repository.get_pipeline_audit()



@app.get("/api/v1/export/csv", response_class=PlainTextResponse)
def export_csv(sector: str | None = None) -> PlainTextResponse:
    rows = repository.list_observations(sector=sector, limit=5000)
    content = observations_to_csv(rows)
    filename = f"freedatatd-{sector or 'all'}-export.csv"
    return PlainTextResponse(
        content,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
        media_type="text/csv",
    )


@app.get("/api/v1/export/json")
def export_json(sector: str | None = None) -> JSONResponse:
    rows = repository.list_observations(sector=sector, limit=5000)
    filename = f"freedatatd-{sector or 'all'}-export.json"
    return JSONResponse(
        content=rows,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/v1/collection/agriculture", status_code=202)
async def collect_agriculture(source: str = "all") -> dict:
    try:
        return (await AgricultureAgent(repository).run(source)).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/environment", status_code=202)
async def collect_environment(source: str = "all") -> dict:
    try:
        return (await EnvironmentAgent(repository).run(source)).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/markets", status_code=202)
async def collect_markets(source: str = "all") -> dict:
    try:
        return (await MarketsAgent(repository).run(source)).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/economy", status_code=202)
async def collect_economy(source: str = "all") -> dict:
    try:
        return (await EconomyAgent(repository).run(source)).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/transport", status_code=202)
async def collect_transport(source: str = "all") -> dict:
    try:
        return (await TransportAgent(repository).run(source)).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/collection/education", status_code=202)
async def collect_education(source: str = "all") -> dict:
    try:
        return (await EducationAgent(repository).run(source)).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/collection/scheduler-status")
def scheduler_status() -> dict:
    return scheduler_service.get_status()


@app.post("/api/v1/collection/run-scheduled-harvest")
async def trigger_harvest() -> dict:
    return await scheduler_service.run_harvest_job()


@app.post("/api/v1/studies")
async def generate_study(sector: str | None = None) -> dict:
    try:
        return (await AnalysisAgent(repository).study(sector)).model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# Mount static assets (css, js, images) to serve static directory
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=False), name="static")

