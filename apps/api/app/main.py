from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import analyses, aois, auth, detections, events, health, monitors, stac

# SEC-10: /docs, /redoc, /openapi.json expose the full API surface (routes,
# schemas, param names) to anyone who can reach this process — fine for
# development, not something a production deployment should serve by
# default. VANTAGE_ENV=production disables all three; dev keeps them.
_docs_kwargs = (
    {"docs_url": None, "redoc_url": None, "openapi_url": None}
    if settings.vantage_env == "production"
    else {}
)
app = FastAPI(title="VANTAGE API", version="0.1.0", **_docs_kwargs)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(aois.router, prefix=API_PREFIX)
app.include_router(stac.router, prefix=API_PREFIX)
app.include_router(analyses.router, prefix=API_PREFIX)
app.include_router(detections.router, prefix=API_PREFIX)
app.include_router(monitors.router, prefix=API_PREFIX)
app.include_router(events.router, prefix=API_PREFIX)
