import unittest
from pathlib import Path

from scripts.train_followup_cuda import load_chat_records, tokenize_record


ROOT = Path(__file__).resolve().parents[1]


class StubTokenizer:
    eos_token = "<eos>"

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert tokenize is False and add_generation_prompt is True
        return "USER:" + messages[0]["content"] + " ASSISTANT:"

    def __call__(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        return {"input_ids": list(text.encode("utf-8"))}


class CudaTrainingDataTests(unittest.TestCase):
    def test_prompt_is_masked_and_completion_is_trained(self):
        records = load_chat_records(ROOT / "finetune/followup/data/test.jsonl")
        tokenized = tokenize_record(records[0], StubTokenizer(), 2048)
        tokenizer = StubTokenizer()
        prompt = tokenizer.apply_chat_template(records[0]["messages"][:1],
                                               tokenize=False, add_generation_prompt=True)
        prompt_length = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
        self.assertEqual(len(tokenized["input_ids"]), len(tokenized["labels"]))
        self.assertEqual(len(tokenized["input_ids"]), len(tokenized["attention_mask"]))
        self.assertTrue(all(value == -100 for value in tokenized["labels"][:prompt_length]))
        self.assertEqual(tokenized["input_ids"][prompt_length:],
                         tokenized["labels"][prompt_length:])
        with self.assertRaises(ValueError):
            tokenize_record(records[0], StubTokenizer(), 1)


if __name__ == "__main__":
    unittest.main()
