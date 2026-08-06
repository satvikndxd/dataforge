"""Event envelope (spec §4.4)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from backend.core.ids import new_id


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    event_type: str
    schema_version: str = "1.0"
    tenant_id: str = ""
    project_id: str = ""
    run_id: str = ""
    actor: str = "system"
    trace_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_wire(self) -> dict:
        data = self.model_dump()
        data["timestamp"] = self.timestamp.isoformat()
        return data


# Canonical event types (non-exhaustive; plugins may add their own)
EVENT_TYPES = [
    "dataset.created",
    "dataset.version.created",
    "dataset.version.published",
    "source.added",
    "ingestion.started",
    "document.fetched",
    "scrape.failed",
    "extraction.completed",
    "cleaning.completed",
    "embedding.generated",
    "dedup.completed",
    "quality.scored",
    "graph.updated",
    "review.requested",
    "review.completed",
    "export.started",
    "export.completed",
    "agent.run.started",
    "agent.run.completed",
    "agent.action.proposed",
    "agent.action.approved",
    "agent.action.rejected",
    "security.violation.detected",
    "alert.raised",
    "pipeline.started",
    "pipeline.stage.started",
    "pipeline.stage.completed",
    "pipeline.completed",
    "pipeline.failed",
]
