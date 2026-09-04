import os

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from dependencies import get_current_user, get_db_connection, require_roles
from models.ai import AIPlanCreate, AIPlanResponse, AIPlanReview, AIPlanReviewResult
from repositories import ai_repository as repository
from services.planning_provider import (
    PlanningProviderConfigurationError,
    PlanningProviderError,
)


router = APIRouter(prefix="/api", tags=["ai planning"])
write_access = require_roles("admin", "advisor")


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, repository.AIWorkflowConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, PlanningProviderConfigurationError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, PlanningProviderError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/travel-requests/{request_id}/ai-plans",
    status_code=status.HTTP_201_CREATED,
    response_model=AIPlanResponse,
)
def create_ai_plan(
    request_id: int,
    payload: AIPlanCreate,
    response: Response,
    idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        run, created = repository.create_ai_plan(
            connection,
            request_id,
            payload.planning_notes,
            idempotency_key,
            current_user["id"],
        )
    except (
        LookupError,
        repository.AIWorkflowConflict,
        PlanningProviderConfigurationError,
        PlanningProviderError,
        ValueError,
    ) as exc:
        raise _http_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return run


@router.get("/ai/providers/status")
def provider_status(_current_user: dict = Depends(get_current_user)):
    active = os.getenv("AI_PLANNING_PROVIDER", "local")
    return {
        "active_provider": active,
        "active_model": (
            os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
            if active == "gemini"
            else "local-planner"
        ),
        "fallback_model": (
            os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
            if active == "gemini"
            else None
        ),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "external_context_fields": {
            "traveler": ["name", "tier", "locale"],
            "request": [
                "title",
                "destination",
                "start_date",
                "end_date",
                "party_size",
                "budget_currency",
                "budget_amount",
                "requirements",
            ],
            "preferences": [
                "travel_styles",
                "dietary_restrictions",
                "room_preferences",
                "accessibility_needs",
            ],
        },
    }


@router.get(
    "/travel-requests/{request_id}/ai-plans",
    response_model=list[AIPlanResponse],
)
def list_ai_plans(
    request_id: int,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return repository.list_ai_plans(connection, request_id)


@router.get("/ai-plans/{run_id}", response_model=AIPlanResponse)
def get_ai_plan(
    run_id: int,
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    run = repository.get_ai_plan(connection, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="AI plan not found")
    return run


@router.post("/ai-plans/{run_id}/review", response_model=AIPlanReviewResult)
def review_ai_plan(
    run_id: int,
    payload: AIPlanReview,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        run, trip_id = repository.review_ai_plan(
            connection,
            run_id,
            payload.decision.value,
            payload.notes,
            current_user["id"],
        )
    except (LookupError, repository.AIWorkflowConflict, ValueError) as exc:
        raise _http_error(exc) from exc
    return AIPlanReviewResult(run=run, trip_id=trip_id)
