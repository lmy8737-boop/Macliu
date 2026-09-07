#!/usr/bin/env python3
"""Run deterministic route policy regression cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from route import classify, load_policy  # noqa: E402


DEFAULT_CASES = ROOT / "evals" / "routing_cases.json"


def run(cases_path: Path) -> dict[str, object]:
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    policy = load_policy()
    results = []
    for case in payload["evals"]:
        actual = classify(case["prompt"], policy)
        passed = actual["route_id"] == case["expected_route"] and actual["primary"] == case["expected_primary"]
        results.append({
            "id": case["id"],
            "passed": passed,
            "prompt": case["prompt"],
            "expected_route": case["expected_route"],
            "actual_route": actual["route_id"],
            "expected_primary": case["expected_primary"],
            "actual_primary": actual["primary"],
        })
    passed_count = sum(1 for item in results if item["passed"])
    return {"passed": passed_count, "total": len(results), "success": passed_count == len(results), "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run web-harvest route regression tests.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run(args.cases)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["results"]:
            if not item["passed"]:
                print(f"FAIL {item['id']}: expected {item['expected_route']}/{item['expected_primary']}, got {item['actual_route']}/{item['actual_primary']}")
        print(f"route regression: {report['passed']}/{report['total']} passed")
    raise SystemExit(0 if report["success"] else 1)


if __name__ == "__main__":
    main()
