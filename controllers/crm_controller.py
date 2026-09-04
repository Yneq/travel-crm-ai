from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies import get_current_user, get_db_connection, require_roles
from models.crm import (
    MemberCreate,
    MemberResponse,
    MemberStatus,
    MemberUpdate,
    TaskCreate,
    TaskResponse,
    TaskStatus,
    TaskUpdate,
    TravelRequestCreate,
    TravelRequestResponse,
    TravelRequestStatus,
    TravelRequestUpdate,
)
from repositories import crm_repository as repository
from services.workflow import (
    InvalidTransition,
    ensure_task_transition,
    ensure_travel_request_transition,
)


router = APIRouter(prefix="/api", tags=["crm"])
write_access = require_roles("admin", "advisor")


def _not_found(entity: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{entity} not found",
    )


@router.post(
    "/members",
    status_code=status.HTTP_201_CREATED,
    response_model=MemberResponse,
)
def create_member(
    payload: MemberCreate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    return repository.create_member(
        connection,
        payload.model_dump(),
        actor_id=current_user["id"],
    )


@router.get("/members", response_model=list[MemberResponse])
def list_members(
    member_status: MemberStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return repository.list_members(
        connection,
        member_status.value if member_status else None,
        search,
        limit,
        offset,
    )


@router.get("/members/{member_id}", response_model=MemberResponse)
def get_member(
    member_id: int,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    member = repository.get_member(connection, member_id)
    if member is None:
        raise _not_found("Member")
    return member


@router.patch("/members/{member_id}", response_model=MemberResponse)
def update_member(
    member_id: int,
    payload: MemberUpdate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field is required",
        )
    member = repository.update_member(connection, member_id, changes, current_user["id"])
    if member is None:
        raise _not_found("Member")
    return member


@router.post(
    "/travel-requests",
    status_code=status.HTTP_201_CREATED,
    response_model=TravelRequestResponse,
)
def create_travel_request(
    payload: TravelRequestCreate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        return repository.create_travel_request(
            connection,
            payload.model_dump(),
            actor_id=current_user["id"],
        )
    except LookupError as exc:
        raise _not_found("Member") from exc


@router.get("/travel-requests", response_model=list[TravelRequestResponse])
def list_travel_requests(
    request_status: TravelRequestStatus | None = Query(default=None, alias="status"),
    member_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return repository.list_travel_requests(
        connection,
        request_status.value if request_status else None,
        member_id,
        limit,
        offset,
    )


@router.get("/travel-requests/{request_id}", response_model=TravelRequestResponse)
def get_travel_request(
    request_id: int,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    travel_request = repository.get_travel_request(connection, request_id)
    if travel_request is None:
        raise _not_found("Travel request")
    return travel_request


@router.patch("/travel-requests/{request_id}", response_model=TravelRequestResponse)
def update_travel_request(
    request_id: int,
    payload: TravelRequestUpdate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    current = repository.get_travel_request(connection, request_id)
    if current is None:
        raise _not_found("Travel request")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field is required",
        )

    start_date = changes.get("start_date", current["start_date"])
    end_date = changes.get("end_date", current["end_date"])
    if start_date and end_date and end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date must not be earlier than start_date",
        )

    if payload.status is not None:
        try:
            ensure_travel_request_transition(current["status"], payload.status)
        except InvalidTransition as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    return repository.update_travel_request(
        connection,
        request_id,
        changes,
        current_user["id"],
    )


@router.post(
    "/tasks",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskResponse,
)
def create_task(
    payload: TaskCreate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    return repository.create_task(
        connection,
        payload.model_dump(),
        actor_id=current_user["id"],
    )


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    assignee_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return repository.list_tasks(
        connection,
        task_status.value if task_status else None,
        assignee_id,
        limit,
        offset,
    )


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    current = repository.get_task(connection, task_id)
    if current is None:
        raise _not_found("Task")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field is required",
        )
    if payload.status is not None:
        try:
            ensure_task_transition(current["status"], payload.status)
        except InvalidTransition as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
    return repository.update_task(connection, task_id, changes, current_user["id"])
