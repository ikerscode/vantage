import json
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.imagery.base import ImagerySource, SceneMetadata


class StaticCatalogSource(ImagerySource):
    """BRIEF v1.3 §6: a small, fixed set of pre-fetched demo scenes bundled
    with the packaged desktop app, read from a local manifest.json +
    per-scene item.json (see scripts/package/fetch_demo_data.py and
    build_demo_stac_items.py). NOT the v2 pgstac-backed local/air-gapped
    catalog seam — that stays a deliberate NotImplementedError in
    pgstac.py. This is deliberately much narrower: one demo AOI, two
    hand-picked scenes, no ingestion pipeline, no spatial index, no general
    catalog browsing. IMAGERY_SOURCE=static_catalog.
    """

    def __init__(self, manifest_path: str | None = None):
        path = Path(manifest_path or settings.static_catalog_manifest_path)
        self._manifest = json.loads(path.read_text())
        self._mount_path = settings.static_catalog_mount_path

    def search(
        self,
        geometry: dict,
        date_from: date,
        date_to: date,
        collections: list[str],
        max_cloud_cover: float | None = None,
    ) -> list[SceneMetadata]:
        # No spatial intersection test: this catalog only ever has scenes
        # for the one bundled demo AOI, so date + collection is the whole
        # filter — see manifest.json's aoi_geometry for what that AOI is.
        results = []
        for entry in self._manifest["items"]:
            item_date = date.fromisoformat(entry["datetime"][:10])
            if not (date_from <= item_date <= date_to):
                continue
            if collections and entry["collection"] not in collections:
                continue
            if max_cloud_cover is not None and (entry.get("cloud_cover") or 0) > max_cloud_cover:
                continue
            results.append(self._to_scene_metadata(entry))
        return results

    def get_asset_href(self, item_id: str, collection: str, asset_key: str) -> str:
        entry = self._find_entry(item_id, collection)
        if asset_key not in entry["assets"]:
            raise ValueError(f"asset {asset_key!r} not found on item {item_id!r}")
        return self._asset_path(entry, asset_key)

    def all_scenes(self) -> list[SceneMetadata]:
        """Every bundled demo scene, unfiltered — used by the demo-data
        seeder (app/scripts/seed_demo_data.py), which needs the full set
        rather than a date-windowed search()."""
        return [self._to_scene_metadata(entry) for entry in self._manifest["items"]]

    @property
    def aoi_geometry(self) -> dict:
        return self._manifest["aoi_geometry"]

    def _find_entry(self, item_id: str, collection: str) -> dict:
        for entry in self._manifest["items"]:
            if entry["id"] == item_id and entry["collection"] == collection:
                return entry
        raise ValueError(f"item {item_id!r} not found in collection {collection!r}")

    def _asset_path(self, entry: dict, asset_key: str) -> str:
        # file:// (not a bare path): the tiler's SSRF-hardening allowlist
        # (services/tiler/app/security.py's validated_url) requires a real
        # URL scheme on anything passed as its `url` query param — found
        # for real in CI (BRIEF v1.6), a bare path was rejected with
        # "unsupported URL scheme: ''" and nobody had ever actually
        # rendered a static_catalog tile through the tiler before that
        # brief's acceptance test. The tiler's own file:// handling is
        # scoped to exactly this mount path, mirroring how s3:// is scoped
        # to the app's own bucket. (item.json's own *internal* asset hrefs,
        # read directly by rio-tiler's STACReader rather than passed
        # through validated_url, stay bare paths — see
        # scripts/package/build_demo_stac_items.py — no change needed
        # there.)
        return f"file://{self._mount_path}/{entry['assets'][asset_key]}"

    def _to_scene_metadata(self, entry: dict) -> SceneMetadata:
        date_dir = Path(entry["assets"]["visual"]).parent.as_posix()
        return SceneMetadata(
            id=entry["id"],
            collection=entry["collection"],
            datetime=entry["datetime"],
            cloud_cover=entry.get("cloud_cover"),
            bbox=tuple(entry["bbox"]),
            assets={key: self._asset_path(entry, key) for key in entry["assets"]},
            self_href=f"file://{self._mount_path}/{date_dir}/item.json",
        )
