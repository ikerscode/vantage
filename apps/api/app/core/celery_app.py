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

# SEC-08: celery's default serializer is pickle, which deserializes
# arbitrary Python objects — anyone who can write to the broker (Redis) can
# get arbitrary code execution in the worker process. JSON-only closes that
# off entirely; every task here only ever passes a plain UUID string
# anyway, so this is a pure hardening change with no functional effect.
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
