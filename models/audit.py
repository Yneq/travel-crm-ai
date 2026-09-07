from datetime import datetime

from pydantic import BaseModel


class AuditActorResponse(BaseModel):
    id: int
    name: str


class AuditLogResponse(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str | None
    entity_type: str
    entity_id: str
    action: str
    before_data: dict | None
    after_data: dict | None
    correlation_id: str | None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


class AuditFacetResponse(BaseModel):
    entity_types: list[str]
    actions: list[str]
    actors: list[AuditActorResponse]
