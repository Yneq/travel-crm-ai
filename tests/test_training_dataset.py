import json
import unittest

from scripts.build_followup_dataset import build_records
from services.followup_provider import GeneratedFollowUp


class TrainingDatasetTests(unittest.TestCase):
    def test_synthetic_dataset_is_disjoint_private_and_schema_valid(self):
        records = build_records()
        self.assertEqual({"train": 60, "valid": 12, "test": 12},
                         {split: len(rows) for split, rows in records.items()})
        prompts = []
        for rows in records.values():
            for row in rows:
                self.assertEqual(["user", "assistant"],
                                 [message["role"] for message in row["messages"]])
                prompt = row["messages"][0]["content"]
                prompts.append(prompt)
                self.assertNotIn("@example.invalid", prompt)
                self.assertNotIn("0000000000", prompt)
                answer = GeneratedFollowUp.model_validate_json(row["messages"][1]["content"])
                self.assertTrue(answer.requires_human_review)
        self.assertEqual(len(prompts), len(set(prompts)))


if __name__ == "__main__":
    unittest.main()
