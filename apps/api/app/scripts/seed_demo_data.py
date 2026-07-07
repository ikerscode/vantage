"""One-shot idempotent seeder for the offline demo dataset (BRIEF v1.3 §6):
inserts the demo AOI, a demo Monitor watching it, and pre-computes one real
AnalysisResult + Event so Explore/Analyze/Monitor are all populated the
moment the app opens — no waiting on a sweep, no network required.

Run via `python -m app.scripts.seed_demo_data` as a one-shot compose
service using the vantage-api image (see infra/docker-compose.prod.yml's
`demo-seed` service) — same image, same dependencies, no separate install.

Idempotent by construction: looks for an AOI with DEMO_AOI_NAME before
doing anything else, and does nothing if one already exists. Safe to run on
every `compose up`, including on machines where IMAGERY_SOURCE isn't even
"static_catalog" (in which case this is a no-op past the imagery_source
check below — seeding demo data into a live-imagery deployment would be
actively wrong, not just redundant).
"""

import logging
import sys
from datetime import date

from app.core.config import settings
from app.db.session import SessionLocal
from app.imagery.static_catalog import StaticCatalogSource
from app.models.aoi import AOI
from app.models.analysis_result import AnalysisResult, AnalysisStatus
from app.models.event import Event
from app.models.monitor import Monitor
from app.schemas.geo import geojson_to_wkb
from app.services.change_detection_pipeline import ChangeDetectionError, execute_change_detection

logger = logging.getLogger(__name__)

DEMO_AOI_NAME = "Demo — Central Valley, CA"
DEMO_MONITOR_SCHEDULE = "0 */6 * * *"  # every 6 hours; irrelevant for the seeded run itself


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if settings.imagery_source != "static_catalog":
        logger.info("IMAGERY_SOURCE=%r, not static_catalog — nothing to seed.", settings.imagery_source)
        return 0

    source = StaticCatalogSource()
    scenes = sorted(source.all_scenes(), key=lambda s: s.datetime)
    if len(scenes) < 2:
        logger.error("demo manifest has fewer than 2 scenes — can't seed a change-detection example.")
        return 1
    date_a = date.fromisoformat(scenes[0].datetime[:10])
    date_b = date.fromisoformat(scenes[-1].datetime[:10])
    aoi_geometry = source.aoi_geometry

    with SessionLocal() as session:
        existing = session.query(AOI).filter(AOI.name == DEMO_AOI_NAME).first()
        if existing is not None:
            logger.info("demo AOI %r already exists (id=%s) — already seeded, nothing to do.", DEMO_AOI_NAME, existing.id)
            return 0

        aoi = AOI(
            name=DEMO_AOI_NAME,
            description="Bundled offline demo scenes — see infra/demo-data/manifest.json.",
            geom=geojson_to_wkb(aoi_geometry),
        )
        session.add(aoi)
        session.flush()
        logger.info("created demo AOI %s", aoi.id)

        monitor = Monitor(
            aoi_id=aoi.id,
            schedule=DEMO_MONITOR_SCHEDULE,
            active=True,
            baseline_date=date_a,
            last_scene_date=date_b,
        )
        session.add(monitor)
        session.flush()
        logger.info("created demo monitor %s", monitor.id)

        analysis = AnalysisResult(
            aoi_id=aoi.id,
            monitor_id=monitor.id,
            date_a=date_a,
            date_b=date_b,
            threshold=settings.change_detection_default_threshold,
            status=AnalysisStatus.PENDING.value,
        )
        session.add(analysis)
        session.commit()

        try:
            execute_change_detection(session, analysis)
        except ChangeDetectionError as exc:
            logger.error("demo change-detection analysis failed: %s", exc)
            session.rollback()
            return 1
        logger.info("computed demo analysis %s (status=%s, stats=%s)", analysis.id, analysis.status, analysis.stats)

        changed_pixel_count = (analysis.stats or {}).get("changed_pixel_count", 0)
        if changed_pixel_count > 0:
            event = Event(
                monitor_id=monitor.id,
                aoi_id=aoi.id,
                analysis_result_id=analysis.id,
                metric_value=(analysis.stats or {}).get("pct_changed", 0.0),
                threshold=analysis.threshold,
                summary=(
                    f"Change detected for AOI {aoi.id}: {changed_pixel_count} pixel(s) "
                    f"exceeded NDVI-diff threshold {analysis.threshold} between {date_a} and {date_b}."
                ),
            )
            session.add(event)
            session.commit()
            logger.info("created demo event %s", event.id)

    logger.info("demo data seed complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
