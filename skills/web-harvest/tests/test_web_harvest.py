from __future__ import annotations

from argparse import Namespace
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cache  # noqa: E402
import route_regression  # noqa: E402
import source_quality  # noqa: E402


class RouteRegressionTests(unittest.TestCase):
    def test_all_route_cases(self) -> None:
        report = route_regression.run(ROOT / "evals" / "routing_cases.json")
        self.assertTrue(report["success"], report["results"])


class SourceQualityTests(unittest.TestCase):
    def test_primary_source_scores_high_without_changing_tier(self) -> None:
        result = source_quality.score_record(
            {
                "url": "https://www.sec.gov/Archives/example",
                "directness": "direct",
                "published_at": "2026-07-01",
                "independent_sources": 2,
                "corroboration": "confirmed",
            },
            as_of=date(2026, 7, 5),
        )
        self.assertEqual(result["evidence_tier"], "P0")
        self.assertEqual(result["score"], 9)
        self.assertEqual(result["verification_status"], "verified_candidate")

    def test_social_source_never_promotes_tier(self) -> None:
        result = source_quality.score_record(
            {
                "url": "https://mp.weixin.qq.com/s/example",
                "directness": "direct",
                "published_at": "2026-07-05",
                "independent_sources": 3,
                "corroboration": "confirmed",
            },
            as_of=date(2026, 7, 5),
        )
        self.assertEqual(result["evidence_tier"], "P3")
        self.assertEqual(result["use_limit"], "lead_only")

    def test_unknown_domain_stays_unclassified(self) -> None:
        result = source_quality.score_record({"url": "https://unknown.example/item"})
        self.assertEqual(result["evidence_tier"], "UNCLASSIFIED")


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cache.sqlite3"
        self.connection = cache.connect(self.db_path)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def document_args(self, url: str, content_file: Path, **overrides: object) -> Namespace:
        values = {
            "url": url,
            "title": "Example",
            "published_at": None,
            "fetched_at": None,
            "content_file": content_file,
            "store_body": False,
            "source_tier": "P1",
            "obsidian_path": None,
            "tool": "test",
            "kind": "static",
            "metadata_json": None,
            "authenticated": False,
            "allow_private_metadata": False,
        }
        values.update(overrides)
        return Namespace(**values)

    def test_url_normalization_removes_tracking(self) -> None:
        normalized = cache.normalize_url("HTTPS://Example.com:443/a/?utm_source=x&b=2&a=1#top")
        self.assertEqual(normalized, "https://example.com/a?a=1&b=2")

    def test_content_hash_detects_cross_url_duplicate_without_body_storage(self) -> None:
        content = Path(self.temp_dir.name) / "article.md"
        content.write_text("same   article\ncontent", encoding="utf-8")
        first = cache.put_document(self.connection, self.document_args("https://example.com/a", content))
        second = cache.put_document(self.connection, self.document_args("https://mirror.example/b", content))
        self.assertIsNone(first["duplicate_content_of"])
        self.assertEqual(second["duplicate_content_of"]["canonical_url"], "https://example.com/a")
        self.assertFalse(second["body_stored"])

    def test_authenticated_content_is_skipped_by_default(self) -> None:
        content = Path(self.temp_dir.name) / "private.md"
        content.write_text("private", encoding="utf-8")
        result = cache.put_document(
            self.connection,
            self.document_args("https://example.com/private", content, authenticated=True),
        )
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(cache.stats(self.connection)["documents"], 0)

    def test_query_cache_round_trip(self) -> None:
        args = Namespace(
            query="Latest HBM4 News",
            sensitive=False,
            result_file=None,
            executed_at=None,
            route="general_search",
            kind="news",
        )
        cache.put_query(self.connection, args)
        result = cache.lookup_query(self.connection, " latest  hbm4 news ", "news", None)
        self.assertTrue(result["hit"])
        self.assertTrue(result["fresh"])


if __name__ == "__main__":
    unittest.main()
