import logging
from datetime import date, datetime, timedelta, timezone

from croniter import CroniterBadCronError, croniter

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.imagery.factory import get_imagery_source
from app.imagery.sensor import SensorType, default_change_threshold_for, sensor_for_collection
from app.models.aoi import AOI
from app.models.analysis_result import AnalysisResult, AnalysisStatus, DetectionStatus
from app.models.event import Event
from app.models.monitor import Monitor
from app.schemas.geo import wkb_to_geojson
from app.services.change_detection_pipeline import ChangeDetectionError, execute_change_detection
from app.services.detection_pipeline import run_placeholder_detection
from app.services.events_pubsub import publish_event

logger = logging.getLogger(__name__)

# How far back to look for a first-ever comparison scene when a monitor has
# neither a baseline_date nor a prior last_scene_date yet.
SEED_LOOKBACK_DAYS = 30


def _is_due(monitor: Monitor, now: datetime) -> bool:
    base = monitor.last_run_at or monitor.created_at
    return croniter(monitor.schedule, base).get_next(datetime) <= now


def _latest_scene_date(imagery, geometry: dict, since: date, today: date, collection: str) -> date | None:
    scenes = imagery.search(
        geometry=geometry,
        date_from=since,
        date_to=today,
        collections=[collection],
    )
    if not scenes:
        return None
    latest = max(scenes, key=lambda s: s.datetime)
    return datetime.fromisoformat(latest.datetime).date()


def _should_run_detection(monitor: Monitor, sensor: SensorType, changed_pixel_count: int) -> bool:
    """Whether app.services.detection_pipeline.run_placeholder_detection
    should run for this sweep result: only when a real change was found (not
    every sweep tick), the monitor has opted in (detect_on_change), and the
    AOI is optical (no honest SAR detector exists yet — see
    detection_pipeline.py's module docstring)."""
    return changed_pixel_count > 0 and monitor.detect_on_change and sensor is SensorType.OPTICAL


def _resolve_comparison_dates(
    monitor: Monitor, imagery, geometry: dict, today: date, collection: str
) -> tuple[date | None, date | None]:
    """Returns (date_a, latest_scene_date). date_a is None when there's nothing
    yet to compare the latest scene against (rolling comparison with no prior
    last_scene_date, and no fixed baseline_date configured) — the sweep still
    records latest_scene_date so the *next* sweep has a comparison point."""
    since = monitor.last_scene_date or (today - timedelta(days=SEED_LOOKBACK_DAYS))
    latest_date = _latest_scene_date(imagery, geometry, since, today, collection)
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
                monitor, imagery, geometry, now.date(), aoi.collection
            )
            monitor.last_run_at = now

            if date_a is None:
                # Either no new imagery, or nothing to compare against yet —
                # seed last_scene_date (if we found one) for next time.
                if latest_scene_date is not None:
                    monitor.last_scene_date = latest_scene_date
                session.commit()
                continue

            sensor = sensor_for_collection(aoi.collection)
            threshold = monitor.threshold or default_change_threshold_for(sensor)
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

            # BRIEF v2: a monitor that only ever reports "something changed"
            # forces an analyst to separately run Analyze/detections by hand
            # to see WHAT changed -- run object detection automatically, but
            # only when there's a real change to characterize (not every
            # sweep tick) and only for optical AOIs (see
            # detection_pipeline.run_placeholder_detection's docstring for
            # why SAR is excluded: no honest detector exists for it yet).
            if _should_run_detection(monitor, sensor, changed_pixel_count):
                try:
                    run_placeholder_detection(session, analysis)  # records OK + count itself
                except Exception as exc:
                    # Same honest-seams handling as the manual path (see
                    # app.tasks.change_detection): a best-effort detection
                    # failure doesn't fail the sweep, but it's recorded on the
                    # analysis rather than swallowed silently.
                    session.rollback()
                    analysis = session.get(AnalysisResult, analysis.id)
                    analysis.detection_status = DetectionStatus.FAILED.value
                    analysis.detection_error = str(exc)
                    session.commit()
                    logger.exception(
                        "auto-detection-on-change failed for analysis %s (monitor %s)",
                        analysis.id,
                        monitor.id,
                    )

            if changed_pixel_count > 0:
                metric_unit = "log-ratio dB" if sensor is SensorType.SAR else "NDVI-diff"
                event = Event(
                    monitor_id=monitor.id,
                    aoi_id=monitor.aoi_id,
                    analysis_result_id=analysis.id,
                    metric_value=(analysis.stats or {}).get("pct_changed", 0.0),
                    threshold=threshold,
                    summary=(
                        f"Change detected for AOI {monitor.aoi_id}: "
                        f"{changed_pixel_count} pixel(s) exceeded {metric_unit} threshold "
                        f"{threshold} between {date_a.isoformat()} and {latest_scene_date.isoformat()}."
                    ),
                )
                session.add(event)
                session.commit()
                publish_event(event)
