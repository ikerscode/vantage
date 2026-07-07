import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rio_tiler.io import STACReader
from titiler.core.factory import MultiBaseTilerFactory, TilerFactory

app = FastAPI(title="VANTAGE Tiler")

_cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single-file COGs (Earth Search's "visual" true-color asset, and our own
# analysis-output COGs) — band-math expressions and multi-TMS tilejson come
# for free from TilerFactory, no custom endpoint code needed. Reads public
# Earth Search COGs via GDAL /vsicurl/ (plain HTTPS) and our own MinIO-hosted
# output COGs via /vsis3/ (AWS_* env vars below), same process.
cog = TilerFactory(router_prefix="/cog")
app.include_router(cog.router, prefix="/cog", tags=["Cloud Optimized GeoTIFF"])

# Multi-asset STAC items — Sentinel-2's red/nir/scl are *separate* COG files
# per item, so NDVI ((nir-red)/(nir+red)) needs a reader that spans multiple
# assets by name. STACReader takes a STAC item URL (Earth Search item hrefs
# are fetchable JSON) and ?assets=red&assets=nir&expression=(nir-red)/(nir+red)
# does the band math across files.
stac = MultiBaseTilerFactory(reader=STACReader, router_prefix="/stac")
app.include_router(stac.router, prefix="/stac", tags=["STAC item (multi-asset band math)"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
