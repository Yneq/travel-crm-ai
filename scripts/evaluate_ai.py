import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from services.ai_evaluation import load_fixtures, run_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description="Run VoyageOps fixed AI regression cases")
    parser.add_argument("--provider", choices=("local", "gemini"), default="local")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "evals" / "fixtures.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-live-api",
        action="store_true",
        help="Required with --provider gemini because it makes billable/external requests",
    )
    args = parser.parse_args()
    if args.provider == "gemini" and not args.allow_live_api:
        parser.error("--provider gemini requires --allow-live-api")

    report = run_evaluation(load_fixtures(args.fixtures), args.provider)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["overall"]["passed_count"] == report["overall"]["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
