import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rio_tiler.io import STACReader
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.core.factory import MultiBaseTilerFactory, TilerFactory
from titiler.core.middleware import CacheControlMiddleware

from app.security import require_tiler_token, validated_url

app = FastAPI(title="VANTAGE Tiler")

# Found live, running a real analysis end-to-end: a small AOI's analysis COG
# only covers a small extent, so MapLibre's tile grid at the current viewport
# routinely requests tiles OUTSIDE that extent (or a source COG's real bounds
# generally). rio-tiler raises TileOutsideBounds for those, which — with no
# handler registered — propagated as an unhandled 500. FastAPI's default
# error path for an uncaught exception doesn't go back through
# CORSMiddleware's header injection, so the browser reported it as a CORS
# failure instead, masking the real cause and leaving the whole Change/NDVI/
# True Color raster looking silently broken. titiler ships exactly the
# mapping this needs (TileOutsideBounds -> a clean 404, still CORS-safe) —
# it's opt-in, and this app never opted in.
add_exception_handlers(app, DEFAULT_STATUS_CODES)

# PERF: found for real — tile/tilejson responses carried no Cache-Control at
# all, so panning back over an already-seen area re-fetched and re-rendered
# every tile from scratch instead of the browser serving it from its own
# cache. Every tile/tilejson response here is genuinely immutable for its
# exact URL: the `url` query param pins an exact dated STAC asset or an exact
# completed analysis's S3 key, and neither ever changes in place — so a long
# max-age is safe, not just fast. /health is excluded on principle (a health
# check should always hit the process live, not a cache).
app.add_middleware(
    CacheControlMiddleware,
    cachecontrol=os.environ.get("TILER_CACHE_CONTROL", "public, max-age=86400"),
    exclude_path={r"/health"},
)

# SEC-01: default-deny, not default-allow. Earlier versions of this file
# fell back to "*" when CORS_ALLOWED_ORIGINS was unset — meaning ANY origin
# could read tiles cross-origin by default. No default now: an empty
# allowlist means no cross-origin access at all (the app's own webview
# origin still works, since same-origin/no-Origin-header requests are never
# subject to CORS in the first place).
_cors_origins = [
    origin.strip() for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# SEC-01: every tile/info/tilejson request must pass BOTH the shared-token
# check and the SSRF-safe URL validator — see app/security.py's module
# docstring for why each is necessary on its own.
_protected = [Depends(require_tiler_token)]

# Single-file COGs (Earth Search's "visual" true-color asset, and our own
# analysis-output COGs) — band-math expressions and multi-TMS tilejson come
# for free from TilerFactory, no custom endpoint code needed. Reads public
# Earth Search COGs via GDAL /vsicurl/ (plain HTTPS) and our own MinIO-hosted
# output COGs via /vsis3/ (AWS_* env vars below), same process.
cog = TilerFactory(router_prefix="/cog", path_dependency=validated_url)
app.include_router(cog.router, prefix="/cog", tags=["Cloud Optimized GeoTIFF"], dependencies=_protected)

# Multi-asset STAC items — Sentinel-2's red/nir/scl are *separate* COG files
# per item, so NDVI ((nir-red)/(nir+red)) needs a reader that spans multiple
# assets by name. STACReader takes a STAC item URL (Earth Search item hrefs
# are fetchable JSON) and ?assets=red&assets=nir&expression=(nir-red)/(nir+red)
# does the band math across files.
stac = MultiBaseTilerFactory(reader=STACReader, router_prefix="/stac", path_dependency=validated_url)
app.include_router(
    stac.router, prefix="/stac", tags=["STAC item (multi-asset band math)"], dependencies=_protected
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
