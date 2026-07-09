"""BRIEF v1.8 Phase 1: build a chip+bbox training set for Sentinel-2 vessel
detection from the Zenodo 15019034 (CC BY 4.0) annotation geopackages.

Real imagery is fetched from Earth Search v1 (the same public STAC catalog
apps/api already uses at inference time) rather than requiring a Copernicus
Data Space Ecosystem account -- both serve the same underlying ESA Sentinel-2
L2A archive, so this keeps the whole pipeline account-free and consistent
with VANTAGE's existing imagery adapter.

One tile (34VER) is held out ENTIRELY -- none of its chips are used for
training -- so Phase 2 evaluation is on genuinely unseen scenes, not just
unseen crops of scenes the model already saw.
"""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyogrio
import rasterio
from pystac_client import Client
from rasterio.windows import Window, from_bounds
from shapely.geometry import box as shapely_box

DATA_DIR = Path(__file__).parent / "data"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
CHIPS_DIR = DATA_DIR / "chips"
CHIP_SIZE = 512
MARGIN_M = 1024  # expand each scene's annotation envelope by this many meters
HELD_OUT_TILE = "34VER"

STAC_API_URL = "https://earth-search.aws.element84.com/v1"
TILES = ["34VEM", "35VLG", "34VEN", "34WFT", "34VER"]


def find_scene(client: Client, tile: str, date: str) -> dict | None:
    """Look up the Earth Search sentinel-2-l2a item for this tile+date."""
    gdf = gpd.read_file(ANNOTATIONS_DIR / f"{tile}.gpkg", layer=date)
    centroid = gdf.geometry.unary_union.centroid
    centroid_wgs84 = (
        gpd.GeoSeries([centroid], crs=gdf.crs).to_crs("EPSG:4326").iloc[0]
    )
    search = client.search(
        collections=["sentinel-2-l2a"],
        datetime=f"{date[:4]}-{date[4:6]}-{date[6:]}/{date[:4]}-{date[4:6]}-{date[6:]}",
        intersects={"type": "Point", "coordinates": [centroid_wgs84.x, centroid_wgs84.y]},
    )
    for item in search.items():
        if item.properties.get("grid:code") == f"MGRS-{tile}":
            return item
    return None


def process_scene(tile: str, date: str, item, gdf: gpd.GeoDataFrame) -> list[dict]:
    """Fetch the windowed region covering this scene's annotations, tile it
    into fixed-size chips, and save each chip + its box list. Returns a list
    of chip metadata dicts."""
    visual_href = item.assets["visual"].href
    records = []

    with rasterio.open(f"/vsicurl/{visual_href}") as src:
        assert gdf.crs.to_epsg() == src.crs.to_epsg(), (
            f"CRS mismatch for {tile}/{date}: annotations={gdf.crs} raster={src.crs}"
        )
        minx, miny, maxx, maxy = gdf.total_bounds
        minx, miny, maxx, maxy = (
            minx - MARGIN_M,
            miny - MARGIN_M,
            maxx + MARGIN_M,
            maxy + MARGIN_M,
        )
        window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
        window = window.round_lengths().round_offsets()
        # clip to raster bounds
        window = window.intersection(Window(0, 0, src.width, src.height))
        region = src.read([1, 2, 3], window=window)  # RGB from the visual COG
        region_transform = src.window_transform(window)

    n_bands, height, width = region.shape
    n_chips_x = width // CHIP_SIZE
    n_chips_y = height // CHIP_SIZE

    out_dir = CHIPS_DIR / tile / date
    out_dir.mkdir(parents=True, exist_ok=True)

    for cy in range(n_chips_y):
        for cx in range(n_chips_x):
            y0, x0 = cy * CHIP_SIZE, cx * CHIP_SIZE
            chip_arr = region[:, y0 : y0 + CHIP_SIZE, x0 : x0 + CHIP_SIZE]
            if chip_arr.max() == 0:
                continue  # nodata-only chip (outside actual scene extent)

            # chip's geographic bounds, to find which boats fall inside it
            chip_transform = rasterio.Affine(
                region_transform.a,
                region_transform.b,
                region_transform.c + x0 * region_transform.a,
                region_transform.d,
                region_transform.e,
                region_transform.f + y0 * region_transform.e,
            )
            chip_minx, chip_maxy = chip_transform.c, chip_transform.f
            chip_maxx = chip_minx + CHIP_SIZE * chip_transform.a
            chip_miny = chip_maxy + CHIP_SIZE * chip_transform.e
            chip_geom = shapely_box(chip_minx, chip_miny, chip_maxx, chip_maxy)

            boxes = []
            for geom in gdf.geometry:
                if not geom.intersects(chip_geom):
                    continue
                gminx, gminy, gmaxx, gmaxy = geom.bounds
                # geo bounds -> pixel bounds within this chip (row 0 at top)
                px0 = (gminx - chip_minx) / chip_transform.a
                px1 = (gmaxx - chip_minx) / chip_transform.a
                py0 = (chip_maxy - gmaxy) / (-chip_transform.e)
                py1 = (chip_maxy - gminy) / (-chip_transform.e)
                px0, px1 = max(0, px0), min(CHIP_SIZE, px1)
                py0, py1 = max(0, py0), min(CHIP_SIZE, py1)
                if px1 - px0 < 1 or py1 - py0 < 1:
                    continue  # sliver from a box barely clipping the chip edge
                boxes.append([px0, py0, px1, py1])

            chip_id = f"{tile}_{date}_{cy}_{cx}"
            img_path = out_dir / f"{chip_id}.npy"
            np.save(img_path, chip_arr)
            records.append(
                {
                    "chip_id": chip_id,
                    "tile": tile,
                    "date": date,
                    "path": str(img_path.relative_to(DATA_DIR)),
                    "boxes": boxes,
                    "held_out": tile == HELD_OUT_TILE,
                }
            )
    return records


def main():
    client = Client.open(STAC_API_URL)
    all_records = []

    for tile in TILES:
        gpkg_path = ANNOTATIONS_DIR / f"{tile}.gpkg"
        for layer_name, _geom_type in pyogrio.list_layers(gpkg_path):
            date = layer_name
            gdf = gpd.read_file(gpkg_path, layer=date)
            print(f"=== {tile} {date}: {len(gdf)} annotated boats ===")
            item = find_scene(client, tile, date)
            if item is None:
                print(f"  !! no matching Earth Search scene found, skipping")
                continue
            print(f"  matched scene: {item.id} (cloud cover {item.properties.get('eo:cloud_cover')}%)")
            records = process_scene(tile, date, item, gdf)
            n_pos = sum(1 for r in records if r["boxes"])
            print(f"  -> {len(records)} chips ({n_pos} with boxes, {len(records) - n_pos} background)")
            all_records.append((tile, date, records))

    manifest = []
    for tile, date, records in all_records:
        manifest.extend(records)

    with open(DATA_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f)

    n_train = sum(1 for r in manifest if not r["held_out"])
    n_held_out = sum(1 for r in manifest if r["held_out"])
    n_train_boxes = sum(len(r["boxes"]) for r in manifest if not r["held_out"])
    n_held_out_boxes = sum(len(r["boxes"]) for r in manifest if r["held_out"])
    print(f"\n=== TOTAL: {len(manifest)} chips ===")
    print(f"train (tiles != {HELD_OUT_TILE}): {n_train} chips, {n_train_boxes} boxes")
    print(f"held-out ({HELD_OUT_TILE}): {n_held_out} chips, {n_held_out_boxes} boxes")


if __name__ == "__main__":
    main()
