#!/usr/bin/env python3
"""Score source quality without promoting its evidence tier."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Iterable


SOURCE_TYPES = {
    "regulatory_filing": ("P0", 4, "fact_base"),
    "exchange_filing": ("P0", 4, "fact_base"),
    "company_disclosure": ("P0", 4, "fact_base"),
    "official_dataset": ("P0", 4, "fact_base"),
    "primary_paper": ("P0", 4, "fact_base"),
    "reliable_media": ("P1", 3, "supporting_fact"),
    "industry_association": ("P1", 3, "supporting_fact"),
    "independent_research": ("P1", 3, "supporting_fact"),
    "sell_side": ("P2", 2, "opinion_or_assumption"),
    "expert_interview": ("P2", 2, "opinion_or_assumption"),
    "social_media": ("P3", 1, "lead_only"),
    "self_media": ("P3", 1, "lead_only"),
    "aggregator": ("P3", 1, "lead_only"),
    "anonymous": ("P3", 0, "lead_only"),
}

DOMAIN_TYPES = {
    "sec.gov": "regulatory_filing",
    "cninfo.com.cn": "exchange_filing",
    "sse.com.cn": "exchange_filing",
    "szse.cn": "exchange_filing",
    "hkexnews.hk": "exchange_filing",
    "reuters.com": "reliable_media",
    "apnews.com": "reliable_media",
    "arxiv.org": "primary_paper",
    "doi.org": "primary_paper",
    "mp.weixin.qq.com": "self_media",
    "xueqiu.com": "social_media",
    "zhihu.com": "social_media",
    "reddit.com": "social_media",
    "twitter.com": "social_media",
    "x.com": "social_media",
}

DIRECTNESS = {"direct": 2, "excerpt": 1, "secondary": 0}
CORROBORATION = {"confirmed", "mixed", "none", "contradicted"}


def infer_source_type(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    for domain, source_type in DOMAIN_TYPES.items():
        if host == domain or host.endswith(f".{domain}"):
            return source_type
    return None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def freshness_score(published_at: str | None, as_of: date, evergreen: bool) -> tuple[int, str]:
    if evergreen:
        return 2, "evergreen"
    published = parse_date(published_at)
    if not published:
        return 0, "unknown"
    age = (as_of - published).days
    if age < 0:
        return 0, "future_date"
    if age <= 30:
        return 2, "current"
    if age <= 365:
        return 1, "recent"
    return 0, "stale"


def score_record(record: dict[str, Any], as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or date.today()
    source_type = record.get("source_type") or infer_source_type(record.get("url"))
    if source_type not in SOURCE_TYPES:
        return {
            **record,
            "source_type": source_type or "unclassified",
            "evidence_tier": "UNCLASSIFIED",
            "score": 0,
            "score_band": "lead_only",
            "verification_status": "unclassified",
            "use_limit": "classify_source_before_use",
            "error": "Unknown source type; provide source_type explicitly.",
        }

    directness = record.get("directness", "secondary")
    if directness not in DIRECTNESS:
        raise ValueError(f"Invalid directness: {directness}")
    corroboration = record.get("corroboration", "none")
    if corroboration not in CORROBORATION:
        raise ValueError(f"Invalid corroboration: {corroboration}")
    independent_sources = max(0, int(record.get("independent_sources", 0)))
    independence_score = 2 if independent_sources >= 3 else 1 if independent_sources >= 2 else 0
    fresh_score, freshness = freshness_score(record.get("published_at"), as_of, bool(record.get("evergreen", False)))
    tier, provenance_score, use_limit = SOURCE_TYPES[source_type]
    total = provenance_score + DIRECTNESS[directness] + fresh_score + independence_score
    band = "strong_candidate" if total >= 8 else "supporting" if total >= 5 else "lead_only"
    if corroboration == "contradicted":
        status = "contradicted"
    elif corroboration == "mixed":
        status = "disputed"
    elif corroboration == "confirmed" and independent_sources >= 2:
        status = "verified_candidate"
    else:
        status = "unverified"

    return {
        **record,
        "source_type": source_type,
        "evidence_tier": tier,
        "score": total,
        "score_band": band,
        "verification_status": status,
        "freshness": freshness,
        "score_components": {
            "provenance": provenance_score,
            "directness": DIRECTNESS[directness],
            "freshness": fresh_score,
            "independence": independence_score,
        },
        "use_limit": use_limit,
    }


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON on line {number}: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Score source quality while preserving P0-P3 evidence tiers.")
    parser.add_argument("--input", type=Path, help="JSONL input for batch scoring")
    parser.add_argument("--jsonl", action="store_true", help="Print one JSON object per line")
    parser.add_argument("--claim")
    parser.add_argument("--url")
    parser.add_argument("--source-type", choices=sorted(SOURCE_TYPES))
    parser.add_argument("--directness", choices=sorted(DIRECTNESS), default="secondary")
    parser.add_argument("--published-at")
    parser.add_argument("--independent-sources", type=int, default=0)
    parser.add_argument("--corroboration", choices=sorted(CORROBORATION), default="none")
    parser.add_argument("--evergreen", action="store_true")
    parser.add_argument("--as-of", help="Scoring date in YYYY-MM-DD")
    args = parser.parse_args()
    as_of = parse_date(args.as_of) or date.today()
    if args.input:
        records = list(read_jsonl(args.input))
    else:
        records = [{
            "claim": args.claim,
            "url": args.url,
            "source_type": args.source_type,
            "directness": args.directness,
            "published_at": args.published_at,
            "independent_sources": args.independent_sources,
            "corroboration": args.corroboration,
            "evergreen": args.evergreen,
        }]
    scored = [score_record(record, as_of) for record in records]
    if args.jsonl:
        for item in scored:
            print(json.dumps(item, ensure_ascii=False))
    else:
        print(json.dumps(scored[0] if len(scored) == 1 else scored, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
