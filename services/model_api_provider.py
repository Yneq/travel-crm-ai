"""HTTP adapters sharing the same structured prompts/validators as MLX.

No MLX imports or GPU are needed to use this runtime. The model endpoint is
operator-configured, not accepted from user input.
"""
import os
from types import SimpleNamespace
import httpx
from services.planning_provider import PlanningProviderError
from services.mlx_provider import MlxPlanningProvider, MlxFollowUpProvider, MlxOperationsAgentProvider

DEFAULT_API_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


class ModelApiRuntime:
    def __init__(self, model_id):
        self.model_id = model_id
        self.name = f"model-api:{model_id}"
        self.last_usage = None
        self.base_url = os.getenv("MODEL_API_URL", "http://127.0.0.1:18090").rstrip("/")

    def generate(self, instruction, *, max_tokens=768):
        response = httpx.post(
            self.base_url + "/v1/generate",
            json={"model": self.model_id, "instruction": instruction, "max_tokens": max_tokens},
            timeout=600, trust_env=False,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("provider") != "model-api" or result.get("model") != self.model_id:
            raise ValueError("Model API returned mismatched identity")
        usage = result.get("usage")
        if usage is not None:
            keys = ("input_tokens", "output_tokens", "total_tokens")
            if any(type(usage.get(key)) is not int or usage[key] < 0 for key in keys):
                raise ValueError("Model API returned invalid usage")
            previous = self.last_usage
            self.last_usage = SimpleNamespace(
                prompt_token_count=usage["input_tokens"] + (previous.prompt_token_count if previous else 0),
                candidates_token_count=usage["output_tokens"] + (previous.candidates_token_count if previous else 0),
                total_token_count=usage["total_tokens"] + (previous.total_token_count if previous else 0),
            )
        if not isinstance(result.get("text"), str):
            raise ValueError("Model API returned no text")
        return result["text"]


class ModelApiPlanningProvider(ModelApiRuntime, MlxPlanningProvider):
    def generate_plan(self, context, planning_notes):
        try:
            return super().generate_plan(context, planning_notes)
        except (httpx.HTTPError, ValueError) as exc:
            raise PlanningProviderError(f"Model API planning failed: {exc}") from exc


class ModelApiFollowUpProvider(ModelApiRuntime, MlxFollowUpProvider):
    def generate_followup(self, context):
        try:
            return super().generate_followup(context)
        except (httpx.HTTPError, ValueError) as exc:
            raise PlanningProviderError(f"Model API follow-up failed: {exc}") from exc


class ModelApiOperationsProvider(ModelApiRuntime, MlxOperationsAgentProvider):
    def run(self, question, execute_tool):
        self.last_error = None
        try:
            return super().run(question, execute_tool)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise
