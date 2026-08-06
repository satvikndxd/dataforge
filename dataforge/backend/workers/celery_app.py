"""Celery application for production deployments.

Queue topology (spec §4.5): ingest.light / ingest.bulk / ai.llm /
ai.embedding / graph.build / export.small / export.large / maintenance.

Run:  celery -A backend.workers.celery_app worker -Q ingest.light,ai.embedding
"""
from __future__ import annotations

from backend.core.config import get_settings

try:  # pragma: no cover - optional in self-hosted mode
    from celery import Celery

    settings = get_settings()
    broker = settings.celery_broker_url or settings.redis_url or "redis://localhost:6379/0"

    celery_app = Celery("dataforge", broker=broker, backend=broker)
    celery_app.conf.update(
        task_default_queue="ingest.light",
        task_routes={
            "dataforge.pipeline.run": {"queue": "ingest.light"},
            "dataforge.export.build": {"queue": "export.small"},
        },
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
    )

    @celery_app.task(name="dataforge.pipeline.run", bind=True, max_retries=3)
    def run_pipeline_task(self, run_id: str):  # pragma: no cover
        from backend.pipelines.engine import execute_run

        try:
            execute_run(run_id)
        except Exception as exc:
            raise self.retry(exc=exc, countdown=min(2 ** self.request.retries * 10, 300))

    @celery_app.task(name="dataforge.export.build")
    def build_export_task(export_id: str):  # pragma: no cover
        from backend.services.exports import execute_export

        execute_export(export_id)

except ImportError:  # pragma: no cover
    celery_app = None
