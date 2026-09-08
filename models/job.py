from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    SCHEDULED = "scheduled"
    PROCESSING = "processing"
    RETRYING = "retrying"
    COMPLETED = "completed"
    DEAD_LETTER = "dead_letter"


class JobResponse(BaseModel):
    id: int
    provider: str
    event_type: str
    idempotency_key: str
    status: JobStatus
    payload: dict = Field(default_factory=dict)
    attempts: int
    next_attempt_at: datetime | None
    processed_at: datetime | None
    last_error: str | None
    created_at: datetime


class WorkerStatusResponse(BaseModel):
    redis_ready: bool
    scheduled: int
    processing: int
    retrying: int
    completed: int
    dead_letter: int


class IntegrationComponentStatus(BaseModel):
    component: str
    mode: str
    configured: bool
    external_actions_enabled: bool
    note: str


class IntegrationStatusResponse(BaseModel):
    production_ready: bool
    components: list[IntegrationComponentStatus]
