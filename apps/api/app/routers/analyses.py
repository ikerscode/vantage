import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.analysis_result import AnalysisResult, AnalysisStatus
from app.schemas.analysis_result import AnalysisCreate, AnalysisRead
from app.schemas.auth import UserClaims
from app.tasks.change_detection import run_change_detection

router = APIRouter(prefix="/analyses", tags=["analyses"])


def _tilejson_url(analysis: AnalysisResult) -> str | None:
    if analysis.status != AnalysisStatus.DONE.value or not analysis.s3_key:
        return None
    cog_url = f"s3://{settings.s3_bucket_analysis}/{analysis.s3_key}"
    return f"{settings.tiler_public_base_url}/cog/WebMercatorQuad/tilejson.json?url={cog_url}"


@router.post("", response_model=AnalysisRead, status_code=status.HTTP_201_CREATED)
def create_analysis(
    payload: AnalysisCreate,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> AnalysisRead:
    analysis = AnalysisResult(
        aoi_id=payload.aoi_id,
        date_a=payload.date_a,
        date_b=payload.date_b,
        threshold=payload.threshold or settings.change_detection_default_threshold,
        status=AnalysisStatus.PENDING.value,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    run_change_detection.delay(str(analysis.id))
    return AnalysisRead.from_model(analysis)


@router.get("", response_model=list[AnalysisRead])
def list_analyses(
    aoi_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> list[AnalysisRead]:
    stmt = select(AnalysisResult).order_by(AnalysisResult.created_at.desc())
    if aoi_id is not None:
        stmt = stmt.where(AnalysisResult.aoi_id == aoi_id)
    analyses = db.scalars(stmt).all()
    return [AnalysisRead.from_model(a, tilejson_url=_tilejson_url(a)) for a in analyses]


@router.get("/{analysis_id}", response_model=AnalysisRead)
def get_analysis(
    analysis_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> AnalysisRead:
    analysis = db.get(AnalysisResult, analysis_id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return AnalysisRead.from_model(analysis, tilejson_url=_tilejson_url(analysis))
