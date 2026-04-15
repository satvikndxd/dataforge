from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Dict
from datetime import datetime


# ------------------------------------------------------------------
# Request Models
# ------------------------------------------------------------------

class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500, description="Research topic to investigate")
    format: Literal["csv", "json"] = Field(default="json", description="Output dataset format")
    num_sources: int = Field(default=20, ge=10, le=50, description="Max number of sources to fetch")
    modality: Literal["text", "image_cnn", "audio", "graph_gnn", "network"] = "text"


# ------------------------------------------------------------------
# Source Models
# ------------------------------------------------------------------

class SourceItem(BaseModel):
    title: str
    url: str
    domain: str
    relevance_score: float = 0.0
    selected: bool = True


# ------------------------------------------------------------------
# Dataset Record
# ------------------------------------------------------------------

class DataRecord(BaseModel):
    id: str
    type: str
    content: str
    metadata: Dict


# ------------------------------------------------------------------
# Job / Progress Models
# ------------------------------------------------------------------

class JobStatus(BaseModel):
    job_id: str
    status: Literal["pending", "searching", "pending_selection", "scraping", "processing", "done", "failed"]
    stage: str
    progress: int  # 0–100
    message: str = ""
    error: Optional[str] = None


class Job(BaseModel):
    id: str
    topic: str
    format: str
    modality: str
    status: Literal["pending", "searching", "pending_selection", "scraping", "processing", "done", "failed"]
    sources: List[SourceItem] = []
    selected_sources: List[str] = []
    results: List[Dict] = []
    created_at: Optional[str] = None
    error: Optional[str] = None


class JobResult(BaseModel):
    job_id: str
    topic: str
    format: str
    modality: str
    sources_used: int
    total_records: int
    records: List[Dict]  # raw dicts — avoids Pydantic coercion on dynamic metadata
    created_at: Optional[str] = None


class SourceSelectionRequest(BaseModel):
    job_id: str
    selected_urls: List[str]
