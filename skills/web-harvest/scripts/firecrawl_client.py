#!/usr/bin/env python3
"""Thin HTTP wrapper for Firecrawl's cloud API — two capabilities not covered
elsewhere in web-harvest's stack: schema-driven structured extraction (scrape
with a JSON schema) and whole-site URL discovery (map).

Deliberately NOT the official firecrawl-cli/MCP server. That installer runs
`npx -y firecrawl-cli@latest init --all --browser` — a blind remote-script
execution — and its Scrape/Crawl/Search/Agent features mostly duplicate
Scrapling + AnySearch, which are already installed and working (see
2026-09-07 doctor.py fix). This wrapper only exposes the two genuinely
non-overlapping endpoints, called directly over HTTPS with an API key.

Requires FIRECRAWL_API_KEY in the environment. Never hardcode the key here,
never write it to any file this script controls. Get a key at
https://www.firecrawl.dev (free tier available) — that step is on the user,
not something this script can do.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

try:
    import requests
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: requests. Install with `pip install requests`.") from exc


API_BASE = "https://api.firecrawl.dev/v2"


def _api_key() -> str:
    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "FIRECRAWL_API_KEY not set. Get a free-tier key at https://www.firecrawl.dev, "
            "then export FIRECRAWL_API_KEY=... for this shell session (or the caller's env). "
            "This script does not persist keys anywhere."
        )
    return key


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}


def scrape_structured(url: str, schema: dict[str, Any], prompt: str | None = None,
                       only_main_content: bool = True) -> dict[str, Any]:
    """Schema-driven structured extraction. `schema` must be a JSON Schema object
    (type/properties/required). Returns the parsed `data.json` payload plus markdown."""
    body: dict[str, Any] = {
        "url": url,
        "formats": [{"type": "json", "schema": schema, **({"prompt": prompt} if prompt else {})}],
        "onlyMainContent": only_main_content,
    }
    resp = requests.post(f"{API_BASE}/scrape", headers=_headers(), json=body, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"Firecrawl scrape failed: {payload}")
    data = payload.get("data", {})
    return {"url": url, "json": data.get("json"), "markdown": data.get("markdown"),
            "metadata": data.get("metadata")}


def map_site(url: str, search: str | None = None, limit: int = 100,
             include_subdomains: bool = True) -> list[dict[str, Any]]:
    """List a site's indexed URLs. `search` sorts by relevance to a keyword
    (e.g. "pricing") instead of dumping every URL — use it for competitor
    page discovery before deciding what to scrape."""
    body: dict[str, Any] = {
        "url": url, "limit": limit, "includeSubdomains": include_subdomains,
    }
    if search:
        body["search"] = search
    resp = requests.post(f"{API_BASE}/map", headers=_headers(), json=body, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"Firecrawl map failed: {payload}")
    return payload.get("links", [])


def _cmd_scrape(args: argparse.Namespace) -> int:
    schema = json.loads(args.schema)
    result = scrape_structured(args.url, schema, args.prompt)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_map(args: argparse.Namespace) -> int:
    result = map_site(args.url, args.search, args.limit)
    print(json.dumps({"count": len(result), "links": result}, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Firecrawl cloud API thin client (scrape+map only)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scrape", help="Schema-driven structured extraction from one URL")
    p.add_argument("url")
    p.add_argument("--schema", required=True, help="JSON Schema as a string, e.g. "
                   '\'{"type":"object","properties":{"title":{"type":"string"}}}\'')
    p.add_argument("--prompt", default=None, help="Natural-language extraction instruction")
    p.set_defaults(func=_cmd_scrape)

    p = sub.add_parser("map", help="List a site's indexed URLs, optionally ranked by relevance")
    p.add_argument("url")
    p.add_argument("--search", default=None, help="Keyword to rank URLs by relevance, e.g. 'pricing'")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=_cmd_map)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
