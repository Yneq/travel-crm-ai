"""Optional Apple Silicon Qwen/MLX benchmark providers.

MLX is imported only when this target is selected. No application default changes.
"""

import json
from functools import lru_cache
from types import SimpleNamespace

from services.followup_provider import GeneratedFollowUp, build_followup_prompt
from services.operations_agent_provider import validate_model_answer
from services.planning_provider import GeneratedTravelPlan, build_gemini_prompt


DEFAULT_MLX_MODEL = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
READ_TOOLS = (
    "operations_overview", "overdue_tasks", "payment_followups",
    "upcoming_departures", "advisor_workload", "quote_followups",
)


def build_mlx_followup_instruction(context: dict) -> str:
    return (
        build_followup_prompt(context)
        + "\n只輸出 JSON 物件，包含 internal_summary、recommended_steps"
          "（字串陣列）、message_subject、message_body、requires_human_review"
          "（必須是 true）。"
    )


@lru_cache(maxsize=2)
def _load(model_id: str):
    try:
        from mlx_lm import load
    except ImportError as exc:
        raise RuntimeError("MLX target requires the optional mlx-lm package") from exc
    return load(model_id)


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    value = json.loads(cleaned.strip())
    if not isinstance(value, dict):
        raise ValueError("MLX response must be a JSON object")
    return value


class MlxRuntime:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.name = f"mlx:{model_id}"
        self.last_usage = None

    def generate(self, instruction: str, *, max_tokens: int = 768) -> str:
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        model, tokenizer = _load(self.model_id)
        prompt = tokenizer.apply_chat_template(
            [{"role": "user", "content": instruction}],
            tokenize=False,
            add_generation_prompt=True,
        )
        parts = []
        last = None
        for response in stream_generate(
            model, tokenizer, prompt=prompt, max_tokens=max_tokens,
            sampler=make_sampler(temp=0),
        ):
            parts.append(response.text)
            last = response
        if last is None:
            raise RuntimeError("MLX returned no generation")
        usage = SimpleNamespace(
            prompt_token_count=last.prompt_tokens,
            candidates_token_count=last.generation_tokens,
            total_token_count=last.prompt_tokens + last.generation_tokens,
        )
        if self.last_usage is None:
            self.last_usage = usage
        else:
            self.last_usage = SimpleNamespace(
                prompt_token_count=self.last_usage.prompt_token_count + usage.prompt_token_count,
                candidates_token_count=self.last_usage.candidates_token_count + usage.candidates_token_count,
                total_token_count=self.last_usage.total_token_count + usage.total_token_count,
            )
        return "".join(parts)

    def generate_json(self, instruction: str, *, max_tokens: int = 768) -> dict:
        raw = self.generate(instruction, max_tokens=max_tokens)
        try:
            return _parse_json(raw)
        except json.JSONDecodeError:
            repaired = self.generate(
                "請把下列內容修正成有效的 JSON 物件。保持原有資料，不加說明或 Markdown。"
                "\n原始要求：" + instruction + "\n待修正內容：" + raw,
                max_tokens=max_tokens,
            )
            return _parse_json(repaired)


class MlxPlanningProvider(MlxRuntime):
    def generate_plan(self, context: dict, planning_notes: str | None) -> dict:
        self.last_usage = None
        prompt = build_gemini_prompt(context, planning_notes)
        result = self.generate_json(
            prompt + "\n只輸出 JSON 物件。格式：{\"summary\":\"文字\","
            "\"itinerary_items\":[{\"day\":1,\"item_type\":\"activity\","
            "\"title\":\"文字\",\"location\":\"文字\",\"rationale\":\"文字\"}]}。"
            "至少三個行程項目，每天至少一項。",
            max_tokens=1024,
        )
        return GeneratedTravelPlan.model_validate(result).model_dump()


class MlxFollowUpProvider(MlxRuntime):
    def generate_followup(self, context: dict) -> dict:
        self.last_usage = None
        result = self.generate_json(
            build_mlx_followup_instruction(context),
            max_tokens=768,
        )
        return GeneratedFollowUp.model_validate(result).model_dump()


class MlxOperationsAgentProvider(MlxRuntime):
    def run(self, question: str, execute_tool) -> dict:
        self.last_usage = None
        selected = _parse_json(self.generate(
            "你是唯讀 CRM 路由器。依問題選擇最少且必要的工具。只能從以下名稱選擇："
            + ", ".join(READ_TOOLS)
            + "。operations_overview=營運總覽；overdue_tasks=待辦任務；"
              "payment_followups=待付款；upcoming_departures=近期出發；"
              "advisor_workload=顧問負荷；quote_followups=停滯報價。"
              "只輸出 JSON，例如 {\"tools\":[\"operations_overview\"]}。問題："
            + question,
            max_tokens=128,
        )).get("tools")
        if (not isinstance(selected, list) or not selected or
                len(selected) > len(READ_TOOLS) or
                any(tool not in READ_TOOLS for tool in selected) or
                len(set(selected)) != len(selected)):
            raise ValueError("MLX selected invalid CRM tools")
        tool_results = [{"tool": tool, "result": execute_tool(tool)} for tool in selected]
        answer = self.generate(
            "你是唯讀 CRM 助理。只能根據以下工具資料回答，使用繁體中文。"
            "不得聲稱已付款、預訂、寄送、建立或修改任何資料；需要後續動作時請建議人工確認。"
            "資料：" + json.dumps(tool_results, ensure_ascii=False, default=str)
            + "\n問題：" + question,
            max_tokens=384,
        ).strip()
        validate_model_answer(answer)
        return {"answer": answer, "tool_results": tool_results,
                "provider": self.name, "fallback_used": False}
