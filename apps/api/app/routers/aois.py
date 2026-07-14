import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.aoi import AOI
from app.schemas.aoi import AOICreate, AOIRead, AOIUpdate
from app.schemas.auth import UserClaims
from app.schemas.geo import geojson_to_wkb

router = APIRouter(prefix="/aois", tags=["aois"])


@router.post("", response_model=AOIRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_aoi(
    request: Request,
    payload: AOICreate,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> AOIRead:
    aoi = AOI(
        name=payload.name,
        description=payload.description,
        geom=geojson_to_wkb(payload.geometry),
        collection=payload.collection,
    )
    db.add(aoi)
    db.commit()
    db.refresh(aoi)
    return AOIRead.from_model(aoi)


@router.get("", response_model=list[AOIRead])
def list_aois(
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> list[AOIRead]:
    aois = db.scalars(
        select(AOI).where(AOI.archived_at.is_(None)).order_by(AOI.created_at.desc())
    ).all()
    return [AOIRead.from_model(a) for a in aois]


@router.get("/{aoi_id}", response_model=AOIRead)
def get_aoi(
    aoi_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> AOIRead:
    aoi = db.get(AOI, aoi_id)
    if aoi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="AOI not found")
    return AOIRead.from_model(aoi)


@router.patch("/{aoi_id}", response_model=AOIRead)
def update_aoi(
    aoi_id: uuid.UUID,
    payload: AOIUpdate,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> AOIRead:
    aoi = db.get(AOI, aoi_id)
    if aoi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="AOI not found")
    if payload.name is not None:
        aoi.name = payload.name
    if payload.description is not None:
        aoi.description = payload.description
    if payload.geometry is not None:
        aoi.geom = geojson_to_wkb(payload.geometry)
    db.commit()
    db.refresh(aoi)
    return AOIRead.from_model(aoi)


@router.delete("/{aoi_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_aoi(
    aoi_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> None:
    """Soft-delete: hard-deleting would orphan AnalysisResult/Event history."""
    aoi = db.get(AOI, aoi_id)
    if aoi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="AOI not found")
    aoi.archived_at = datetime.now(timezone.utc)
    db.commit()
