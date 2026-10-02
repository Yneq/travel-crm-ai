"""Build a small, fully synthetic MLX LoRA dataset for follow-up JSON output."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.followup_provider import GeneratedFollowUp, LocalFollowUpProvider
from services.mlx_provider import build_mlx_followup_instruction


SCENARIOS = {
    "task_due": (
        "待辦即將到期：{place}資料核對",
        "顧問待辦將在 24 小時內到期",
        "確認負責人與最新進度",
    ),
    "payment_follow_up": (
        "待付款訂單：SYN-{number:03d}",
        "付款期限接近，尚待人工確認最新狀態",
        "核對訂單與付款紀錄後再決定是否聯絡",
    ),
    "trip_countdown": (
        "出發前確認：{place}旅程",
        "行程即將出發，文件與版本需要再次核對",
        "確認文件、付款與最後行程版本",
    ),
}
PLACES = ("東京", "京都", "大阪", "台北", "高雄", "首爾", "新加坡")


def build_records() -> dict[str, list[dict]]:
    records = {"train": [], "valid": [], "test": []}
    provider = LocalFollowUpProvider()
    prompts: set[str] = set()
    for scenario_index, (reminder_type, (title, reason, action)) in enumerate(SCENARIOS.items()):
        for index in range(28):
            serial = scenario_index * 28 + index
            split = "train" if index < 20 else "valid" if index < 24 else "test"
            context = {
                "member": {
                    "name": f"合成旅客{serial:03d}", "tier": ("standard", "premium", "vip")[index % 3],
                    "locale": "zh-TW", "email": f"synthetic-{serial}@example.invalid",
                    "phone": "0000000000",
                },
                "reminder": {
                    "type": reminder_type,
                    "title": title.format(place=PLACES[index % len(PLACES)], number=serial),
                    "reason": reason,
                    "recommended_action": action,
                    "severity": "high" if index % 3 == 0 else "normal",
                },
            }
            prompt = build_mlx_followup_instruction(context)
            assert "@example.invalid" not in prompt and "0000000000" not in prompt
            assert prompt not in prompts, "Duplicate prompt across splits"
            prompts.add(prompt)
            answer = GeneratedFollowUp.model_validate(provider.generate_followup(context))
            assert answer.requires_human_review is True
            records[split].append({"messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": json.dumps(
                    answer.model_dump(), ensure_ascii=False, separators=(",", ":")
                )},
            ]})
    return records


def write_dataset(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    records = build_records()
    manifest = {
        "task": "synthetic_followup_json",
        "source": "Synthetic reminder templates labeled by LocalFollowUpProvider",
        "purpose": "MLX LoRA pipeline smoke test, not evidence of customer-task improvement",
        "eval_fixture_overlap": "No prompts copied from evals/fixtures.json",
        "splits": {},
    }
    for split, rows in records.items():
        data = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                       for row in rows)
        (output / f"{split}.jsonl").write_text(data, encoding="utf-8")
        manifest["splits"][split] = {
            "examples": len(rows),
            "sha256": hashlib.sha256(data.encode("utf-8")).hexdigest(),
        }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "finetune" / "followup" / "data")
    args = parser.parse_args()
    print(json.dumps(write_dataset(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
