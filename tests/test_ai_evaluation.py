import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services.ai_evaluation import _usage, contains_risky_claim, load_fixtures, run_benchmark, run_evaluation
from services.benchmark_provider import BenchmarkTarget, make_benchmark_adapter


ROOT = Path(__file__).resolve().parents[1]


class AIEvaluationTests(unittest.TestCase):
    def test_fixed_local_regression_set_passes_all_contracts(self):
        fixtures = load_fixtures(ROOT / "evals" / "fixtures.json")

        report = run_evaluation(fixtures, "local")

        self.assertEqual(16, report["overall"]["case_count"])
        self.assertEqual(16, report["overall"]["passed_count"])
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


if __name__ == "__main__":
    unittest.main()
