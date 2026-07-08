"""Real regression coverage for StaticCatalogSource's href format — found
broken for real in CI (BRIEF v1.6): asset/self hrefs were bare filesystem
paths with no URL scheme, which the tiler's SSRF-hardening allowlist
(services/tiler/app/security.py) has always rejected outright
("unsupported URL scheme: ''"). Nobody had ever actually rendered a
static_catalog tile through the tiler before that brief's clean-machine
acceptance test — this makes the fix (file:// prefixed hrefs) a real,
repeatable test instead of something only an end-to-end run would catch."""

import json
from datetime import date

import pytest

from app.imagery.static_catalog import StaticCatalogSource

_MANIFEST = {
    "aoi_name": "Demo AOI",
    "aoi_geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
    "collection": "sentinel-2-l2a",
    "items": [
        {
            "id": "S2B_TEST_20250619_0_L2A",
            "collection": "sentinel-2-l2a",
            "datetime": "2025-06-19T18:54:20.509000Z",
            "cloud_cover": 0.0,
            "bbox": [0, 0, 1, 1],
            "assets": {
                "visual": "2025-06-19/visual.tif",
                "red": "2025-06-19/red.tif",
                "nir": "2025-06-19/nir.tif",
            },
        },
    ],
}


@pytest.fixture
def source(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_MANIFEST))
    return StaticCatalogSource(manifest_path=str(manifest_path))


def test_search_results_have_file_scheme_asset_hrefs(source):
    scenes = source.search(
        geometry={}, date_from=date(2025, 6, 1), date_to=date(2025, 6, 30), collections=["sentinel-2-l2a"]
    )
    assert len(scenes) == 1
    assert scenes[0].assets["visual"] == "file:///data/demo/2025-06-19/visual.tif"


def test_search_results_have_a_file_scheme_self_href(source):
    scenes = source.search(
        geometry={}, date_from=date(2025, 6, 1), date_to=date(2025, 6, 30), collections=["sentinel-2-l2a"]
    )
    assert scenes[0].self_href == "file:///data/demo/2025-06-19/item.json"


def test_get_asset_href_has_the_file_scheme(source):
    href = source.get_asset_href("S2B_TEST_20250619_0_L2A", "sentinel-2-l2a", "visual")
    assert href == "file:///data/demo/2025-06-19/visual.tif"


def test_get_asset_href_respects_a_configured_mount_path(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_MANIFEST))
    source = StaticCatalogSource(manifest_path=str(manifest_path))
    source._mount_path = "/custom/mount"
    href = source.get_asset_href("S2B_TEST_20250619_0_L2A", "sentinel-2-l2a", "red")
    assert href == "file:///custom/mount/2025-06-19/red.tif"
