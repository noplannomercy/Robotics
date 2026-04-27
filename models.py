from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetType(StrEnum):
    PLSQL = "plsql"
    DICTIONARY = "dictionary"
    ERD = "erd"
    POLICY = "policy"


class Job(BaseModel):
    id: str
    status: JobStatus
    asset_type: str
    file_name: str
    file_size: int | None = None
    source_hash: str
    result: str | None = None
    error: str | None = None
    attempts: int = 0
    callback_url: str | None = None
    requested_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
