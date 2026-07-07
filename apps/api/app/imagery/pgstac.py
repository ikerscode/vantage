from datetime import date

from app.imagery.base import ImagerySource, SceneMetadata


class PgstacSource(ImagerySource):
    """TODO(v2): pgstac-backed local/air-gapped catalog.

    Requires a STAC ingestion pipeline populating the `pgstac` schema that
    infra already provisions (see the `pgstac-migrate` service in
    infra/docker-compose.yml). Deliberately left unimplemented rather than
    faked: nothing imports `pypgstac` here, so repointing
    IMAGERY_SOURCE=pgstac before the ingestion pipeline exists fails loudly
    instead of silently returning nothing.
    """

    def search(
        self,
        geometry: dict,
        date_from: date,
        date_to: date,
        collections: list[str],
        max_cloud_cover: float | None = None,
    ) -> list[SceneMetadata]:
        raise NotImplementedError(
            "TODO(v2): pgstac-backed local/air-gapped imagery catalog is not implemented yet"
        )

    def get_asset_href(self, item_id: str, collection: str, asset_key: str) -> str:
        raise NotImplementedError(
            "TODO(v2): pgstac-backed local/air-gapped imagery catalog is not implemented yet"
        )
