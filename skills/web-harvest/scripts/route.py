#!/usr/bin/env python3
"""Deterministic routing helper for web-harvest policy audits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "references" / "route-policy.json"


def _matches(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def route_matches(route: dict[str, Any], prompt: str) -> bool:
    if any(_matches(pattern, prompt) for pattern in route.get("exclude_patterns", [])):
        return False
    any_patterns = route.get("any_patterns", [])
    if any_patterns and not any(_matches(pattern, prompt) for pattern in any_patterns):
        return False
    for group in route.get("all_groups", []):
        if not any(_matches(pattern, prompt) for pattern in group):
            return False
    return bool(any_patterns or route.get("all_groups"))


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def classify(prompt: str, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    routes = sorted(policy["routes"], key=lambda item: item.get("priority", 0), reverse=True)
    for route in routes:
        if route_matches(route, prompt):
            return {
                "route_id": route["id"],
                "primary": route["primary"],
                "supplements": route.get("supplements", []),
                "reason": route["reason"],
            }
    raise RuntimeError(f"No route matched and default route is invalid: {policy.get('default_route')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify a prompt using web-harvest route policy.")
    parser.add_argument("prompt", help="User request to classify")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = classify(args.prompt, load_policy(args.policy))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"route: {result['route_id']}")
        print(f"primary: {result['primary']}")
        if result["supplements"]:
            print(f"supplements: {', '.join(result['supplements'])}")
        print(f"reason: {result['reason']}")


if __name__ == "__main__":
    main()
