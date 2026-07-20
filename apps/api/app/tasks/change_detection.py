import logging
import uuid

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.imagery.sensor import SensorType, sensor_for_collection
from app.models.aoi import AOI
from app.models.analysis_result import AnalysisResult, AnalysisStatus, DetectionStatus
from app.services.change_detection_pipeline import execute_change_detection
from app.services.detection_pipeline import run_placeholder_detection

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.change_detection.run_change_detection", bind=True)
def run_change_detection(self, analysis_id: str) -> None:
    """Thin Celery wrapper: the real pipeline logic lives in
    app.services.change_detection_pipeline so it's unit-testable without Celery."""
    with SessionLocal() as session:
        analysis = session.get(AnalysisResult, uuid.UUID(analysis_id))
        if analysis is None:
            return

        analysis.celery_task_id = self.request.id
        session.commit()

        try:
            execute_change_detection(session, analysis)
        except Exception as exc:
            session.rollback()
            analysis = session.get(AnalysisResult, uuid.UUID(analysis_id))
            analysis.status = AnalysisStatus.FAILED.value
            analysis.error_message = str(exc)
            session.commit()
            return

        # Best-effort: the analysis itself already succeeded, so a detection
        # failure (e.g. services/inference unreachable) never flips it to
        # FAILED. But it's no longer swallowed silently — the outcome is
        # recorded on the analysis (detection_status/count/error) so the UI can
        # tell "ran, found 0" apart from "detection failed" apart from "skipped
        # because SAR". SAR AOIs have no honest detector yet, so detection is
        # deliberately not attempted for them (SKIPPED), not run-and-failed.
        aoi = session.get(AOI, analysis.aoi_id)
        if aoi is not None and sensor_for_collection(aoi.collection) is SensorType.OPTICAL:
            try:
                run_placeholder_detection(session, analysis)  # records OK + count itself
            except Exception as exc:
                session.rollback()
                analysis = session.get(AnalysisResult, uuid.UUID(analysis_id))
                analysis.detection_status = DetectionStatus.FAILED.value
                analysis.detection_error = str(exc)
                session.commit()
                logger.exception("placeholder detection failed for analysis %s", analysis_id)
        else:
            analysis.detection_status = DetectionStatus.SKIPPED.value
            analysis.detection_error = None
            session.commit()
