from pydantic import BaseModel, Field


class OperationsAgentRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class ToolExecution(BaseModel):
    tool: str
    label: str
    result_count: int


class OperationsAgentResponse(BaseModel):
    run_id: int
    answer: str
    tools_used: list[ToolExecution]
    node_trace: list[str]
    guardrails: dict

