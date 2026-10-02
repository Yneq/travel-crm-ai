import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from services.ai_evaluation import load_fixtures, run_benchmark, run_evaluation
from services.benchmark_provider import BenchmarkTarget


def parse_target(value: str) -> BenchmarkTarget:
    provider, separator, model = value.partition(":")
    if provider not in ("local", "gemini", "mlx") or (separator and not model):
        raise argparse.ArgumentTypeError("Target must be local, gemini[:MODEL], or mlx[:MODEL]")
    if provider == "local" and separator:
        raise argparse.ArgumentTypeError("The local target has no model")
    return BenchmarkTarget(provider, model if separator else None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run VoyageOps fixed AI regression cases")
    parser.add_argument("--provider", choices=("local", "gemini", "mlx"), default="local")
    parser.add_argument("--model", help="Model for a single Gemini or MLX run")
    parser.add_argument("--target", action="append", type=parse_target,
                        help="Repeat for comparison, e.g. local --target gemini:MODEL")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "evals" / "fixtures.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-live-api",
        action="store_true",
        help="Required with --provider gemini because it makes billable/external requests",
    )
    args = parser.parse_args()
    if args.model and args.provider == "local":
        parser.error("--model requires --provider gemini or mlx")
    if args.target and (args.provider != "local" or args.model):
        parser.error("Use --target on its own for multi-model comparisons")
    targets = args.target or [BenchmarkTarget(args.provider, args.model)]
    if any(target.provider == "gemini" for target in targets) and not args.allow_live_api:
        parser.error("Gemini targets require --allow-live-api")

    fixtures = load_fixtures(args.fixtures)
    try:
        report = (run_benchmark(fixtures, targets) if args.target else
                  run_evaluation(fixtures, args.provider, args.model))
    except ValueError as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    runs = report["runs"].values() if args.target else [report]
    return 0 if all(run["overall"]["passed_count"] == run["overall"]["case_count"]
                    for run in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
