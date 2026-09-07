import json
import os
from collections.abc import Callable


class OperationsAgentProviderError(RuntimeError):
    pass


def _json_safe(value: dict) -> dict:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def validate_model_answer(answer: str) -> None:
    unsafe_claims = (
        "已替你付款",
        "已完成付款",
        "已建立訂單",
        "已寄送",
        "已聯絡旅客",
        "已完成預訂",
    )
    if not answer.strip():
        raise OperationsAgentProviderError("Gemini returned an empty answer")
    if any(claim in answer for claim in unsafe_claims):
        raise OperationsAgentProviderError("Gemini returned an unsafe action claim")


class GeminiOperationsAgentProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_ms: int = 20_000,
        fallback_model: str | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout_ms = timeout_ms
        self.fallback_model = fallback_model if fallback_model != model else None
        self.name = f"gemini:{model}"

    def run(self, question: str, execute_tool: Callable[[str], dict]) -> dict:
        from google import genai
        from google.genai import types

        executions: list[dict] = []

        def invoke(tool_name: str) -> dict:
            result = _json_safe(execute_tool(tool_name))
            executions.append({"tool": tool_name, "result": result})
            return result

        def operations_overview():
            """取得有效會員、進行中需求、待辦任務、待付款與待處理提醒的數量。"""
            return invoke("operations_overview")

        def overdue_tasks():
            """取得已逾期或未來 24 小時內到期的任務，依期限與優先級排序。"""
            return invoke("overdue_tasks")

        def payment_followups():
            """取得需要人工追蹤的待付款訂單，不執行付款或聯絡。"""
            return invoke("payment_followups")

        def upcoming_departures():
            """取得未來 30 天內已核准或已訂購的出發行程。"""
            return invoke("upcoming_departures")

        candidate_models = [self.model]
        if self.fallback_model:
            candidate_models.append(self.fallback_model)
        last_error = None
        for candidate_model in candidate_models:
            executions.clear()
            try:
                with genai.Client(
                    api_key=self.api_key,
                    http_options=types.HttpOptions(timeout=self.timeout_ms),
                ) as client:
                    chat = client.chats.create(
                        model=candidate_model,
                        config=types.GenerateContentConfig(
                            system_instruction=(
                                "你是高端旅遊 CRM 的內部營運助理。必須先呼叫至少一個工具取得證據，"
                                "只使用工具回傳資料，以繁體中文純文字簡潔回答，不要使用 Markdown。"
                                "不得聲稱已建立、修改、付款、"
                                "預訂、寄送或聯絡；所有外部動作都必須建議由人員確認。"
                            ),
                            tools=[
                                operations_overview,
                                overdue_tasks,
                                payment_followups,
                                upcoming_departures,
                            ],
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                                maximum_remote_calls=4
                            ),
                        ),
                    )
                    response = chat.send_message(question)
                answer = response.text or ""
                validate_model_answer(answer)
                if not executions:
                    raise OperationsAgentProviderError("Gemini did not call a CRM tool")
                return {
                    "answer": answer,
                    "tool_results": list(executions),
                    "provider": f"gemini:{candidate_model}",
                    "fallback_used": candidate_model != self.model,
                }
            except Exception as exc:
                last_error = exc
        raise OperationsAgentProviderError("Gemini function calling failed") from last_error


def get_operations_agent_provider(name: str):
    if name != "gemini":
        return None
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise OperationsAgentProviderError("Gemini API key is not configured")
    return GeminiOperationsAgentProvider(
        api_key=api_key,
        model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        timeout_ms=int(os.getenv("AI_PROVIDER_TIMEOUT_MS", "20000")),
        fallback_model=os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite"),
    )
