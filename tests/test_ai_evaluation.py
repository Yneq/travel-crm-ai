import unittest
from pathlib import Path

from services.ai_evaluation import contains_risky_claim, load_fixtures, run_evaluation


ROOT = Path(__file__).resolve().parents[1]


class AIEvaluationTests(unittest.TestCase):
    def test_fixed_local_regression_set_passes_all_contracts(self):
        fixtures = load_fixtures(ROOT / "evals" / "fixtures.json")

        report = run_evaluation(fixtures, "local")

        self.assertEqual(12, report["overall"]["case_count"])
        self.assertEqual(12, report["overall"]["passed_count"])
        self.assertEqual(1.0, report["overall"]["privacy_pass_rate"])
        self.assertEqual(1.0, report["overall"]["guardrail_pass_rate"])
        self.assertEqual(
            1.0,
            report["workflows"]["operations_agent"]["summary"]["tool_selection_accuracy"],
        )

    def test_risky_operational_claim_is_detected(self):
        self.assertTrue(contains_risky_claim({"message_body": "您的訂單已完成付款"}))
        self.assertFalse(contains_risky_claim({"message_body": "請由顧問確認付款狀態"}))


if __name__ == "__main__":
    unittest.main()
