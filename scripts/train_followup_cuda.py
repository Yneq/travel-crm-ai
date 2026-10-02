"""Small, synthetic QLoRA exercise for a free Colab CUDA runtime.

Install the optional requirements in requirements-colab.txt first. This script
never purchases compute, enables a paid runtime, or uploads an adapter.
"""

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_chat_records(path: Path) -> list[dict]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not records:
        raise ValueError(f"Empty dataset: {path}")
    for record in records:
        if [message.get("role") for message in record.get("messages", [])] != ["user", "assistant"]:
            raise ValueError(f"Expected user/assistant chat records in {path}")
    return records


def tokenize_record(record: dict, tokenizer, max_length: int) -> dict:
    messages = record["messages"]
    prompt = tokenizer.apply_chat_template(messages[:1], tokenize=False, add_generation_prompt=True)
    prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    completion_ids = tokenizer(messages[1]["content"] + tokenizer.eos_token,
                               add_special_tokens=False)["input_ids"]
    input_ids = prompt_ids + completion_ids
    if len(input_ids) > max_length:
        raise ValueError(f"Example has {len(input_ids)} tokens; raise --max-length")
    return {
        "input_ids": input_ids,
        "attention_mask": [1] * len(input_ids),
        "labels": [-100] * len(prompt_ids) + completion_ids,
    }


def make_collator(pad_token_id: int):
    import torch

    def collate(examples: list[dict]) -> dict:
        max_length = max(len(example["input_ids"]) for example in examples)
        return {
            key: torch.tensor([
                example[key] + [(-100 if key == "labels" else
                                 0 if key == "attention_mask" else pad_token_id)]
                * (max_length - len(example[key]))
                for example in examples
            ], dtype=torch.long)
            for key in ("input_ids", "attention_mask", "labels")
        }

    return collate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--data", type=Path, default=ROOT / "finetune/followup/data")
    parser.add_argument("--output", type=Path, default=ROOT / "output/followup-colab-qlora")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-length", type=int, default=768)
    args = parser.parse_args()

    import torch
    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU unavailable. Select a free GPU runtime in Colab; no CPU fallback.")
    if args.max_steps < 1 or args.max_length < 1:
        parser.error("--max-steps and --max-length must be positive")

    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              BitsAndBytesConfig, Trainer, TrainingArguments)

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    datasets = {}
    for split in ("train", "valid", "test"):
        records = load_chat_records(args.data / f"{split}.jsonl")
        datasets[split] = Dataset.from_list([
            tokenize_record(record, tokenizer, args.max_length) for record in records
        ])

    bf16 = torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if bf16 else torch.float16
    quantization = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model, quantization_config=quantization, device_map={"": 0},
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM", target_modules=["q_proj", "v_proj"],
    ))

    args.output.mkdir(parents=True, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=str(args.output / "checkpoints"),
        max_steps=args.max_steps,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_steps=3,
        logging_steps=5,
        eval_strategy="steps",
        eval_steps=10,
        save_strategy="no",
        report_to="none",
        fp16=not bf16,
        bf16=bf16,
        gradient_checkpointing=True,
        remove_unused_columns=False,
        seed=42,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=datasets["train"],
        eval_dataset=datasets["valid"],
        data_collator=make_collator(tokenizer.pad_token_id),
    )
    base_test = trainer.evaluate(eval_dataset=datasets["test"], metric_key_prefix="base_test")
    train_result = trainer.train()
    adapted_test = trainer.evaluate(eval_dataset=datasets["test"], metric_key_prefix="adapted_test")
    adapter_dir = args.output / "adapter"
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    report = {
        "task": "synthetic_followup_json",
        "model": args.model,
        "gpu": torch.cuda.get_device_name(0),
        "precision": "bf16" if bf16 else "fp16",
        "quantization": "bitsandbytes NF4 4-bit QLoRA",
        "steps": args.max_steps,
        "split_sizes": {split: len(dataset) for split, dataset in datasets.items()},
        "base_test_loss": base_test["base_test_loss"],
        "adapted_test_loss": adapted_test["adapted_test_loss"],
        "train_loss": train_result.training_loss,
        "adapter_path": str(adapter_dir),
        "cost": "not measured; use only an explicitly free Colab runtime",
        "limitations": [
            "Labels are deterministic synthetic templates, not human-reviewed customer data.",
            "Held-out loss alone does not establish improvement in customer-facing quality.",
        ],
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
