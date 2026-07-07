import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.detection import Detection
from app.schemas.auth import UserClaims
from app.schemas.detection import DetectionRead

router = APIRouter(prefix="/detections", tags=["detections"])


@router.get("", response_model=list[DetectionRead])
def list_detections(
    analysis_id: uuid.UUID = Query(),
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> list[DetectionRead]:
    stmt = select(Detection).where(Detection.analysis_result_id == analysis_id)
    detections = db.scalars(stmt).all()
    return [DetectionRead.from_model(d) for d in detections]
