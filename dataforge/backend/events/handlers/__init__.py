"""Default event subscribers: audit trail + monitoring counters."""
from __future__ import annotations

import logging
import threading
from collections import Counter

from backend.core.ids import new_id
from backend.events.schemas import Event

logger = logging.getLogger(__name__)

_metrics_lock = threading.Lock()
METRICS: Counter = Counter()


def _audit_handler(event: Event) -> None:
    """Mirror governance-relevant events into audit_logs."""
    interesting_prefixes = ("agent.", "dataset.version.", "security.", "review.", "export.")
    if not event.event_type.startswith(interesting_prefixes):
        return
    from backend.db.base import session_scope
    from backend.db.models import AuditLog

    with session_scope() as session:
        session.add(
            AuditLog(
                id=new_id("aud"),
                org_id=event.tenant_id,
                actor=event.actor,
                action=event.event_type,
                resource_type=event.payload.get("resource_type", ""),
                resource_id=event.payload.get("resource_id", event.run_id or ""),
                payload=event.payload,
            )
        )


def _metrics_handler(event: Event) -> None:
    with _metrics_lock:
        METRICS[event.event_type] += 1
        METRICS["events.total"] += 1


def register_default_handlers(bus) -> None:
    bus.add_handler(">", _metrics_handler)
    bus.add_handler(">", _audit_handler)
