"""Real regression coverage for pick_best_sar_scene's orbit-direction
preference (sar_change_detection_pipeline.py) -- comparing two Sentinel-1
scenes shot from different orbit directions (ascending/descending) shifts
backscatter from viewing geometry alone, not real ground change, which plain
amplitude log-ratio change detection has no way to correct for. This is the
one mitigation the pipeline applies (see its module docstring for the fuller
honest-scope statement), so it needs to actually work."""

from datetime import date

import pytest

from app.imagery.base import ImagerySource, SceneMetadata
from app.services.change_detection_pipeline import ChangeDetectionError
from app.services.sar_change_detection_pipeline import pick_best_sar_scene

_AOI_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[-121.5, 38.5], [-121.4, 38.5], [-121.4, 38.6], [-121.5, 38.6], [-121.5, 38.5]]],
}
# Comfortably covers _AOI_GEOMETRY above.
_COVERING_BBOX = (-122.0, 38.0, -121.0, 39.0)
_NON_COVERING_BBOX = (10.0, 10.0, 11.0, 11.0)


class FakeImagerySource(ImagerySource):
    def __init__(self, scenes: list[SceneMetadata]):
        self._scenes = scenes

    def search(self, geometry, date_from, date_to, collections, max_cloud_cover=None):
        return list(self._scenes)

    def get_asset_href(self, item_id, collection, asset_key):
        raise NotImplementedError


def _scene(id_: str, orbit_state: str | None, bbox=_COVERING_BBOX) -> SceneMetadata:
    return SceneMetadata(
        id=id_,
        collection="sentinel-1-grd",
        datetime="2026-01-01T00:00:00Z",
        cloud_cover=None,
        bbox=bbox,
        assets={"vv": f"https://example.com/{id_}/vv.tif"},
        orbit_state=orbit_state,
    )


def test_picks_the_only_covering_scene_when_no_preference_given():
    imagery = FakeImagerySource([_scene("a", "ascending")])

    scene = pick_best_sar_scene(imagery, _AOI_GEOMETRY, date(2026, 1, 1), "sentinel-1-grd")

    assert scene.id == "a"


def test_prefers_the_matching_orbit_state():
    imagery = FakeImagerySource(
        [_scene("descending-match", "descending"), _scene("ascending-mismatch", "ascending")]
    )

    scene = pick_best_sar_scene(
        imagery, _AOI_GEOMETRY, date(2026, 1, 1), "sentinel-1-grd", preferred_orbit_state="descending"
    )

    assert scene.id == "descending-match"


def test_falls_back_to_any_covering_scene_when_no_orbit_match_exists():
    imagery = FakeImagerySource([_scene("ascending-only", "ascending")])

    # Asked for "descending", but only an ascending scene covers the AOI on
    # this date -- must still return it rather than failing outright; the
    # caller (execute_sar_change_detection) is the one that records the
    # resulting mismatch honestly in AnalysisResult.stats.
    scene = pick_best_sar_scene(
        imagery, _AOI_GEOMETRY, date(2026, 1, 1), "sentinel-1-grd", preferred_orbit_state="descending"
    )

    assert scene.id == "ascending-only"


def test_non_covering_scenes_are_ignored():
    imagery = FakeImagerySource([_scene("off-aoi", "ascending", bbox=_NON_COVERING_BBOX)])

    with pytest.raises(ChangeDetectionError, match="none covering"):
        pick_best_sar_scene(imagery, _AOI_GEOMETRY, date(2026, 1, 1), "sentinel-1-grd")


def test_no_scenes_at_all_raises():
    imagery = FakeImagerySource([])

    with pytest.raises(ChangeDetectionError, match="none covering"):
        pick_best_sar_scene(imagery, _AOI_GEOMETRY, date(2026, 1, 1), "sentinel-1-grd")
