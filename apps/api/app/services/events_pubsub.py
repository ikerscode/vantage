import json
from functools import lru_cache

import redis

from app.core.config import settings
from app.models.event import Event

EVENTS_CHANNEL = "vantage:events"


@lru_cache
def _get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url)


def event_to_payload(event: Event) -> dict:
    return {
        "id": str(event.id),
        "monitor_id": str(event.monitor_id),
        "aoi_id": str(event.aoi_id),
        "analysis_result_id": str(event.analysis_result_id),
        "metric_value": event.metric_value,
        "threshold": event.threshold,
        "summary": event.summary,
        "created_at": event.created_at.isoformat(),
    }


def publish_event(event: Event) -> None:
    """Fire-and-forget publish to the live SSE channel. Durability for clients
    that connect late (or are briefly disconnected) comes from the Event table
    itself, replayed by GET /api/events/stream on connect — not from this
    pub/sub message, which any not-currently-subscribed client will simply miss."""
    _get_redis_client().publish(EVENTS_CHANNEL, json.dumps(event_to_payload(event)))
