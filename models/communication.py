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


class CommunicationTemplateResponse(BaseModel):
    id: int
    template_key: str
    name: str
    channel: str
    subject_template: str
    body_template: str
    version: int
    is_active: bool
    created_at: datetime


class CommunicationVersionResponse(BaseModel):
    id: int
    communication_draft_id: int
    version: int
    subject: str
    body: str
    edited_by: int
    edited_by_name: str
    source: str
    source_template_id: int | None
    source_template_name: str | None
    created_at: datetime


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
    created_by_name: str
    last_edited_by: int
    last_edited_by_name: str
    approved_by: int | None
    approved_by_name: str | None
    approved_at: datetime | None
    sent_by: int | None
    sent_by_name: str | None
    sent_at: datetime | None
    provider_message_id: str | None
    provider_payload: dict | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
