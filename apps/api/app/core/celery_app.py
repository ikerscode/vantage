from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "vantage",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.change_detection", "app.tasks.monitor_sweep"],
)

celery_app.conf.beat_schedule = {
    "monitor-sweep": {
        "task": "app.tasks.monitor_sweep.sweep_monitors",
        "schedule": settings.monitor_sweep_interval_seconds,
    }
}
celery_app.conf.timezone = "UTC"
