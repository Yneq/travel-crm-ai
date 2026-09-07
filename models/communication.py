from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CommunicationStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"


class CommunicationUpdate(BaseModel):
    subject: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=5000)


class CommunicationResponse(BaseModel):
    id: int
    reminder_id: int
    member_id: int | None
    channel: str
    recipient_label: str
    subject: str
    body: str
    status: CommunicationStatus
    version: int
    provider: str
    created_by: int
    approved_by: int | None
    approved_at: datetime | None
    sent_by: int | None
    sent_at: datetime | None
    provider_message_id: str | None
    provider_payload: dict | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
