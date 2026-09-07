from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from repositories.operations_agent_repository import TOOL_LABELS
from services.operations_agent_provider import get_operations_agent_provider


class OperationsAgentState(TypedDict, total=False):
    question: str
    pending_tools: list[str]
    tool_results: list[dict]
    answer: str
    node_trace: list[str]
    guardrails: dict


def select_tools(question: str) -> list[str]:
    normalized = question.lower()
    selected: list[str] = []
    keyword_groups = [
        ("overdue_tasks", ("任務", "待辦", "逾期", "到期", "task", "todo")),
        ("payment_followups", ("付款", "未付款", "收款", "payment", "order")),
        ("upcoming_departures", ("出發", "行程", "近期", "departure", "trip")),
    ]
    for tool, keywords in keyword_groups:
        if any(keyword in normalized for keyword in keywords):
            selected.append(tool)
    if not selected or any(keyword in normalized for keyword in ("總覽", "全部", "整體", "overview")):
        selected.insert(0, "operations_overview")
    return list(dict.fromkeys(selected))[:4]


def _format_item(tool: str, item: dict) -> str:
    if tool == "overdue_tasks":
        owner = f"（{item['member_name']}）" if item.get("member_name") else ""
        return f"- {item['title']}{owner}｜{item['priority']}｜期限 {item['due_at']}"
    if tool == "payment_followups":
        return f"- {item['order_number']}｜{item['member_name']}｜{item['currency']} {item['total']}"
    if tool == "upcoming_departures":
        return f"- {item['start_date']}｜{item['member_name']}｜{item['destination']}（{item['status']}）"
    return f"- {item}"


def synthesize_answer(tool_results: list[dict]) -> str:
    sections: list[str] = []
    for execution in tool_results:
        tool = execution["tool"]
        result = execution["result"]
        label = TOOL_LABELS[tool]
        if tool == "operations_overview":
            summary = result["summary"]
            sections.append(
                f"{label}：有效會員 {summary['active_members']}、進行中需求 {summary['active_requests']}、"
                f"待辦任務 {summary['open_tasks']}、待付款訂單 {summary['pending_payments']}、"
                f"待處理提醒 {summary['scheduled_reminders']}。"
            )
            continue
        items = result.get("items", [])
        if not items:
            sections.append(f"{label}：目前沒有符合條件的項目。")
        else:
            sections.append(f"{label}（{len(items)} 筆）：\n" + "\n".join(_format_item(tool, item) for item in items))
    sections.append("建議先確認上述資料的最新狀態，再由人員決定是否建立任務、聯絡旅客或進行付款操作。")
    return "\n\n".join(sections)


def build_operations_agent_graph(execute_tool: Callable[[str], dict]):
    def route(state: OperationsAgentState) -> dict:
        return {
            "pending_tools": select_tools(state["question"]),
            "tool_results": [],
            "node_trace": ["route_intent"],
        }

    def execute_next(state: OperationsAgentState) -> dict:
        pending = list(state["pending_tools"])
        tool = pending.pop(0)
        result = execute_tool(tool)
        return {
            "pending_tools": pending,
            "tool_results": [*state["tool_results"], {"tool": tool, "result": result}],
            "node_trace": [*state["node_trace"], f"tool:{tool}"],
        }

    def next_step(state: OperationsAgentState) -> str:
        return "execute_tool" if state["pending_tools"] else "synthesize"

    def synthesize(state: OperationsAgentState) -> dict:
        return {
            "answer": synthesize_answer(state["tool_results"]),
            "node_trace": [*state["node_trace"], "synthesize_evidence"],
        }

    def guardrail(state: OperationsAgentState) -> dict:
        return {
            "guardrails": {
                "read_only_tools": True,
                "requires_human_confirmation": True,
                "external_actions_executed": False,
                "note": "Agent 只能讀取營運資料，不會自行建立訂單、付款或發送訊息。",
            },
            "node_trace": [*state["node_trace"], "enforce_read_only_guardrail"],
        }

    builder = StateGraph(OperationsAgentState)
    builder.add_node("route_intent", route)
    builder.add_node("execute_tool", execute_next)
    builder.add_node("synthesize", synthesize)
    builder.add_node("guardrail", guardrail)
    builder.add_edge(START, "route_intent")
    builder.add_edge("route_intent", "execute_tool")
    builder.add_conditional_edges("execute_tool", next_step)
    builder.add_edge("synthesize", "guardrail")
    builder.add_edge("guardrail", END)
    return builder.compile()


def run_operations_agent(question: str, execute_tool: Callable[[str], dict]) -> dict:
    result = build_operations_agent_graph(execute_tool).invoke({"question": question})
    tools_used = [
        {
            "tool": item["tool"],
            "label": TOOL_LABELS[item["tool"]],
            "result_count": len(item["result"].get("items", [])) if item["tool"] != "operations_overview" else 1,
        }
        for item in result["tool_results"]
    ]
    return {
        "answer": result["answer"],
        "tools_used": tools_used,
        "node_trace": result["node_trace"],
        "guardrails": result["guardrails"],
        "provider": "langgraph-local",
        "fallback_used": False,
    }


def run_operations_agent_with_fallback(
    question: str,
    execute_tool: Callable[[str], dict],
    provider_name: str,
    provider=None,
) -> dict:
    if provider_name != "gemini":
        return run_operations_agent(question, execute_tool)
    try:
        active_provider = provider or get_operations_agent_provider(provider_name)
        model_result = active_provider.run(question, execute_tool)
        tool_results = model_result["tool_results"]
        output = {
            "answer": model_result["answer"],
            "tools_used": [
                {
                    "tool": item["tool"],
                    "label": TOOL_LABELS[item["tool"]],
                    "result_count": len(item["result"].get("items", []))
                    if item["tool"] != "operations_overview" else 1,
                }
                for item in tool_results
            ],
            "node_trace": [
                "model_route_intent",
                *[f"function_call:{item['tool']}" for item in tool_results],
                "model_synthesize_evidence",
                "enforce_read_only_guardrail",
            ],
            "guardrails": {
                "read_only_tools": True,
                "requires_human_confirmation": True,
                "external_actions_executed": False,
                "note": "Gemini 只能呼叫唯讀 CRM 工具，不會自行建立訂單、付款或發送訊息。",
            },
            "provider": model_result["provider"],
            "fallback_used": model_result.get("fallback_used", False),
        }
        return output
    except Exception:
        output = run_operations_agent(question, execute_tool)
        output["fallback_used"] = True
        return output
