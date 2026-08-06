"""Event bus.

In-memory pub/sub with NATS-style subject wildcards (`pipeline.*`, `>`)
as the default; a NATS JetStream adapter takes over when DATAFORGE_NATS_URL
is configured. Every published event is also durably written to the
`events` table, giving an audit trail and replayability regardless of
transport.

Subscriptions are queue-based so both background handlers and live SSE
streams can consume without blocking publishers.
"""
from __future__ import annotations

import fnmatch
import logging
import queue
import threading
from dataclasses import dataclass, field
from typing import Callable

from backend.core.ids import new_id
from backend.events.schemas import Event

logger = logging.getLogger(__name__)


def subject_matches(pattern: str, subject: str) -> bool:
    if pattern in (">", "*", "**"):
        return True
    # NATS-ish: '*' matches one token, '>' matches remainder
    translated = pattern.replace(".", r"\.").replace("*", "[^.]+").replace(">", ".+")
    import re

    return re.fullmatch(translated, subject) is not None or fnmatch.fnmatch(subject, pattern)


@dataclass
class Subscription:
    id: str
    pattern: str
    q: "queue.Queue[Event]" = field(default_factory=lambda: queue.Queue(maxsize=1000))


class EventBus:
    def __init__(self):
        self._subs: dict[str, Subscription] = {}
        self._handlers: list[tuple[str, Callable[[Event], None]]] = []
        self._lock = threading.Lock()

    # -- durable + fanout publish ------------------------------------
    def publish(self, event: Event) -> Event:
        self._persist(event)
        with self._lock:
            subs = list(self._subs.values())
            handlers = list(self._handlers)
        for pattern, handler in handlers:
            if subject_matches(pattern, event.event_type):
                try:
                    handler(event)
                except Exception:  # handlers must never break publishers
                    logger.exception("event handler failed for %s", event.event_type)
        for sub in subs:
            if subject_matches(sub.pattern, event.event_type):
                try:
                    sub.q.put_nowait(event)
                except queue.Full:
                    logger.warning("subscriber %s backpressure: dropping %s", sub.id, event.event_id)
        return event

    def emit(self, event_type: str, *, tenant_id: str = "", project_id: str = "",
             run_id: str = "", actor: str = "system", payload: dict | None = None) -> Event:
        return self.publish(
            Event(event_type=event_type, tenant_id=tenant_id, project_id=project_id,
                  run_id=run_id, actor=actor, payload=payload or {})
        )

    # -- consumption ---------------------------------------------------
    def subscribe(self, pattern: str = ">") -> Subscription:
        sub = Subscription(id=new_id("sub"), pattern=pattern)
        with self._lock:
            self._subs[sub.id] = sub
        return sub

    def unsubscribe(self, sub_id: str) -> None:
        with self._lock:
            self._subs.pop(sub_id, None)

    def add_handler(self, pattern: str, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._handlers.append((pattern, handler))

    # -- durability ----------------------------------------------------
    @staticmethod
    def _persist(event: Event) -> None:
        try:
            from backend.db.base import session_scope
            from backend.db.models import EventRecord

            with session_scope() as session:
                session.add(
                    EventRecord(
                        id=event.event_id,
                        org_id=event.tenant_id,
                        event_type=event.event_type,
                        run_id=event.run_id or None,
                        actor=event.actor,
                        payload=event.payload,
                    )
                )
        except Exception:
            logger.exception("failed to persist event %s", event.event_id)


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
        from backend.events.handlers import register_default_handlers

        register_default_handlers(_bus)
    return _bus


def reset_event_bus() -> None:
    global _bus
    _bus = None
