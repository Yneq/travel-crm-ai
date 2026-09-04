from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from services.planning_provider import PlanningProvider


class PlanningState(TypedDict, total=False):
    context: dict
    planning_notes: str | None
    summary: str
    provider_plan: dict
    missing_fields: list[str]
    itinerary_items: list[dict]
    guardrails: dict
    node_trace: list[str]


def build_planning_graph(provider: PlanningProvider):
    def prepare_context(state: PlanningState) -> dict:
        return {
            "node_trace": [*state.get("node_trace", []), "prepare_privacy_safe_context"],
        }

    def identify_gaps(state: PlanningState) -> dict:
        request = state["context"]["request"]
        checks = {
            "start_date": request.get("start_date"),
            "end_date": request.get("end_date"),
            "budget_amount": request.get("budget_amount"),
            "requirements": request.get("requirements"),
        }
        return {
            "missing_fields": [name for name, value in checks.items() if not value],
            "node_trace": [*state["node_trace"], "identify_missing_information"],
        }

    def generate(state: PlanningState) -> dict:
        plan = provider.generate_plan(state["context"], state.get("planning_notes"))
        return {
            "provider_plan": plan,
            "summary": plan["summary"],
            "itinerary_items": plan["itinerary_items"],
            "node_trace": [*state["node_trace"], "generate_structured_plan"],
        }

    def guardrail(state: PlanningState) -> dict:
        items = state["itinerary_items"]
        return {
            "guardrails": {
                "requires_human_review": True,
                "unverified_supplier_claims": False,
                "unverified_prices": False,
                "has_draft_items": bool(items),
                "warnings": [
                    "此草稿未查詢即時庫存、營業時間或價格。",
                    "核准只會建立可編輯的行程草稿，不會建立訂單或付款。",
                ],
            },
            "node_trace": [*state["node_trace"], "quality_guardrail"],
        }

    builder = StateGraph(PlanningState)
    builder.add_node("prepare_privacy_safe_context", prepare_context)
    builder.add_node("identify_missing_information", identify_gaps)
    builder.add_node("generate_structured_plan", generate)
    builder.add_node("quality_guardrail", guardrail)
    builder.add_edge(START, "prepare_privacy_safe_context")
    builder.add_edge("prepare_privacy_safe_context", "identify_missing_information")
    builder.add_edge("identify_missing_information", "generate_structured_plan")
    builder.add_edge("generate_structured_plan", "quality_guardrail")
    builder.add_edge("quality_guardrail", END)
    return builder.compile()


def run_planning_graph(context: dict, planning_notes: str | None, provider: PlanningProvider) -> dict:
    result = build_planning_graph(provider).invoke(
        {"context": context, "planning_notes": planning_notes, "node_trace": []}
    )
    request = context["request"]
    return {
        "summary": result["summary"],
        "missing_fields": result["missing_fields"],
        "draft_name": f"{request['destination']} AI 行程草稿",
        "itinerary_items": result["itinerary_items"],
        "guardrails": result["guardrails"],
        "node_trace": result["node_trace"],
    }
