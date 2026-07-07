from functools import lru_cache

from app.core.config import settings
from app.imagery.base import ImagerySource
from app.imagery.earth_search import EarthSearchSource
from app.imagery.pgstac import PgstacSource


@lru_cache
def _build_source() -> ImagerySource:
    if settings.imagery_source == "earth_search":
        return EarthSearchSource()
    if settings.imagery_source == "pgstac":
        return PgstacSource()
    raise ValueError(f"unknown IMAGERY_SOURCE: {settings.imagery_source!r}")


def get_imagery_source() -> ImagerySource:
    return _build_source()
