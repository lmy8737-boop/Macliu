#!/usr/bin/env python3
"""Privacy-conscious metadata cache and content deduplication for web-harvest."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_DB = Path(os.environ.get("WEB_HARVEST_CACHE_DB", "~/.cache/web-harvest/harvest.sqlite3")).expanduser()
TTL_SECONDS = {
    "t0": 10 * 60,
    "news": 6 * 60 * 60,
    "page": 24 * 60 * 60,
    "query": 6 * 60 * 60,
    "static": 3650 * 24 * 60 * 60,
}
DROP_QUERY_KEYS = {"scene", "spm", "fbclid", "gclid", "share_token"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Only absolute http(s) URLs can be cached")
    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    port = parts.port
    netloc = host if not port or (scheme == "http" and port == 80) or (scheme == "https" and port == 443) else f"{host}:{port}"
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered.startswith("share_") or lowered in DROP_QUERY_KEYS:
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items))
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def query_hash(query: str) -> tuple[str, str]:
    normalized = normalize_text(query).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest(), normalized


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            canonical_url TEXT NOT NULL UNIQUE,
            original_url TEXT NOT NULL,
            title TEXT,
            published_at TEXT,
            fetched_at TEXT NOT NULL,
            content_hash TEXT,
            body TEXT,
            source_tier TEXT,
            obsidian_path TEXT,
            tool TEXT,
            kind TEXT NOT NULL DEFAULT 'page',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            authenticated INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
        CREATE TABLE IF NOT EXISTS queries (
            query_hash TEXT PRIMARY KEY,
            normalized_query TEXT NOT NULL,
            executed_at TEXT NOT NULL,
            route TEXT,
            kind TEXT NOT NULL DEFAULT 'query',
            result_json TEXT
        );
        """
    )
    return connection


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def is_fresh(timestamp: str, kind: str, max_age: int | None = None) -> bool:
    ttl = max_age if max_age is not None else TTL_SECONDS.get(kind, TTL_SECONDS["page"])
    saved = datetime.fromisoformat(timestamp)
    if saved.tzinfo is None:
        saved = saved.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - saved <= timedelta(seconds=ttl)


def put_document(connection: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    if args.authenticated and not args.allow_private_metadata:
        return {"status": "skipped", "reason": "authenticated content is not cached without explicit metadata permission"}
    canonical = normalize_url(args.url)
    text = args.content_file.read_text(encoding="utf-8") if args.content_file else ""
    digest = content_hash(text) if text else None
    duplicate = None
    if digest:
        duplicate = connection.execute(
            "SELECT canonical_url, title, obsidian_path FROM documents WHERE content_hash = ? AND canonical_url != ? LIMIT 1",
            (digest, canonical),
        ).fetchone()
    body = text if args.store_body and not args.authenticated else None
    metadata = json.loads(args.metadata_json) if args.metadata_json else {}
    fetched_at = args.fetched_at or now_iso()
    connection.execute(
        """
        INSERT INTO documents (
            canonical_url, original_url, title, published_at, fetched_at, content_hash, body,
            source_tier, obsidian_path, tool, kind, metadata_json, authenticated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(canonical_url) DO UPDATE SET
            original_url=excluded.original_url,
            title=COALESCE(excluded.title, documents.title),
            published_at=COALESCE(excluded.published_at, documents.published_at),
            fetched_at=excluded.fetched_at,
            content_hash=COALESCE(excluded.content_hash, documents.content_hash),
            body=COALESCE(excluded.body, documents.body),
            source_tier=COALESCE(excluded.source_tier, documents.source_tier),
            obsidian_path=COALESCE(excluded.obsidian_path, documents.obsidian_path),
            tool=COALESCE(excluded.tool, documents.tool),
            kind=excluded.kind,
            metadata_json=excluded.metadata_json,
            authenticated=excluded.authenticated
        """,
        (
            canonical, args.url, args.title, args.published_at, fetched_at, digest, body,
            args.source_tier, args.obsidian_path, args.tool, args.kind,
            json.dumps(metadata, ensure_ascii=False), int(args.authenticated),
        ),
    )
    connection.commit()
    return {
        "status": "stored",
        "canonical_url": canonical,
        "content_hash": digest,
        "body_stored": body is not None,
        "duplicate_content_of": row_dict(duplicate),
    }


def lookup_url(connection: sqlite3.Connection, url: str, max_age: int | None) -> dict[str, Any]:
    canonical = normalize_url(url)
    row = connection.execute("SELECT * FROM documents WHERE canonical_url = ?", (canonical,)).fetchone()
    if not row:
        return {"hit": False, "canonical_url": canonical}
    item = row_dict(row)
    item.pop("body", None)
    return {"hit": True, "fresh": is_fresh(item["fetched_at"], item["kind"], max_age), "document": item}


def lookup_content(connection: sqlite3.Connection, path: Path) -> dict[str, Any]:
    digest = content_hash(path.read_text(encoding="utf-8"))
    rows = connection.execute(
        "SELECT canonical_url, title, fetched_at, obsidian_path FROM documents WHERE content_hash = ?",
        (digest,),
    ).fetchall()
    return {"hit": bool(rows), "content_hash": digest, "matches": [row_dict(row) for row in rows]}


def put_query(connection: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    if args.sensitive:
        return {"status": "skipped", "reason": "sensitive query was not cached"}
    digest, normalized = query_hash(args.query)
    result_json = args.result_file.read_text(encoding="utf-8") if args.result_file else None
    connection.execute(
        """
        INSERT INTO queries (query_hash, normalized_query, executed_at, route, kind, result_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(query_hash) DO UPDATE SET
            executed_at=excluded.executed_at,
            route=excluded.route,
            kind=excluded.kind,
            result_json=COALESCE(excluded.result_json, queries.result_json)
        """,
        (digest, normalized, args.executed_at or now_iso(), args.route, args.kind, result_json),
    )
    connection.commit()
    return {"status": "stored", "query_hash": digest, "result_stored": result_json is not None}


def lookup_query(connection: sqlite3.Connection, query: str, kind: str, max_age: int | None) -> dict[str, Any]:
    digest, _ = query_hash(query)
    row = connection.execute("SELECT * FROM queries WHERE query_hash = ?", (digest,)).fetchone()
    if not row:
        return {"hit": False, "query_hash": digest}
    item = row_dict(row)
    effective_kind = item["kind"] or kind
    return {"hit": True, "fresh": is_fresh(item["executed_at"], effective_kind, max_age), "query": item}


def stats(connection: sqlite3.Connection) -> dict[str, Any]:
    documents = connection.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"]
    queries = connection.execute("SELECT COUNT(*) AS count FROM queries").fetchone()["count"]
    bodies = connection.execute("SELECT COUNT(*) AS count FROM documents WHERE body IS NOT NULL").fetchone()["count"]
    duplicates = connection.execute(
        "SELECT COUNT(*) AS count FROM (SELECT content_hash FROM documents WHERE content_hash IS NOT NULL GROUP BY content_hash HAVING COUNT(*) > 1)"
    ).fetchone()["count"]
    return {"documents": documents, "queries": queries, "stored_bodies": bodies, "duplicate_hash_groups": duplicates}


def prune(connection: sqlite3.Connection, days: int) -> dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()
    cursor = connection.execute("DELETE FROM queries WHERE executed_at < ?", (cutoff,))
    connection.commit()
    return {"status": "pruned", "queries_deleted": cursor.rowcount, "cutoff": cutoff}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="web-harvest metadata cache and content deduplication")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init")
    subparsers.add_parser("stats")

    lookup_url_parser = subparsers.add_parser("lookup-url")
    lookup_url_parser.add_argument("url")
    lookup_url_parser.add_argument("--max-age", type=int, help="Maximum age in seconds")

    lookup_content_parser = subparsers.add_parser("lookup-content")
    lookup_content_parser.add_argument("--content-file", type=Path, required=True)

    put_document_parser = subparsers.add_parser("put-document")
    put_document_parser.add_argument("url")
    put_document_parser.add_argument("--title")
    put_document_parser.add_argument("--published-at")
    put_document_parser.add_argument("--fetched-at")
    put_document_parser.add_argument("--content-file", type=Path)
    put_document_parser.add_argument("--store-body", action="store_true")
    put_document_parser.add_argument("--source-tier")
    put_document_parser.add_argument("--obsidian-path")
    put_document_parser.add_argument("--tool")
    put_document_parser.add_argument("--kind", choices=sorted(TTL_SECONDS), default="page")
    put_document_parser.add_argument("--metadata-json")
    put_document_parser.add_argument("--authenticated", action="store_true")
    put_document_parser.add_argument("--allow-private-metadata", action="store_true")

    lookup_query_parser = subparsers.add_parser("lookup-query")
    lookup_query_parser.add_argument("query")
    lookup_query_parser.add_argument("--kind", choices=sorted(TTL_SECONDS), default="query")
    lookup_query_parser.add_argument("--max-age", type=int)

    put_query_parser = subparsers.add_parser("put-query")
    put_query_parser.add_argument("query")
    put_query_parser.add_argument("--route")
    put_query_parser.add_argument("--kind", choices=sorted(TTL_SECONDS), default="query")
    put_query_parser.add_argument("--executed-at")
    put_query_parser.add_argument("--result-file", type=Path)
    put_query_parser.add_argument("--sensitive", action="store_true")

    prune_parser = subparsers.add_parser("prune")
    prune_parser.add_argument("--older-than-days", type=int, default=30)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    connection = connect(args.db.expanduser())
    try:
        if args.command == "init":
            result = {"status": "initialized", "db": str(args.db.expanduser())}
        elif args.command == "stats":
            result = stats(connection)
        elif args.command == "lookup-url":
            result = lookup_url(connection, args.url, args.max_age)
        elif args.command == "lookup-content":
            result = lookup_content(connection, args.content_file)
        elif args.command == "put-document":
            result = put_document(connection, args)
        elif args.command == "lookup-query":
            result = lookup_query(connection, args.query, args.kind, args.max_age)
        elif args.command == "put-query":
            result = put_query(connection, args)
        elif args.command == "prune":
            result = prune(connection, args.older_than_days)
        else:
            raise RuntimeError(f"Unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
