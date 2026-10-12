import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.compare_followup_adapter import evaluate_records, load_records


ROOT = Path(__file__).resolve().parents[1]


class StubProvider:
    model_id = "stub"
    adapter_path = None
    last_usage = None

    def generate_json(self, prompt):
        self.last_usage = SimpleNamespace(
            prompt_token_count=10, candidates_token_count=5, total_token_count=15)
        return json.loads(self.answer)


class FollowupAdapterComparisonTests(unittest.TestCase):
    def test_heldout_scorer_checks_schema_guardrails_and_exact_match(self):
        records = load_records(ROOT / "finetune/followup/data/test.jsonl")
        self.assertEqual(12, len(records))
        provider = StubProvider()
        provider.answer = records[0]["messages"][1]["content"]
        result = evaluate_records(records[:1], provider)
        self.assertEqual(1.0, result["metrics"]["exact_label_match"])
        self.assertEqual(15, result["cases"][0]["token_usage"]["total_tokens"])

        answer = json.loads(provider.answer)
        answer["requires_human_review"] = False
        provider.answer = json.dumps(answer)
        result = evaluate_records(records[:1], provider)
        self.assertEqual(0.0, result["metrics"]["guardrail_pass"])
        self.assertEqual(0.0, result["metrics"]["exact_label_match"])


    def test_output_capture_is_opt_in_and_preserves_invalid_generation(self):
        records = load_records(ROOT / "finetune/followup/data/test.jsonl")
        provider = StubProvider()
        provider.answer = records[0]["messages"][1]["content"]
        self.assertNotIn("generated_output", evaluate_records(records[:1], provider)["cases"][0])
        captured = evaluate_records(records[:1], provider, include_outputs=True)["cases"][0]
        self.assertEqual(captured["expected_output"], captured["generated_output"])
        class BrokenProvider(StubProvider):
            last_raw_output = None
            def generate_json(self, prompt):
                self.last_raw_output = "invalid-json"
                raise ValueError("invalid JSON")
        failed = evaluate_records(records[:1], BrokenProvider(), include_outputs=True)["cases"][0]
        self.assertEqual(failed["raw_output"], "invalid-json")
        self.assertFalse(failed["schema_valid"])


if __name__ == "__main__":
    unittest.main()
