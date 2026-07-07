#!/usr/bin/env python3
"""Fetches and crops real Sentinel-2 scenes into infra/demo-data/ for the
offline installer (BRIEF v1.3 §6). Run ONCE, by a maintainer, when
refreshing the bundled demo dataset — not run by end users or by the
launcher at first-run time. The output (small local COGs + a manifest +
per-scene STAC-item-shaped JSON) is what actually ships inside the
installer and is committed to the repo like any other asset.

Reuses the exact AOI and dates already proven (RUN_REPORT.md, scripts/smoke.sh)
to have real, useful NDVI contrast between two dates — no new location was
picked blind for this pass. Padded ~3x larger than the smoke-test AOI so the
demo has some room to pan/zoom around in, while staying small (~1500x1500px
per band at native 10m resolution).

Requires: apps/api's venv (rasterio, pystac_client, rio_cogeo — the same
libraries the real pipeline uses, so this crop is read the same way
_read_bands() in change_detection_pipeline.py reads a live scene).
"""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from pystac_client import Client
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "geo" / "src"))
from vantage_geo.transform import bounds_to_window  # noqa: E402

STAC_API_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"

# Same AOI center as scripts/smoke.sh's fixed test AOI
# ([-119.75,36.75,-119.70,36.80]), padded out for a nicer demo viewing area.
DEMO_BBOX_4326 = (-119.80, 36.70, -119.65, 36.85)
DEMO_AOI_GEOJSON = {
    "type": "Polygon",
    "coordinates": [
        [
            [DEMO_BBOX_4326[0], DEMO_BBOX_4326[1]],
            [DEMO_BBOX_4326[2], DEMO_BBOX_4326[1]],
            [DEMO_BBOX_4326[2], DEMO_BBOX_4326[3]],
            [DEMO_BBOX_4326[0], DEMO_BBOX_4326[3]],
            [DEMO_BBOX_4326[0], DEMO_BBOX_4326[1]],
        ]
    ],
}

# Same two dates already verified (RUN_REPORT.md) to both have low-cloud
# scenes and a real NDVI-diff signal between them.
DEMO_DATES = ["2025-06-19", "2025-11-01"]

ASSET_KEYS = ("visual", "red", "green", "blue", "nir", "scl")

OUT_DIR = REPO_ROOT / "infra" / "demo-data"


def write_cog(path: Path, array: np.ndarray, transform, crs, dtype: str) -> None:
    is_multiband = array.ndim == 3
    bands = array.shape[0] if is_multiband else 1
    height, width = array.shape[-2:]
    src_profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": bands,
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
    }
    dst_profile = cog_profiles.get("deflate")
    with MemoryFile() as src_mem:
        with src_mem.open(**src_profile) as src_dataset:
            if is_multiband:
                for b in range(bands):
                    src_dataset.write(array[b], b + 1)
            else:
                src_dataset.write(array, 1)
            path.parent.mkdir(parents=True, exist_ok=True)
            cog_translate(src_dataset, str(path), dst_profile, in_memory=False, quiet=True)


def fetch_one_scene(client: Client, target_date: str) -> dict:
    search = client.search(
        collections=[COLLECTION],
        intersects=DEMO_AOI_GEOJSON,
        datetime=f"{target_date}/{target_date}",
    )
    items = list(search.items())
    covering = [i for i in items if i.properties.get("eo:cloud_cover", 100) < 40]
    if not covering:
        raise RuntimeError(f"no usable scene found for {target_date} (found {len(items)} candidates)")
    item = min(covering, key=lambda i: i.properties.get("eo:cloud_cover", 100))
    print(f"  scene {item.id} cloud_cover={item.properties.get('eo:cloud_cover')}")

    scene_dir = OUT_DIR / target_date
    manifest_assets = {}
    ref_transform = None
    ref_crs = None
    ref_shape = None

    for asset_key in ASSET_KEYS:
        if asset_key not in item.assets:
            print(f"    skip {asset_key}: not present on this item")
            continue
        href = item.assets[asset_key].href
        with rasterio.open(href) as src:
            bounds_in_crs = transform_bounds("EPSG:4326", src.crs, *DEMO_BBOX_4326)
            window = bounds_to_window(src.transform, bounds_in_crs)
            if asset_key == "visual":
                data = src.read(window=window, boundless=True, fill_value=0)
                dtype = "uint8"
            else:
                data = src.read(1, window=window, boundless=True, fill_value=0)
                dtype = str(src.dtypes[0])
            window_transform = src.window_transform(window)
            crs = src.crs
        if asset_key == "red":
            ref_transform, ref_crs, ref_shape = window_transform, crs, data.shape

        out_path = scene_dir / f"{asset_key}.tif"
        write_cog(out_path, data, window_transform, crs, dtype)
        size_kb = out_path.stat().st_size / 1024
        print(f"    wrote {out_path.relative_to(REPO_ROOT)} ({size_kb:.0f} KB)")
        manifest_assets[asset_key] = str(out_path.relative_to(OUT_DIR))

    bbox_4326 = DEMO_BBOX_4326
    return {
        "id": item.id,
        "collection": COLLECTION,
        "datetime": item.properties["datetime"],
        "cloud_cover": item.properties.get("eo:cloud_cover"),
        "bbox": list(bbox_4326),
        "assets": manifest_assets,
    }


def main() -> None:
    client = Client.open(STAC_API_URL)
    manifest_items = []
    for d in DEMO_DATES:
        print(f"fetching demo scene for {d}...")
        manifest_items.append(fetch_one_scene(client, d))

    manifest = {
        "aoi_name": "Demo AOI — Central Valley, CA",
        "aoi_geometry": DEMO_AOI_GEOJSON,
        "collection": COLLECTION,
        "items": manifest_items,
    }
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nwrote {manifest_path.relative_to(REPO_ROOT)} with {len(manifest_items)} scene(s)")


if __name__ == "__main__":
    main()
