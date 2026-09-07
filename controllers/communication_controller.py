from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from dependencies import get_current_user, get_db_connection, require_roles
from models.communication import CommunicationResponse, CommunicationUpdate
from repositories import communication_repository as repository


router = APIRouter(prefix="/api", tags=["communication drafts"])
write_access = require_roles("admin", "advisor")


def _raise(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, repository.CommunicationConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/communication-drafts", response_model=list[CommunicationResponse])
def list_drafts(
    limit: int = 100,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return repository.list_drafts(connection, min(max(limit, 1), 100))


@router.post(
    "/reminders/{reminder_id}/communication-draft",
    status_code=status.HTTP_201_CREATED,
    response_model=CommunicationResponse,
)
def create_draft(
    reminder_id: int,
    response: Response,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        draft, created = repository.create_from_reminder(
            connection, reminder_id, current_user["id"]
        )
    except (LookupError, repository.CommunicationConflict, ValueError) as exc:
        _raise(exc)
    if not created:
        response.status_code = status.HTTP_200_OK
    return draft


@router.patch("/communication-drafts/{draft_id}", response_model=CommunicationResponse)
def update_draft(
    draft_id: int,
    payload: CommunicationUpdate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        return repository.update_draft(
            connection, draft_id, payload.subject, payload.body, current_user["id"]
        )
    except (LookupError, repository.CommunicationConflict, ValueError) as exc:
        _raise(exc)


@router.post(
    "/communication-drafts/{draft_id}/approve",
    response_model=CommunicationResponse,
)
def approve_draft(
    draft_id: int,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        return repository.approve_draft(connection, draft_id, current_user["id"])
    except (LookupError, repository.CommunicationConflict, ValueError) as exc:
        _raise(exc)


@router.post(
    "/communication-drafts/{draft_id}/send",
    response_model=CommunicationResponse,
)
def send_draft(
    draft_id: int,
    response: Response,
    idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        draft, sent = repository.send_draft(
            connection, draft_id, idempotency_key, current_user["id"]
        )
    except (LookupError, repository.CommunicationConflict, ValueError) as exc:
        _raise(exc)
    if not sent:
        response.status_code = status.HTTP_200_OK
    return draft
