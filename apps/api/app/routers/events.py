import json
import uuid
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import SessionLocal, get_db
from app.models.event import Event
from app.schemas.auth import UserClaims
from app.schemas.event import EventRead
from app.services.events_pubsub import EVENTS_CHANNEL, event_to_payload

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventRead])
def list_events(
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db),
    _user: UserClaims = Depends(get_current_user),
) -> list[Event]:
    stmt = select(Event).order_by(Event.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())


async def _event_source(since: uuid.UUID | None) -> AsyncIterator[str]:
    # Replay unseen rows from Postgres first — pub/sub alone is fire-and-forget
    # and would silently drop events for a client that connects late or was
    # briefly disconnected; durability comes from the Event table, not redis.
    with SessionLocal() as db:
        stmt = select(Event).order_by(Event.created_at.asc())
        if since is not None:
            since_event = db.get(Event, since)
            if since_event is not None:
                stmt = stmt.where(Event.created_at > since_event.created_at)
        for event in db.scalars(stmt).all():
            yield f"data: {json.dumps(event_to_payload(event))}\n\n"

    client = aioredis.Redis.from_url(settings.redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe(EVENTS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message["data"]
            yield f"data: {data.decode() if isinstance(data, bytes) else data}\n\n"
    finally:
        await pubsub.unsubscribe(EVENTS_CHANNEL)
        await client.aclose()


@router.get("/stream")
async def stream_events(
    since: uuid.UUID | None = Query(default=None),
    _user: UserClaims = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(_event_source(since), media_type="text/event-stream")
