"""
In-memory job store for DataForge pipeline jobs.
Each job_id maps to a mutable JobState dict.
"""

import uuid
from typing import Dict, Any, Optional


# Global in-memory store: { job_id: dict }
_store: Dict[str, Dict[str, Any]] = {}


def create_job(topic: str, fmt: str, num_sources: int, modality: str = "text") -> str:
    job_id = str(uuid.uuid4())
    _store[job_id] = {
        "job_id": job_id,
        "topic": topic,
        "format": fmt,
        "modality": modality,
        "num_sources": num_sources,
        "status": "pending",
        "stage": "Initializing",
        "progress": 0,
        "message": "",
        "error": None,
        "sources": [],          # List[dict] from research
        "selected_urls": [],    # After user selects
        "records": [],          # Final DataRecord dicts
        "created_at": None,
    }
    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    return _store.get(job_id)


def update_job(job_id: str, **kwargs) -> None:
    if job_id in _store:
        _store[job_id].update(kwargs)


def all_jobs() -> Dict[str, Dict[str, Any]]:
    return _store
