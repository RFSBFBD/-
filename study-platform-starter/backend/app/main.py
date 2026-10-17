from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, validate_settings
from app.errors import register_exception_handlers
from app.health import health_payload, readiness_payload
from app.logging_config import configure_logging
from app.middleware import RequestContextMiddleware
from app.routers import (
    admin,
    artifacts,
    materials,
    me,
    rag,
    storage,
    study_sessions,
    subjects,
    transcription,
)

# Fail fast for the active environment. Development mode permits intentionally
# unconfigured integrations so that health endpoints remain reachable.
validate_settings(settings)

configure_logging(settings.log_level)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API for the AI Study Platform. Business endpoints are added phase by phase.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

app.add_middleware(RequestContextMiddleware)

register_exception_handlers(app)

app.include_router(me.router)
app.include_router(admin.router)
app.include_router(subjects.router)
app.include_router(study_sessions.router)
app.include_router(materials.router)
app.include_router(storage.router)
app.include_router(rag.router)
app.include_router(transcription.router)
app.include_router(artifacts.router)


@app.get("/health", tags=["system"])
async def health():
    return health_payload(settings)


@app.get("/ready", tags=["system"])
async def ready():
    return readiness_payload(settings)
