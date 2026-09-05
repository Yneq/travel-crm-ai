import json
import os
import time
from typing import Protocol

from pydantic import BaseModel, Field

from services.planning_provider import PlanningProviderConfigurationError, PlanningProviderError


class GeneratedFollowUp(BaseModel):
    internal_summary: str = Field(min_length=1, max_length=500)
    recommended_steps: list[str] = Field(min_length=1, max_length=5)
    message_subject: str = Field(min_length=1, max_length=160)
    message_body: str = Field(min_length=1, max_length=2000)
    requires_human_review: bool = True


class FollowUpProvider(Protocol):
    name: str

    def generate_followup(self, context: dict) -> dict:
        ...


class LocalFollowUpProvider:
    name = "local-followup"

    def generate_followup(self, context: dict) -> dict:
        reminder = context["reminder"]
        member = context.get("member") or {}
        traveler = member.get("name") or "旅客"
        action = reminder["recommended_action"]
        reminder_type = reminder["type"]
        if reminder_type == "payment_follow_up":
            subject = "付款狀態確認"
            body = f"{traveler}您好，我們想確認目前的付款狀態。如需協助，請告訴我們，我們會由顧問為您確認。"
        elif reminder_type == "trip_countdown":
            subject = "出發前行程確認"
            body = f"{traveler}您好，您的旅程即將出發。我們正在做最後確認，顧問確認文件與行程版本後會再與您聯繫。"
        else:
            subject = "旅程安排進度確認"
            body = f"{traveler}您好，我們正在確認您的旅程安排進度；待顧問核對最新資訊後會再與您聯繫。"
        return {
            "internal_summary": f"{reminder['title']}。{reminder['reason']}",
            "recommended_steps": [action, "核對 CRM 最新紀錄", "由顧問修改並決定是否使用聯絡草稿"],
            "message_subject": subject,
            "message_body": body,
            "requires_human_review": True,
        }


class GeminiFollowUpProvider:
    TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, api_key: str, model: str, timeout_ms: int = 20_000, max_retries: int = 2):
        self.api_key = api_key
        self.model = model
        self.timeout_ms = timeout_ms
        self.max_retries = max(0, max_retries)
        self.name = f"gemini:{model}"

    def generate_followup(self, context: dict) -> dict:
        from google import genai
        from google.genai import errors, types

        prompt = build_followup_prompt(context)
        for attempt in range(self.max_retries + 1):
            try:
                with genai.Client(
                    api_key=self.api_key,
                    http_options=types.HttpOptions(timeout=self.timeout_ms),
                ) as client:
                    response = client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=GeneratedFollowUp,
                            max_output_tokens=4096,
                        ),
                    )
                parsed = response.parsed
                result = (
                    parsed
                    if isinstance(parsed, GeneratedFollowUp)
                    else GeneratedFollowUp.model_validate(parsed)
                    if parsed is not None
                    else GeneratedFollowUp.model_validate_json(response.text)
                )
                return result.model_dump()
            except errors.APIError as exc:
                if exc.code in self.TRANSIENT_STATUS_CODES and attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
                raise PlanningProviderError(f"Gemini follow-up request failed ({exc.code})") from exc
            except (TimeoutError, OSError) as exc:
                if attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
                raise PlanningProviderError("Gemini follow-up request timed out") from exc
            except Exception as exc:
                raise PlanningProviderError("Gemini returned an invalid follow-up response") from exc
        raise PlanningProviderError("Gemini follow-up request failed")


def _external_context(context: dict) -> dict:
    member = context.get("member") or {}
    reminder = context["reminder"]
    return {
        "member": {field: member.get(field) for field in ("name", "tier", "locale")},
        "reminder": {
            field: reminder.get(field)
            for field in ("type", "title", "reason", "recommended_action", "severity")
        },
    }


def build_followup_prompt(context: dict) -> str:
    return (
        "你是高端旅遊公司的內部營運助理。請用繁體中文產生內部摘要、最多五項處理步驟，"
        "以及一份可由顧問編輯的旅客聯絡草稿。不得宣稱已付款、完成預訂、確認庫存或已寄送；"
        "不得加入輸入中沒有的資訊。requires_human_review 必須為 true。\n\n輸入資料：\n"
        + json.dumps(_external_context(context), ensure_ascii=False, default=str)
    )


def get_followup_provider(name: str = "local") -> FollowUpProvider:
    if name == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise PlanningProviderConfigurationError(
                "Gemini follow-up is selected but GEMINI_API_KEY is not configured"
            )
        return GeminiFollowUpProvider(
            api_key=api_key,
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            timeout_ms=int(os.getenv("AI_PROVIDER_TIMEOUT_MS", "20000")),
            max_retries=int(os.getenv("AI_PROVIDER_MAX_RETRIES", "2")),
        )
    if name == "local":
        return LocalFollowUpProvider()
    raise PlanningProviderConfigurationError(f"Unsupported follow-up provider: {name}")


def generate_followup_with_fallback(context: dict, provider_name: str) -> tuple[dict, str]:
    provider = get_followup_provider(provider_name)
    try:
        return provider.generate_followup(context), provider.name
    except PlanningProviderError:
        if provider_name == "local":
            raise
        fallback = LocalFollowUpProvider()
        draft = fallback.generate_followup(context)
        draft["provider_warning"] = "外部 AI 暫時無法使用，已切換為本機安全草稿，請人工確認內容。"
        return draft, f"{fallback.name}:fallback"
