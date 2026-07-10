import logging
from datetime import date, datetime, timedelta, timezone

from croniter import CroniterBadCronError, croniter

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.imagery.factory import get_imagery_source
from app.models.aoi import AOI
from app.models.analysis_result import AnalysisResult, AnalysisStatus
from app.models.event import Event
from app.models.monitor import Monitor
from app.schemas.geo import wkb_to_geojson
from app.services.change_detection_pipeline import ChangeDetectionError, execute_change_detection
from app.services.events_pubsub import publish_event

logger = logging.getLogger(__name__)

# How far back to look for a first-ever comparison scene when a monitor has
# neither a baseline_date nor a prior last_scene_date yet.
SEED_LOOKBACK_DAYS = 30


def _is_due(monitor: Monitor, now: datetime) -> bool:
    base = monitor.last_run_at or monitor.created_at
    return croniter(monitor.schedule, base).get_next(datetime) <= now


def _latest_scene_date(imagery, geometry: dict, since: date, today: date) -> date | None:
    scenes = imagery.search(
        geometry=geometry,
        date_from=since,
        date_to=today,
        collections=[settings.stac_default_collection],
    )
    if not scenes:
        return None
    latest = max(scenes, key=lambda s: s.datetime)
    return datetime.fromisoformat(latest.datetime).date()


def _resolve_comparison_dates(
    monitor: Monitor, imagery, geometry: dict, today: date
) -> tuple[date | None, date | None]:
    """Returns (date_a, latest_scene_date). date_a is None when there's nothing
    yet to compare the latest scene against (rolling comparison with no prior
    last_scene_date, and no fixed baseline_date configured) — the sweep still
    records latest_scene_date so the *next* sweep has a comparison point."""
    since = monitor.last_scene_date or (today - timedelta(days=SEED_LOOKBACK_DAYS))
    latest_date = _latest_scene_date(imagery, geometry, since, today)
    if latest_date is None:
        return None, None

    date_a = monitor.baseline_date or monitor.last_scene_date
    if date_a is None or date_a == latest_date:
        return None, latest_date
    return date_a, latest_date


@celery_app.task(name="app.tasks.monitor_sweep.sweep_monitors")
def sweep_monitors() -> None:
    now = datetime.now(timezone.utc)
    imagery = get_imagery_source()

    with SessionLocal() as session:
        monitors = session.query(Monitor).filter(Monitor.active.is_(True)).all()

        for monitor in monitors:
            try:
                due = _is_due(monitor, now)
            except CroniterBadCronError:
                # BRIEF v2, found for real: this used to raise unhandled
                # here, crashing the sweep for every OTHER monitor too, not
                # just this one -- the API now validates cron expressions
                # at creation time (app/schemas/monitor.py), so this is a
                # defensive backstop for any row that predates that
                # validation, not the primary defense.
                logger.error(
                    "monitor %s has an invalid cron schedule %r -- skipping, not failing the whole sweep",
                    monitor.id,
                    monitor.schedule,
                )
                continue
            if not due:
                continue

            aoi = session.get(AOI, monitor.aoi_id)
            if aoi is None:
                continue
            geometry = wkb_to_geojson(aoi.geom)

            date_a, latest_scene_date = _resolve_comparison_dates(
                monitor, imagery, geometry, now.date()
            )
            monitor.last_run_at = now

            if date_a is None:
                # Either no new imagery, or nothing to compare against yet —
                # seed last_scene_date (if we found one) for next time.
                if latest_scene_date is not None:
                    monitor.last_scene_date = latest_scene_date
                session.commit()
                continue

            threshold = monitor.threshold or settings.change_detection_default_threshold
            analysis = AnalysisResult(
                aoi_id=monitor.aoi_id,
                monitor_id=monitor.id,
                date_a=date_a,
                date_b=latest_scene_date,
                threshold=threshold,
                status=AnalysisStatus.PENDING.value,
            )
            session.add(analysis)
            session.commit()

            try:
                execute_change_detection(session, analysis)
            except ChangeDetectionError as exc:
                analysis.status = AnalysisStatus.FAILED.value
                analysis.error_message = str(exc)
                session.commit()
                continue

            monitor.last_scene_date = latest_scene_date
            session.commit()

            changed_pixel_count = (analysis.stats or {}).get("changed_pixel_count", 0)
            if changed_pixel_count > 0:
                event = Event(
                    monitor_id=monitor.id,
                    aoi_id=monitor.aoi_id,
                    analysis_result_id=analysis.id,
                    metric_value=(analysis.stats or {}).get("pct_changed", 0.0),
                    threshold=threshold,
                    summary=(
                        f"Change detected for AOI {monitor.aoi_id}: "
                        f"{changed_pixel_count} pixel(s) exceeded NDVI-diff threshold "
                        f"{threshold} between {date_a.isoformat()} and {latest_scene_date.isoformat()}."
                    ),
                )
                session.add(event)
                session.commit()
                publish_event(event)
