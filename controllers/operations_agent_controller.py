import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from dependencies import get_current_user, get_db_connection, require_roles
from models.operations_agent import (
    ActionProposalPage,
    ActionProposalResponse,
    ActionProposalReview,
    OperationsAgentRequest,
    OperationsAgentResponse,
)
from repositories import operations_agent_repository as repository
from services.operations_agent_graph import run_operations_agent_with_fallback


router = APIRouter(prefix="/api/operations-agent", tags=["operations agent"])
write_access = require_roles("admin", "advisor")


@router.post("/runs", response_model=OperationsAgentResponse)
def create_operations_agent_run(
    payload: OperationsAgentRequest,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(get_current_user),
):
    run_id = repository.start_run(connection, payload.question, current_user["id"])
    try:
        output = run_operations_agent_with_fallback(
            payload.question,
            lambda tool: repository.execute_read_tool(connection, tool),
            os.getenv("AI_OPERATIONS_PROVIDER", "local"),
        )
        output = repository.complete_run(connection, run_id, output, current_user["id"])
        return {"run_id": run_id, **output}
    except Exception as exc:
        repository.fail_run(connection, run_id, exc)
        raise HTTPException(status_code=500, detail="Operations Agent could not complete the request") from exc


@router.get("/proposals", response_model=ActionProposalPage)
def list_action_proposals(
    status: Literal["pending", "executed", "rejected", "expired"] | None = None,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=8, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    connection=Depends(get_db_connection),
    _current_user: dict = Depends(get_current_user),
):
    return repository.list_action_proposals(
        connection, status=status, search=search, limit=limit, offset=offset
    )


@router.post("/proposals/{proposal_id}/review", response_model=ActionProposalResponse)
def review_action_proposal(
    proposal_id: int,
    payload: ActionProposalReview,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(write_access),
):
    try:
        return repository.review_action_proposal(
            connection, proposal_id, payload.decision, payload.notes, current_user["id"]
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except repository.ActionProposalConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
