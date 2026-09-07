from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies import get_db_connection, require_roles
from models.audit import AuditFacetResponse, AuditLogPage
from repositories import audit_repository


router = APIRouter(prefix="/api/audit-logs", tags=["audit logs"])
admin_access = require_roles("admin")


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    entity_type: str | None = Query(default=None, min_length=1, max_length=64),
    entity_id: str | None = Query(default=None, min_length=1, max_length=64),
    action: str | None = Query(default=None, min_length=1, max_length=64),
    actor_id: int | None = Query(default=None, ge=1),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(admin_access),
):
    if date_from and date_to and date_to < date_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_to must not be earlier than date_from",
        )
    return audit_repository.list_audit_logs(
        connection,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/facets", response_model=AuditFacetResponse)
def get_audit_facets(
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(admin_access),
):
    return audit_repository.get_audit_facets(connection)
