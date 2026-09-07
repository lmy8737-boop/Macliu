from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


SKILLS = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


stock = load_module("phase1_stock_data", Path(__file__).with_name("stock_data_cli.py"))
anysearch = load_module(
    "phase1_anysearch", SKILLS / "anysearch" / "scripts" / "anysearch_cli.py"
)
doctor = load_module(
    "phase1_web_harvest_doctor", SKILLS / "web-harvest" / "scripts" / "doctor.py"
)


class FakeResponse:
    def __init__(self, payload=None, text="", http_error=None):
        self.payload = payload
        self.text = text or json.dumps(payload or {})
        self.http_error = http_error

    def raise_for_status(self):
        if self.http_error:
            raise self.http_error

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def quote(source, market, code, price, market_at="2026-09-04T15:00:00"):
    return {
        "source": source,
        "market": market,
        "code": code,
        "price": price,
        "market_at": market_at,
        "retrieved_at": "2026-09-04T07:00:01Z",
    }


class QuoteTests(unittest.TestCase):
    def test_primary_exception_uses_same_fallback_path(self):
        symbols = [stock.normalize_ticker("AAPL")]
        with mock.patch.object(stock, "tencent_quotes", side_effect=RuntimeError("primary down")), \
             mock.patch.object(stock, "yahoo_quotes", return_value={
                 "AAPL": quote("Yahoo", "us", "AAPL", 250.0)
             }):
            report, exit_code = stock.build_quote_report(symbols)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["quotes"]["AAPL"]["source"], "Yahoo")
        self.assertEqual(report["quotes"]["AAPL"]["status"], "ok")
        self.assertEqual(report["quotes"]["AAPL"]["reason_code"], "fallback_after_primary_error")

    def test_missing_key_field_and_empty_price_both_fallback(self):
        symbols = [stock.normalize_ticker("AAPL"), stock.normalize_ticker("MSFT")]
        primary = {
            "AAPL": quote("Tencent", "us", "AAPL", 250.0, market_at=None),
            "MSFT": quote("Tencent", "us", "MSFT", None),
        }
        fallback = {
            "AAPL": quote("Yahoo", "us", "AAPL", 251.0),
            "MSFT": quote("Yahoo", "us", "MSFT", 501.0),
        }
        with mock.patch.object(stock, "tencent_quotes", return_value=primary), \
             mock.patch.object(stock, "yahoo_quotes", return_value=fallback):
            report, exit_code = stock.build_quote_report(symbols)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["quotes"]["AAPL"]["reason_code"], "fallback_after_market_at_missing")
        self.assertEqual(report["quotes"]["MSFT"]["reason_code"], "fallback_after_price_missing")

    def test_mixed_success_failure_is_explicit(self):
        symbols = [stock.normalize_ticker("AAPL"), stock.normalize_ticker("MSFT")]
        with mock.patch.object(stock, "tencent_quotes", return_value={
                 "AAPL": quote("Tencent", "us", "AAPL", 250.0)
             }), mock.patch.object(stock, "yahoo_quotes", return_value={
                 "MSFT": quote("Yahoo", "us", "MSFT", None)
             }):
            report, exit_code = stock.build_quote_report(symbols)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["quotes"]["AAPL"]["status"], "ok")
        self.assertEqual(report["quotes"]["MSFT"]["status"], "error")
        self.assertEqual(report["as_of"], "2026-09-04T15:00:00")

    def test_all_failed_returns_nonzero(self):
        symbols = [stock.normalize_ticker("AAPL")]
        with mock.patch.object(stock, "tencent_quotes", return_value={}), \
             mock.patch.object(stock, "yahoo_quotes", return_value={}):
            report, exit_code = stock.build_quote_report(symbols)
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "error")
        self.assertIsNone(report["as_of"])


class HealthcheckTests(unittest.TestCase):
    @staticmethod
    def fail():
        raise RuntimeError("down")

    def test_all_failed_health_is_nonzero(self):
        checks = stock.run_health_checks([
            ("exception", self.fail, False),
            ("unexpected-empty", lambda: [], False),
        ])
        report, exit_code = stock.build_health_report(checks)
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["failed_count"], 2)
        self.assertEqual([item["status"] for item in checks], ["error", "empty"])
        with mock.patch.object(stock, "run_health_checks", return_value=checks), \
             mock.patch.object(stock, "print_json"):
            self.assertEqual(stock.cmd_healthcheck(mock.Mock(skip_slow=True)), 1)

    def test_legal_no_event_is_empty_but_acceptable(self):
        checks = stock.run_health_checks([("no-event", lambda: [], True)])
        report, exit_code = stock.build_health_report(checks)
        self.assertEqual(exit_code, 0)
        self.assertEqual(checks[0]["status"], "empty")
        self.assertEqual(checks[0]["reason_code"], "empty_allowed")
        self.assertTrue(report["ok"])


class AnySearchTests(unittest.TestCase):
    def test_http_error_is_explicit(self):
        response = FakeResponse(
            {"error": {"message": "denied"}},
            http_error=anysearch.requests.exceptions.HTTPError("403"),
        )
        with mock.patch.object(anysearch.requests, "post", return_value=response):
            with self.assertRaises(anysearch.AnySearchError):
                anysearch._call_api("search", {"query": "x"}, "")

    def test_json_rpc_error_and_mcp_is_error_fail(self):
        with self.assertRaises(anysearch.AnySearchError):
            anysearch._parse_mcp_response({"error": {"message": "rpc failed"}})
        with self.assertRaises(anysearch.AnySearchError):
            anysearch._parse_mcp_response({
                "result": {"isError": True, "content": [{"type": "text", "text": "tool failed"}]}
            })

    def test_malformed_and_empty_content_fail(self):
        for payload in (
            {"result": {}},
            {"result": {"content": []}},
            {"result": {"content": [{"type": "text", "text": ""}]}},
            {"result": {"content": ["bad"]}},
            {"result": {"content": [{"text": "missing type"}]}},
            {"result": {"content": [{"type": "text", "text": "## Search Results"}]}},
        ):
            with self.subTest(payload=payload), self.assertRaises(anysearch.AnySearchError):
                anysearch._parse_mcp_response(payload)

    def test_search_results_error_text_is_not_a_result(self):
        with self.assertRaises(anysearch.AnySearchError):
            anysearch._parse_mcp_response({
                "result": {"content": [{
                    "type": "text", "text": "## Search Results\n\n**Error:** backend unavailable"
                }]}
            })


class DoctorTests(unittest.TestCase):
    def test_anysearch_checks_exit_and_result_structure(self):
        valid = "## Search Results\n\n### 1. OpenAI\nhttps://openai.com/"
        self.assertEqual(doctor.validate_anysearch_probe(0, valid, "")[0], "ok")
        error_text = "## Search Results\n\nError: backend unavailable"
        self.assertEqual(doctor.validate_anysearch_probe(0, error_text, "")[0], "error")
        json_error = '## Search Results\n\n{"error":"backend unavailable"}'
        self.assertEqual(doctor.validate_anysearch_probe(0, json_error, "")[0], "error")
        self.assertEqual(doctor.validate_anysearch_probe(1, valid, "failed")[0], "error")

    def test_agent_reach_nonempty_dict_is_not_enough(self):
        status, reason, _ = doctor.validate_agent_reach_channels({
            "web": {"status": "error", "active_backend": None}
        })
        self.assertEqual((status, reason), ("empty", "no_healthy_channel"))
        malformed = doctor.validate_agent_reach_channels({"web": {"status": "ok"}})
        self.assertEqual(malformed[0], "error")


class KlineTests(unittest.TestCase):
    def test_weekly_request_rejects_daily_response_key(self):
        payload = {"data": {"sh600519": {
            "qfqday": [["2026-09-04", "1", "2", "3", "1", "10"]]
        }}}
        with mock.patch.object(stock.requests, "get", return_value=FakeResponse(payload)):
            with self.assertRaisesRegex(ValueError, "expected exact key='qfqweek'"):
                stock.tencent_akline("600519", count=1, ktype=102)

    def test_response_for_another_security_is_rejected(self):
        payload = {"data": {"sz000001": {
            "qfqday": [["2026-09-04", "1", "2", "3", "1", "10"]]
        }}}
        with mock.patch.object(stock.requests, "get", return_value=FakeResponse(payload)):
            with self.assertRaisesRegex(ValueError, "sh600519"):
                stock.tencent_akline("600519", count=1, ktype=9)

    def test_unconfirmed_minute_and_unknown_ktype_fail_before_request(self):
        with mock.patch.object(stock.requests, "get") as request:
            with self.assertRaisesRegex(ValueError, "not enabled"):
                stock.tencent_akline("600519", count=1, ktype=5)
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                stock.tencent_akline("600519", count=1, ktype=999)
        request.assert_not_called()

    def test_qfq_request_rejects_unadjusted_key(self):
        payload = {"data": {"sh600519": {
            "day": [["2026-09-04", "1", "2", "3", "1", "10"]]
        }}}
        with mock.patch.object(stock.requests, "get", return_value=FakeResponse(payload)):
            with self.assertRaisesRegex(ValueError, "expected exact key='qfqday'"):
                stock.tencent_akline("600519", count=1, ktype=9)


class CompatibilityTests(unittest.TestCase):
    def test_sec_metric_catalog_keeps_legacy_descriptions(self):
        facts = {"entityName": "Example", "facts": {"us-gaap": {
            "Revenues": {"label": "Revenue", "units": {"USD": []}},
            "Assets": {"label": "Assets", "units": {"USD": [], "shares": []}},
        }}}
        with mock.patch.object(stock.requests, "get", return_value=FakeResponse(facts)):
            report = stock.sec_xbrl("0000000000", None)
        self.assertEqual(report["total_metrics"], 2)
        self.assertEqual(report["available_metrics"][0]["name"], "Revenues")
        self.assertEqual(report["available_metrics"][0]["label"], "Revenue")
        self.assertIn("USD", report["available_metrics"][0]["units"])
        self.assertIn("available_metric_names", report)


class SecTests(unittest.TestCase):
    def test_preserves_periods_units_revisions_and_more_than_twenty(self):
        base = [{
            "start": f"2024-{(i % 9) + 1:02d}-01",
            "end": f"2024-{(i % 9) + 1:02d}-28",
            "val": i,
            "filed": "2025-01-01",
            "accn": f"accn-{i}",
            "form": "10-Q",
            "fy": 2024,
            "fp": "Q1",
            "frame": f"CY2024Q{i % 4 + 1}",
            "custom_source_field": "kept",
        } for i in range(21)]
        same_end = [
            {**base[0], "start": "2025-01-01", "end": "2025-06-30", "val": 60,
             "filed": "2025-07-20", "accn": "ytd-original", "fp": "Q2", "frame": None},
            {**base[0], "start": "2025-04-01", "end": "2025-06-30", "val": 35,
             "filed": "2025-07-20", "accn": "quarter", "fp": "Q2", "frame": "CY2025Q2"},
            {**base[0], "start": "2025-01-01", "end": "2025-06-30", "val": 61,
             "filed": "2025-08-01", "accn": "ytd-amended", "fp": "Q2", "frame": None},
        ]
        payload = {"entityName": "Example", "facts": {"us-gaap": {
            "Revenues": {"units": {"USD": base + same_end, "EUR": [{
                **base[0], "val": 99, "accn": "eur-entry"
            }]}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [
                {**same_end[0], "val": 5.0, "accn": "eps-ytd"},
                {**same_end[1], "val": 3.0, "accn": "eps-quarter"},
            ]}},
        }}}
        with mock.patch.object(stock.requests, "get", return_value=FakeResponse(payload)):
            result = stock.sec_xbrl("0000000001", ["Revenues", "EarningsPerShareDiluted"])

        revenue = result["metrics"]["Revenues"]
        self.assertGreater(len(revenue), 20)
        self.assertEqual({row["unit"] for row in revenue}, {"USD", "EUR"})
        self.assertEqual(len([row for row in revenue if row["end"] == "2025-06-30"]), 3)
        self.assertEqual(
            {row["accn"] for row in revenue if row["end"] == "2025-06-30"},
            {"ytd-original", "quarter", "ytd-amended"},
        )
        expected_fields = {
            "concept", "unit", "start", "end", "val", "filed", "accn",
            "form", "fy", "fp", "frame",
        }
        self.assertTrue(all(expected_fields <= row.keys() for row in revenue))
        self.assertTrue(all(row["custom_source_field"] == "kept" for row in revenue))
        self.assertFalse(result["metric_metadata"]["Revenues"]["truncated"])
        self.assertEqual(result["metric_metadata"]["Revenues"]["derivation"], "none")
        eps = result["metrics"]["EarningsPerShareDiluted"]
        self.assertEqual([row["val"] for row in eps], [5.0, 3.0])


if __name__ == "__main__":
    unittest.main()
