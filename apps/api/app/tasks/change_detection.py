import logging
import uuid

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.analysis_result import AnalysisResult, AnalysisStatus
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

        # Best-effort: the analysis itself already succeeded. A detection
        # failure (e.g. services/inference unreachable) is logged, not
        # surfaced as an AnalysisResult failure.
        try:
            run_placeholder_detection(session, analysis)
        except Exception:
            session.rollback()
            logger.exception("placeholder detection failed for analysis %s", analysis_id)
