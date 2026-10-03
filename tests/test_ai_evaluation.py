import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services.ai_evaluation import (
    _normalize_planning_context, _usage, contains_risky_claim, evaluate_followup, evaluate_operations_agent,
    evaluate_planning, load_fixtures, run_benchmark, run_evaluation,
)
from services.benchmark_provider import BenchmarkTarget, make_benchmark_adapter
from services.followup_provider import LocalFollowUpProvider
from services.mlx_provider import MlxOperationsAgentProvider, MlxRuntime, _load, _parse_json
from services.planning_provider import LocalPlanningProvider


ROOT = Path(__file__).resolve().parents[1]


class AIEvaluationTests(unittest.TestCase):
    def test_fixed_local_regression_set_passes_all_contracts(self):
        fixtures = load_fixtures(ROOT / "evals" / "fixtures.json")

        report = run_evaluation(fixtures, "local")

        self.assertEqual(16, report["overall"]["case_count"])
        self.assertEqual(16, report["overall"]["passed_count"])
        self.assertEqual("member_email_phone_exact_match_prompt_and_output", report["privacy_check"])
        self.assertEqual(1.0, report["overall"]["privacy_pass_rate"])
        self.assertEqual(1.0, report["overall"]["guardrail_pass_rate"])
        self.assertEqual(
            1.0,
            report["workflows"]["operations_agent"]["summary"]["tool_selection_accuracy"],
        )

    def test_risky_operational_claim_is_detected(self):
        self.assertTrue(contains_risky_claim({"message_body": "您的訂單已完成付款"}))
        self.assertFalse(contains_risky_claim({"message_body": "請由顧問確認付款狀態"}))

    def test_comparison_preserves_case_identity_and_unavailable_usage(self):
        fixtures = load_fixtures(ROOT / "evals" / "fixtures.json")
        report = run_benchmark(fixtures, [BenchmarkTarget("local")])
        self.assertEqual(16, report["comparison"][0]["passed_count"])
        self.assertEqual("unavailable", report["comparison"][0]["token_usage"]["status"])
        self.assertEqual({"local"}, set(report["runs"]))
        cases = report["runs"]["local"]["workflows"]["operations_agent"]["cases"]
        self.assertTrue(all(case["provider"] == "langgraph-local" and case["model"] is None for case in cases))

    def test_model_is_forwarded_to_each_gemini_workflow(self):
        target = BenchmarkTarget("gemini", "gemini-test")
        with patch("services.benchmark_provider.get_planning_provider") as planning, \
             patch("services.benchmark_provider.get_followup_provider") as followup, \
             patch("services.benchmark_provider.get_operations_agent_provider") as operations:
            adapter = make_benchmark_adapter(target)
            adapter.planning()
            adapter.followup()
            adapter.operations()
        planning.assert_called_once_with("gemini", model="gemini-test")
        followup.assert_called_once_with("gemini", model="gemini-test")
        operations.assert_called_once_with("gemini", model="gemini-test")

    def test_usage_uses_only_reported_token_counts(self):
        provider = SimpleNamespace(last_usage=SimpleNamespace(
            prompt_token_count=10, candidates_token_count=4, total_token_count=14))
        self.assertEqual(14, _usage(provider)["total_tokens"])
        self.assertEqual("unavailable", _usage(SimpleNamespace())["status"])

    def test_failed_generation_separates_attempted_from_actual_provider(self):
        fixtures = load_fixtures(ROOT / "evals" / "fixtures.json")
        target = BenchmarkTarget("gemini", "test-model")
        provider = SimpleNamespace(name="gemini:test-model", last_usage=None,
                                   generate_followup=Mock(side_effect=RuntimeError("offline")))
        adapter = SimpleNamespace(planning=Mock(return_value=provider),
                                  followup=Mock(return_value=provider))
        with patch("services.ai_evaluation.make_benchmark_adapter", return_value=adapter), \
             patch("services.ai_evaluation.run_planning_graph", side_effect=RuntimeError("offline")):
            planning = evaluate_planning(fixtures["planning"][:1], "gemini", target)["cases"][0]
            followup = evaluate_followup(fixtures["followup"][:1], "gemini", target)["cases"][0]
        for case in (planning, followup):
            self.assertFalse(case["passed"])
            self.assertEqual("gemini", case["provider_attempted"])
            self.assertEqual("test-model", case["model_attempted"])
            self.assertIsNone(case["provider"])
            self.assertIsNone(case["model"])
            self.assertEqual("unavailable", case["token_usage"]["status"])

    def test_privacy_metric_catches_contact_data_in_model_response(self):
        fixtures = load_fixtures(ROOT / "evals" / "fixtures.json")
        planning_fixture = fixtures["planning"][0]
        followup_fixture = fixtures["followup"][0]
        planning_output = LocalPlanningProvider().generate_plan(
            _normalize_planning_context(planning_fixture["context"]), planning_fixture.get("notes")
        )
        planning_output["summary"] += " planning-canary@example.com"
        followup_output = LocalFollowUpProvider().generate_followup(followup_fixture["context"])
        followup_output["message_body"] += " 0911222333"
        adapter = SimpleNamespace(
            planning=Mock(return_value=SimpleNamespace(
                name="local-planner", generate_plan=Mock(return_value=planning_output))),
            followup=Mock(return_value=SimpleNamespace(
                name="local-followup", generate_followup=Mock(return_value=followup_output))),
        )
        with patch("services.ai_evaluation.make_benchmark_adapter", return_value=adapter):
            planning = evaluate_planning([planning_fixture], "local")["cases"][0]
            followup = evaluate_followup([followup_fixture], "local")["cases"][0]
        for case in (planning, followup):
            self.assertTrue(case["schema_valid"])
            self.assertFalse(case["privacy_pass"])
            self.assertFalse(case["passed"])

    def test_fallback_records_actual_local_provider_and_attempted_model(self):
        fixtures = load_fixtures(ROOT / "evals" / "fixtures.json")
        target = BenchmarkTarget("gemini", "test-model")
        provider = SimpleNamespace(name="gemini:test-model", last_usage=None,
                                   run=Mock(side_effect=RuntimeError("offline")))
        adapter = SimpleNamespace(operations=Mock(return_value=provider))
        with patch("services.ai_evaluation.make_benchmark_adapter", return_value=adapter):
            case = evaluate_operations_agent(
                fixtures["operations_agent"][:1], "gemini", target
            )["cases"][0]
        self.assertEqual("langgraph-local", case["provider"])
        self.assertEqual("gemini", case["provider_attempted"])
        self.assertEqual("test-model", case["model_attempted"])
        self.assertTrue(case["fallback_used"])
        self.assertFalse(case["provider_pass"])

    def test_mlx_target_is_optional_and_has_a_fixed_default_model(self):
        target = BenchmarkTarget("mlx")
        self.assertTrue(target.label.startswith("mlx:mlx-community/Qwen"))
        adapter = make_benchmark_adapter(target)
        self.assertEqual(target.label, adapter.planning().name)
        self.assertEqual(target.label, adapter.followup().name)
        self.assertEqual(target.label, adapter.operations().name)

    def test_mlx_operations_uses_only_selected_read_tools(self):
        provider = MlxOperationsAgentProvider("test-model")
        with patch.object(provider, "generate", side_effect=[
            '{"tools":["payment_followups"]}', "有一筆待付款資料，請顧問確認。",
        ]) as generate:
            result = provider.run("哪些訂單待付款？", lambda tool: {"items": [{"id": 1}]})
        self.assertEqual("mlx:test-model", result["provider"])
        self.assertEqual("payment_followups", result["tool_results"][0]["tool"])
        self.assertEqual(2, generate.call_count)

    def test_mlx_rejects_invalid_json_and_tool_names(self):
        with self.assertRaises(ValueError):
            _parse_json("not json")
        provider = MlxOperationsAgentProvider("test-model")
        with patch.object(provider, "generate", return_value='{"tools":["delete_orders"]}'):
            with self.assertRaises(ValueError):
                provider.run("delete", lambda tool: {})

    def test_mlx_repairs_invalid_json_once(self):
        runtime = MlxRuntime("test-model")
        with patch.object(runtime, "generate", side_effect=['{"a":', '{"a":1}']) as generate:
            self.assertEqual({"a": 1}, runtime.generate_json("Return a JSON object"))
        self.assertEqual(2, generate.call_count)

    def test_mlx_loader_passes_optional_adapter_to_model_runtime(self):
        loader = Mock(return_value=(object(), object()))
        with patch.dict(sys.modules, {"mlx_lm": SimpleNamespace(load=loader)}):
            _load.cache_clear()
            _load("test-model", "/tmp/test-adapter")
            loader.assert_called_once_with("test-model", adapter_path="/tmp/test-adapter")
        _load.cache_clear()


if __name__ == "__main__":
    unittest.main()
