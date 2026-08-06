"""Human review queues + active-learning prioritization (spec §7.15–7.16)."""
from __future__ import annotations

from datetime import datetime, timezone

from backend.core.ids import new_id
from backend.db.base import session_scope
from backend.db.models import Chunk, DatasetVersion, ReviewItem
from backend.events.bus import get_event_bus


def request_review(org_id: str, project_id: str, subject_type: str, subject_id: str,
                   reason: str, *, run_id: str | None = None, priority: float = 0.5) -> str:
    review_id = new_id("rev")
    with session_scope() as session:
        session.add(
            ReviewItem(id=review_id, org_id=org_id, project_id=project_id, run_id=run_id,
                       subject_type=subject_type, subject_id=subject_id,
                       reason=reason, priority=priority)
        )
    get_event_bus().emit("review.requested", tenant_id=org_id, project_id=project_id,
                         payload={"review_id": review_id, "subject_type": subject_type,
                                  "subject_id": subject_id, "reason": reason,
                                  "resource_type": "review", "resource_id": review_id})
    return review_id


def resolve_review(org_id: str, review_id: str, reviewer_id: str,
                   decision: str, notes: str = "") -> dict:
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    with session_scope() as session:
        item = session.get(ReviewItem, review_id)
        if item is None or item.org_id != org_id:
            raise ValueError("review item not found")
        item.status = decision
        item.reviewer_id = reviewer_id
        item.resolution = {"notes": notes}
        item.resolved_at = datetime.now(timezone.utc)
        subject_type, subject_id = item.subject_type, item.subject_id

        # apply the decision to the subject
        if subject_type == "chunk":
            chunk = session.get(Chunk, subject_id)
            if chunk is not None:
                chunk.status = "active" if decision == "approved" else "rejected"
        elif subject_type == "dataset_version" and decision == "approved":
            version = session.get(DatasetVersion, subject_id)
            if version is not None and version.status == "pending_approval":
                version.status = "published"

    get_event_bus().emit("review.completed", tenant_id=org_id,
                         actor=f"user:{reviewer_id}",
                         payload={"review_id": review_id, "decision": decision,
                                  "subject_type": subject_type, "subject_id": subject_id,
                                  "resource_type": "review", "resource_id": review_id})
    if subject_type == "dataset_version" and decision == "approved":
        get_event_bus().emit("dataset.version.published", tenant_id=org_id,
                             actor=f"user:{reviewer_id}",
                             payload={"resource_type": "dataset_version", "resource_id": subject_id})
    return {"review_id": review_id, "status": decision}


def review_priority(quality_score: float, novelty: float = 0.5, policy_risk: float = 0.0) -> float:
    """Active learning: prioritize uncertain (mid-score), novel, risky samples."""
    uncertainty = 1.0 - abs(quality_score - 0.5) * 2  # peak at 0.5
    return round(min(1.0, 0.5 * uncertainty + 0.3 * novelty + 0.2 * policy_risk + policy_risk * 0.5), 4)
