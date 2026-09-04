from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AIRunStatus(StrEnum):
    AWAITING_REVIEW = "awaiting_review"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"


class AIReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class AIPlanCreate(BaseModel):
    planning_notes: str | None = Field(default=None, max_length=2000)


class AIPlanReview(BaseModel):
    decision: AIReviewDecision
    notes: str | None = Field(default=None, max_length=2000)


class AIPlanResponse(BaseModel):
    id: int
    request_id: int
    workflow_name: str
    workflow_version: str
    model_name: str
    status: AIRunStatus
    input_data: dict
    output_data: dict | None
    error_data: dict | None
    started_at: datetime
    completed_at: datetime | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    review_notes: str | None
    applied_trip_id: int | None


class AIPlanReviewResult(BaseModel):
    run: AIPlanResponse
    trip_id: int | None = None
