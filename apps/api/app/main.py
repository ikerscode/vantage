from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.limiter import limiter
from app.routers import analyses, aois, auth, detections, events, health, inference, monitors, stac

# SEC-10: /docs, /redoc, /openapi.json expose the full API surface (routes,
# schemas, param names) to anyone who can reach this process — fine for
# development, not something a production deployment should serve by
# default. VANTAGE_ENV=production disables all three; dev keeps them.
_docs_kwargs = (
    {"docs_url": None, "redoc_url": None, "openapi_url": None}
    if settings.vantage_env == "production"
    else {}
)
app = FastAPI(title="VANTAGE API", version="2.0.0", **_docs_kwargs)

# BRIEF v2 (SECURITY_FIXES_REPORT.md's one explicitly-flagged remaining
# gap): see app/core/limiter.py for what this does and doesn't buy in a
# single-workstation deployment. The exception handler is what turns a
# tripped limit into a real 429 response instead of an unhandled
# RateLimitExceeded propagating as a 500.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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
app.include_router(inference.router, prefix=API_PREFIX)
app.include_router(monitors.router, prefix=API_PREFIX)
app.include_router(events.router, prefix=API_PREFIX)
