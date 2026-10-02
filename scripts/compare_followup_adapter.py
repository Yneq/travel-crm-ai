"""Compare an MLX follow-up adapter with its base model on held-out synthetic cases."""

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ai_evaluation import _latency_summary, _usage, contains_risky_claim
from services.followup_provider import GeneratedFollowUp
from services.mlx_provider import DEFAULT_MLX_MODEL, MlxFollowUpProvider


def load_records(path: Path) -> list[dict]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not records:
        raise ValueError(f"No test records in {path}")
    for row in records:
        if [message.get("role") for message in row.get("messages", [])] != ["user", "assistant"]:
            raise ValueError("Expected two-message chat records: user, assistant")
        GeneratedFollowUp.model_validate_json(row["messages"][1]["content"])
    return records


def evaluate_records(records: list[dict], provider: MlxFollowUpProvider) -> dict:
    results = []
    for index, row in enumerate(records):
        prompt = row["messages"][0]["content"]
        expected = GeneratedFollowUp.model_validate_json(row["messages"][1]["content"])
        provider.last_usage = None
        started = time.perf_counter()
        try:
            actual = GeneratedFollowUp.model_validate(provider.generate_json(prompt))
            results.append({
                "case": index + 1,
                "schema_valid": True,
                "guardrail_pass": actual.requires_human_review is True,
                "privacy_pass": "@example.invalid" not in actual.model_dump_json()
                                and "0000000000" not in actual.model_dump_json(),
                "claim_safety_pass": not contains_risky_claim(actual.model_dump()),
                "exact_label_match": actual == expected,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "token_usage": _usage(provider),
                "error": None,
            })
        except Exception as exc:
            results.append({
                "case": index + 1,
                "schema_valid": False, "guardrail_pass": False,
                "privacy_pass": False, "claim_safety_pass": False,
                "exact_label_match": False,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "token_usage": _usage(provider),
                "error": f"{type(exc).__name__}: {exc}",
            })
    count = len(results)
    dimensions = ("schema_valid", "guardrail_pass", "privacy_pass",
                  "claim_safety_pass", "exact_label_match")
    return {
        "model": provider.model_id,
        "adapter_path": provider.adapter_path,
        "case_count": count,
        "metrics": {key: round(sum(row[key] for row in results) / count, 4)
                    for key in dimensions},
        "latency": _latency_summary([row["latency_ms"] for row in results]),
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MLX_MODEL)
    parser.add_argument("--adapter-path", type=Path, required=True)
    parser.add_argument("--test-data", type=Path,
                        default=ROOT / "finetune/followup/data/test.jsonl")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "output/followup-adapter-comparison.json")
    args = parser.parse_args()
    if not (args.adapter_path / "adapters.safetensors").is_file():
        parser.error(f"No trained adapter at {args.adapter_path / 'adapters.safetensors'}")
    records = load_records(args.test_data)
    base = evaluate_records(records, MlxFollowUpProvider(args.model))
    adapted = evaluate_records(records, MlxFollowUpProvider(
        args.model, adapter_path=str(args.adapter_path.resolve())))
    report = {
        "task": "synthetic_followup_json",
        "test_data": str(args.test_data),
        "base": base,
        "adapted": adapted,
        "limitations": [
            "Labels come from the deterministic local provider, not human review.",
            "Exact label match is a synthetic-task metric, not customer-facing quality.",
            "This small held-out set does not establish production accuracy or throughput.",
            "Token counts are recorded only when reported by MLX; cost is not estimated.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
