import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rio_tiler.io import STACReader
from titiler.core.factory import MultiBaseTilerFactory, TilerFactory

from app.security import require_tiler_token, validated_url

app = FastAPI(title="VANTAGE Tiler")

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
