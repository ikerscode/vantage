from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.imagery.factory import get_imagery_source
from app.models.aoi import AOI
from app.schemas.auth import UserClaims
from app.schemas.geo import wkb_to_geojson
from app.schemas.stac import AssetRef, StacItemSummary, StacSearchRequest

router = APIRouter(prefix="/stac", tags=["stac"])


@router.post("/search", response_model=list[StacItemSummary])
# Online mode (IMAGERY_SOURCE=earth_search) forwards this to a public,
# shared third-party API — this cap protects that goodwill, not just this
# process (SECURITY_FIXES_REPORT.md's rate-limiting gap).
@limiter.limit("30/minute")
def search_stac(
    request: Request,
    payload: StacSearchRequest,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> list[StacItemSummary]:
    if payload.geometry is not None:
        geometry = payload.geometry
    else:
        aoi = db.get(AOI, payload.aoi_id)
        if aoi is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="AOI not found")
        geometry = wkb_to_geojson(aoi.geom)

    scenes = get_imagery_source().search(
        geometry=geometry,
        date_from=payload.date_from,
        date_to=payload.date_to,
        collections=payload.collections,
        max_cloud_cover=payload.max_cloud_cover,
    )
    return [
        StacItemSummary(
            id=s.id,
            collection=s.collection,
            datetime=s.datetime,
            cloud_cover=s.cloud_cover,
            bbox=list(s.bbox),
            assets={key: AssetRef(href=href) for key, href in s.assets.items()},
            self_href=s.self_href,
        )
        for s in scenes
    ]
