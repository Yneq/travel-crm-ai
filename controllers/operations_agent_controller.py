from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user, get_db_connection
from models.operations_agent import OperationsAgentRequest, OperationsAgentResponse
from repositories import operations_agent_repository as repository
from services.operations_agent_graph import run_operations_agent


router = APIRouter(prefix="/api/operations-agent", tags=["operations agent"])


@router.post("/runs", response_model=OperationsAgentResponse)
def create_operations_agent_run(
    payload: OperationsAgentRequest,
    connection=Depends(get_db_connection),
    current_user: dict = Depends(get_current_user),
):
    run_id = repository.start_run(connection, payload.question, current_user["id"])
    try:
        output = run_operations_agent(
            payload.question,
            lambda tool: repository.execute_read_tool(connection, tool),
        )
        repository.complete_run(connection, run_id, output, current_user["id"])
        return {"run_id": run_id, **output}
    except Exception as exc:
        repository.fail_run(connection, run_id, exc)
        raise HTTPException(status_code=500, detail="Operations Agent could not complete the request") from exc

