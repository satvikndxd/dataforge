"""Task execution abstraction.

Default executor: a bounded thread pool inside the API process (correct for
self-hosted single-node deployments and tests). Production deployments run
the same task functions on Celery workers (`backend.workers.celery_app`);
the call-sites are identical, only the dispatcher changes.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class TaskQueue:
    def __init__(self, max_workers: int = 8):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="df-worker")
        self._inflight: dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit(self, task_id: str, fn: Callable[..., Any], *args, **kwargs) -> Future:
        def _wrapped():
            try:
                return fn(*args, **kwargs)
            except Exception:
                logger.exception("task %s failed", task_id)
                raise
            finally:
                with self._lock:
                    self._inflight.pop(task_id, None)

        future = self._pool.submit(_wrapped)
        with self._lock:
            self._inflight[task_id] = future
        return future

    def is_running(self, task_id: str) -> bool:
        with self._lock:
            fut = self._inflight.get(task_id)
        return fut is not None and not fut.done()

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            fut = self._inflight.get(task_id)
        return bool(fut and fut.cancel())


_queue: TaskQueue | None = None


def get_task_queue() -> TaskQueue:
    global _queue
    if _queue is None:
        settings = get_settings()
        use_celery = bool(settings.celery_broker_url)
        if use_celery:  # pragma: no cover - requires broker
            logger.info("Celery broker configured; API still uses local dispatch for sync paths")
        _queue = TaskQueue()
    return _queue
