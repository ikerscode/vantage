#!/usr/bin/env python3
"""Emits a minimal valid STAC 1.0 Item JSON per demo scene (BRIEF v1.3 §6),
from the manifest fetch_demo_data.py already wrote. Separate script (not
folded into the fetch, which needs network) so item.json can be
regenerated/edited without re-downloading imagery.

Asset hrefs are absolute paths under --mount-path (default /data/demo, the
container path docker-compose.prod.yml bind-mounts
${VANTAGE_DATA_DIR}/demo-data to — the launcher copies the bundled
infra/demo-data/ resource there on first run). rio-tiler's STACReader
(services/tiler's /stac route) opens this file via pystac, which reads
absolute local paths directly (no HTTP server needed) — same as it would
for a real https:// STAC item href, just local.

These hrefs are baked in at generation time, so this must be re-run whenever
the mount path changes — e.g. once with the real repo path for native
(non-container) verification in a sandbox with no Docker, and once with
/data/demo for what actually ships. Both runs were used to build this exact
bundle — see PACKAGE_REPORT.md.
"""

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "infra" / "demo-data" / "manifest.json"

ASSET_MEDIA_TYPES = {
    "visual": "image/tiff; application=geotiff; profile=cloud-optimized",
    "red": "image/tiff; application=geotiff; profile=cloud-optimized",
    "green": "image/tiff; application=geotiff; profile=cloud-optimized",
    "blue": "image/tiff; application=geotiff; profile=cloud-optimized",
    "nir": "image/tiff; application=geotiff; profile=cloud-optimized",
    "scl": "image/tiff; application=geotiff; profile=cloud-optimized",
}


def build_item(entry: dict, mount_path: str) -> dict:
    # Matches where this actually gets written below: alongside the scene's
    # assets, i.e. infra/demo-data/<date>/item.json — NOT keyed by scene id,
    # since manifest.json's asset paths are date-keyed.
    date_dir = Path(entry["assets"]["visual"]).parent.name
    self_href = f"{mount_path}/{date_dir}/item.json"
    assets = {
        key: {
            "href": f"{mount_path}/{rel_path}",
            "type": ASSET_MEDIA_TYPES.get(key, "image/tiff; application=geotiff"),
            "roles": ["data"],
        }
        for key, rel_path in entry["assets"].items()
    }
    minx, miny, maxx, maxy = entry["bbox"]
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": entry["id"],
        "collection": entry["collection"],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
        },
        "bbox": entry["bbox"],
        "properties": {
            "datetime": entry["datetime"],
            "eo:cloud_cover": entry["cloud_cover"],
        },
        "assets": assets,
        "links": [{"rel": "self", "href": self_href, "type": "application/json"}],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mount-path",
        default="/data/demo",
        help="Absolute path these assets will be readable at when the tiler/api open them "
        "(default: /data/demo, the packaged container mount point).",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text())
    for entry in manifest["items"]:
        item = build_item(entry, args.mount_path)
        date_dir = Path(entry["assets"]["visual"]).parent.name
        out_path = MANIFEST_PATH.parent / date_dir / "item.json"
        out_path.write_text(json.dumps(item, indent=2))
        print(f"wrote {out_path.relative_to(REPO_ROOT)} (mount_path={args.mount_path})")


if __name__ == "__main__":
    main()
