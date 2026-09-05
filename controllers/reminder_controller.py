from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from dependencies import get_current_user, get_db_connection, require_roles
from models.reminder import FollowUpReview, ReminderResponse, ReminderScanResponse, ReminderStatus, ReminderUpdate
from repositories import reminder_repository as repository
from services.workflow import InvalidTransition, ensure_reminder_transition
from services.planning_provider import PlanningProviderConfigurationError, PlanningProviderError


router = APIRouter(prefix="/api", tags=["operational reminders"])
write_access = require_roles("admin", "advisor")


@router.get("/reminders", response_model=list[ReminderResponse])
def list_reminders(
    reminder_status: ReminderStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return repository.list_reminders(
        connection, reminder_status.value if reminder_status else None, limit, offset
    )


@router.post("/reminders/scan", response_model=ReminderScanResponse)
def scan_reminders(
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return repository.scan_operational_reminders(connection, current_user["id"], now)


@router.patch("/reminders/{reminder_id}", response_model=ReminderResponse)
def update_reminder(
    reminder_id: int,
    payload: ReminderUpdate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    current = repository.get_reminder(connection, reminder_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    try:
        ensure_reminder_transition(current["status"], payload.status)
    except InvalidTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return repository.update_reminder_status(
        connection,
        reminder_id,
        payload.status.value,
        current_user["id"],
        datetime.now(timezone.utc).replace(tzinfo=None),
    )


@router.post(
    "/reminders/{reminder_id}/ai-draft",
    status_code=status.HTTP_201_CREATED,
    response_model=ReminderResponse,
)
def create_followup_draft(
    reminder_id: int,
    response: Response,
    idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        reminder, created = repository.create_followup_draft(
            connection, reminder_id, idempotency_key, current_user["id"]
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except repository.FollowUpConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PlanningProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PlanningProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return reminder


@router.post(
    "/reminders/{reminder_id}/ai-draft/review",
    response_model=ReminderResponse,
)
def review_followup_draft(
    reminder_id: int,
    payload: FollowUpReview,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        return repository.review_followup_draft(
            connection, reminder_id, payload.decision.value, payload.notes, current_user["id"]
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except repository.FollowUpConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
