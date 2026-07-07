from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import analyses, aois, auth, detections, events, health, monitors, stac

app = FastAPI(title="VANTAGE API", version="0.1.0")

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
