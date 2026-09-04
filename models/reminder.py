from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ReminderStatus(StrEnum):
    SCHEDULED = "scheduled"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


class ReminderType(StrEnum):
    MANUAL = "manual"
    TASK_DUE = "task_due"
    PAYMENT_FOLLOW_UP = "payment_follow_up"
    TRIP_COUNTDOWN = "trip_countdown"


class ReminderUpdate(BaseModel):
    status: ReminderStatus


class ReminderResponse(BaseModel):
    id: int
    task_id: int | None
    member_id: int | None
    reminder_type: ReminderType
    source_type: str | None
    source_id: int | None
    dedup_key: str | None
    title: str
    channel: str
    scheduled_at: datetime
    status: ReminderStatus
    payload: dict = Field(default_factory=dict)
    sent_at: datetime | None
    last_error: str | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReminderScanResponse(BaseModel):
    created_count: int
    existing_count: int
    scanned_at: datetime
    reminders: list[ReminderResponse]
