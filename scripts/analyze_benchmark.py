"""Annotate a saved benchmark; never modify raw case measurements."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.benchmark_analysis import analyze_run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    report['provider_observations'] = {label: analyze_run(run) for label, run in report['runs'].items()}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['provider_observations'], ensure_ascii=False, indent=2))
