import json
import os
import time
from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class PlanningProviderConfigurationError(RuntimeError):
    pass


class PlanningProviderError(RuntimeError):
    pass


class GeneratedItineraryItem(BaseModel):
    day: int = Field(ge=1, le=10)
    item_type: Literal["hotel", "flight", "transfer", "activity", "dining", "other"]
    title: str = Field(min_length=1, max_length=160)
    location: str | None = Field(default=None, max_length=255)
    rationale: str = Field(min_length=1, max_length=500)


class GeneratedTravelPlan(BaseModel):
    summary: str = Field(min_length=1, max_length=1200)
    itinerary_items: list[GeneratedItineraryItem] = Field(min_length=2, max_length=30)


class PlanningProvider(Protocol):
    name: str

    def generate_plan(self, context: dict, planning_notes: str | None) -> dict:
        ...


class LocalPlanningProvider:
    """Deterministic local adapter for development; it does not call an LLM."""

    name = "local-planner"

    def generate_plan(self, context: dict, planning_notes: str | None) -> dict:
        request = context["request"]
        member = context["member"]
        budget = (
            f"{request['budget_currency']} {request['budget_amount']}"
            if request.get("budget_amount") is not None
            else "預算待確認"
        )
        date_range = (
            f"{request['start_date']} 至 {request['end_date']}"
            if request.get("start_date") and request.get("end_date")
            else "日期待確認"
        )
        styles = context.get("preferences", {}).get("travel_styles") or []
        style_text = "、".join(styles) if styles else "偏好待訪談"
        note_text = f"；顧問補充：{planning_notes}" if planning_notes else ""
        summary = (
            f"{member['name']}，{request['party_size']} 位旅客前往{request['destination']}，"
            f"期間為{date_range}，預算 {budget}，旅遊偏好為{style_text}{note_text}。"
        )
        destination = request["destination"]
        day_count = _day_count(request.get("start_date"), request.get("end_date"))
        items = [
            {
                "day": 1,
                "item_type": "transfer",
                "title": f"抵達{destination}與專車接送",
                "location": destination,
                "rationale": "先安排抵達與移動銜接，實際航班和供應商需由顧問確認。",
            },
            {
                "day": 1,
                "item_type": "hotel",
                "title": "飯店入住與休息",
                "location": destination,
                "rationale": "依會員房型偏好篩選，草稿不指定未查證的飯店或價格。",
            },
        ]
        for day in range(2, max(2, day_count)):
            items.append(
                {
                    "day": day,
                    "item_type": "activity",
                    "title": f"{destination}主題體驗與在地探索",
                    "location": destination,
                    "rationale": "依旅遊風格安排，開放時間與預約條件需人工查證。",
                }
            )
        items.append(
            {
                "day": day_count,
                "item_type": "transfer",
                "title": "退房與返程接送",
                "location": destination,
                "rationale": "保留足夠交通緩衝，實際時間依航班調整。",
            }
        )
        return {"summary": summary, "itinerary_items": items}


class GeminiPlanningProvider:
    TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_ms: int = 20_000,
        max_retries: int = 2,
        fallback_model: str | None = None,
        max_output_tokens: int = 8_192,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout_ms = timeout_ms
        self.max_retries = max(0, max_retries)
        self.fallback_model = fallback_model if fallback_model != model else None
        self.max_output_tokens = max(2_048, max_output_tokens)
        self.name = f"gemini:{model}"

    def generate_plan(self, context: dict, planning_notes: str | None) -> dict:
        from google import genai
        from google.genai import errors, types

        prompt = build_gemini_prompt(context, planning_notes)
        candidate_models = [self.model]
        if self.fallback_model:
            candidate_models.append(self.fallback_model)
        response = None
        last_error = None
        for model_index, candidate_model in enumerate(candidate_models):
            for attempt in range(self.max_retries + 1):
                try:
                    with genai.Client(
                        api_key=self.api_key,
                        http_options=types.HttpOptions(timeout=self.timeout_ms),
                    ) as client:
                        response = client.models.generate_content(
                            model=candidate_model,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema=GeneratedTravelPlan,
                                max_output_tokens=self.max_output_tokens,
                            ),
                        )
                    try:
                        parsed = response.parsed
                        plan = (
                            parsed
                            if isinstance(parsed, GeneratedTravelPlan)
                            else GeneratedTravelPlan.model_validate(parsed)
                            if parsed is not None
                            else GeneratedTravelPlan.model_validate_json(response.text)
                        )
                    except Exception as exc:
                        last_error = exc
                        response = None
                        if model_index < len(candidate_models) - 1:
                            break
                        raise PlanningProviderError(
                            "Gemini returned an invalid planning response"
                        ) from exc
                    self.name = f"gemini:{candidate_model}"
                    return plan.model_dump()
                except errors.APIError as exc:
                    last_error = exc
                    transient = exc.code in self.TRANSIENT_STATUS_CODES
                    if transient and attempt < self.max_retries:
                        time.sleep(2**attempt)
                        continue
                    if transient and model_index < len(candidate_models) - 1:
                        break
                    raise PlanningProviderError(
                        f"Gemini request failed ({exc.code}): {exc.message}"
                    ) from exc
                except (TimeoutError, OSError) as exc:
                    last_error = exc
                    if attempt < self.max_retries:
                        time.sleep(2**attempt)
                        continue
                    if model_index < len(candidate_models) - 1:
                        break
                    raise PlanningProviderError(
                        "Gemini request timed out or could not connect"
                    ) from exc
        raise PlanningProviderError("Gemini request failed after model fallback") from last_error


def _external_context(context: dict) -> dict:
    request = context["request"]
    member = context["member"]
    preferences = context.get("preferences", {})
    return {
        "traveler": {field: member.get(field) for field in ("name", "tier", "locale")},
        "request": {
            field: request.get(field)
            for field in (
                "title",
                "destination",
                "start_date",
                "end_date",
                "party_size",
                "budget_currency",
                "budget_amount",
                "requirements",
            )
        },
        "preferences": {
            field: preferences.get(field, [])
            for field in (
                "travel_styles",
                "dietary_restrictions",
                "room_preferences",
                "accessibility_needs",
            )
        },
    }


def build_gemini_prompt(context: dict, planning_notes: str | None) -> str:
    payload = _external_context(context)
    payload["advisor_notes"] = planning_notes
    return (
        "你是高端旅遊公司的行程規劃助理。請使用繁體中文產生需求摘要與逐日行程草稿。"
        "只能使用輸入資料；不得聲稱已查詢即時價格、庫存、營業時間或完成預訂；"
        "不得捏造特定供應商。每個項目的 rationale 必須指出仍需顧問查證的內容。"
        "日期不完整時以三天草稿處理，最多規劃十天。\n\n輸入資料：\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


def _day_count(start: date | None, end: date | None) -> int:
    if start and end:
        return max(1, min((end - start).days + 1, 10))
    return 3


PROVIDERS: dict[str, PlanningProvider] = {"local": LocalPlanningProvider()}


def get_planning_provider(name: str = "local") -> PlanningProvider:
    if name == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise PlanningProviderConfigurationError(
                "Gemini is selected but GEMINI_API_KEY is not configured"
            )
        return GeminiPlanningProvider(
            api_key=api_key,
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            timeout_ms=int(os.getenv("AI_PROVIDER_TIMEOUT_MS", "20000")),
            max_retries=int(os.getenv("AI_PROVIDER_MAX_RETRIES", "2")),
            fallback_model=os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite"),
            max_output_tokens=int(os.getenv("AI_PROVIDER_MAX_OUTPUT_TOKENS", "8192")),
        )
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise PlanningProviderConfigurationError(
            f"Unsupported planning provider: {name}"
        ) from exc
