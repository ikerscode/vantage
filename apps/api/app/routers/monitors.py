import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.monitor import Monitor
from app.schemas.auth import UserClaims
from app.schemas.monitor import MonitorCreate, MonitorRead, MonitorUpdate

router = APIRouter(prefix="/monitors", tags=["monitors"])


@router.post("", response_model=MonitorRead, status_code=status.HTTP_201_CREATED)
def create_monitor(
    payload: MonitorCreate,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> Monitor:
    monitor = Monitor(**payload.model_dump())
    db.add(monitor)
    db.commit()
    db.refresh(monitor)
    return monitor


@router.get("", response_model=list[MonitorRead])
def list_monitors(
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> list[Monitor]:
    return list(db.scalars(select(Monitor).order_by(Monitor.created_at.desc())).all())


@router.get("/{monitor_id}", response_model=MonitorRead)
def get_monitor(
    monitor_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> Monitor:
    monitor = db.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return monitor


@router.patch("/{monitor_id}", response_model=MonitorRead)
def update_monitor(
    monitor_id: uuid.UUID,
    payload: MonitorUpdate,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> Monitor:
    monitor = db.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(monitor, field, value)
    db.commit()
    db.refresh(monitor)
    return monitor


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_monitor(
    monitor_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> None:
    """Deactivates rather than deletes: Event rows FK-cascade off Monitor, so a
    hard delete would silently destroy alert history."""
    monitor = db.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    monitor.active = False
    db.commit()
