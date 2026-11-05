from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


WEB_HARVEST = Path(__file__).resolve().parents[1]
SKILLS = Path(os.environ.get("SKILLS_DIR", WEB_HARVEST.parent))
if not (SKILLS / "anysearch/scripts/anysearch_cli.py").is_file():
    raise unittest.SkipTest("AnySearch 未安装；用 SKILLS_DIR 指向其所在的 skills 目录")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    original_isfile = os.path.isfile
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(
            os.path,
            "isfile",
            side_effect=lambda candidate: False
            if str(candidate).endswith(".env")
            else original_isfile(candidate),
        ),
    ):
        spec.loader.exec_module(module)
    return module


anysearch_cli = load_module(
    "anysearch_cli_response_contract",
    SKILLS / "anysearch/scripts/anysearch_cli.py",
)
doctor = load_module(
    "web_harvest_doctor_response_contract",
    WEB_HARVEST / "scripts/doctor.py",
)


class FakeResponse:
    def __init__(self, status_code: int, body=None, *, text="", json_error=None):
        self.status_code = status_code
        self._body = body
        self.text = text
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._body


class ResponseContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request_guard = patch.object(
            anysearch_cli.requests,
            "request",
            side_effect=AssertionError("network must not be used by contract tests"),
        )
        self.subprocess_guard = patch.object(
            doctor.subprocess,
            "run",
            side_effect=AssertionError("subprocess probes must not run in contract tests"),
        )
        self.request_guard.start()
        self.subprocess_guard.start()
        self.addCleanup(self.request_guard.stop)
        self.addCleanup(self.subprocess_guard.stop)

    def call_rest(self, response):
        with patch.object(anysearch_cli.requests, "request", return_value=response) as request:
            result = anysearch_cli._call_rest(
                "POST", "/v1/search", "test-key", payload={"query": "OpenAI"}
            )
        return result, request

    def test_import_isolates_dotenv_discovery(self) -> None:
        self.assertEqual(anysearch_cli.API_BASE_URL, "https://api.anysearch.com")
        self.assertNotIn("Authorization", anysearch_cli._build_headers(""))

    def test_rest_rejects_http_error(self) -> None:
        response = FakeResponse(503, {"code": 0, "message": "upstream unavailable", "request_id": "req-1"})
        with patch.object(anysearch_cli.requests, "request", return_value=response):
            with self.assertRaisesRegex(anysearch_cli.ApiError, "upstream unavailable") as caught:
                anysearch_cli._call_rest("POST", "/v1/search", "")
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(caught.exception.request_id, "req-1")

    def test_rest_rejects_business_error_code(self) -> None:
        response = FakeResponse(200, {"code": 42901, "message": "quota exhausted", "request_id": "req-2"})
        with patch.object(anysearch_cli.requests, "request", return_value=response):
            with self.assertRaisesRegex(anysearch_cli.ApiError, "quota exhausted") as caught:
                anysearch_cli._call_rest("POST", "/v1/search", "")
        self.assertEqual(caught.exception.status, 200)
        self.assertEqual(caught.exception.request_id, "req-2")

    def test_rest_rejects_bad_json_and_malformed_envelope(self) -> None:
        cases = [
            (FakeResponse(502, text="<html>", json_error=ValueError("bad json")), "Invalid JSON response"),
            (FakeResponse(200, []), "Invalid API response"),
        ]
        for response, message in cases:
            with self.subTest(message=message), patch.object(
                anysearch_cli.requests, "request", return_value=response
            ):
                with self.assertRaisesRegex(anysearch_cli.ApiError, message):
                    anysearch_cli._call_rest("POST", "/v1/search", "")

    def test_rest_empty_successful_results_are_not_errors(self) -> None:
        envelope, request = self.call_rest(
            FakeResponse(200, {"code": 0, "data": {"results": [], "metadata": {}}})
        )
        self.assertEqual(anysearch_cli._format_search_response(envelope), "No relevant results found.")
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(request.call_args.args[0], "POST")
        self.assertTrue(request.call_args.args[1].endswith("/v1/search"))

    def test_rest_formats_valid_results(self) -> None:
        envelope, _ = self.call_rest(
            FakeResponse(
                200,
                {
                    "code": 0,
                    "data": {
                        "results": [{"title": "Example", "url": "https://example.com", "content": "snippet"}],
                        "metadata": {"total_results": 1, "search_time_ms": 12},
                    },
                },
            )
        )
        rendered = anysearch_cli._format_search_response(envelope)
        self.assertIn("## Search Results (1 results, 12ms)", rendered)
        self.assertIn("https://example.com", rendered)

    def test_doctor_classifies_empty_and_error_results(self) -> None:
        self.assertEqual(
            doctor.validate_anysearch_probe(0, "No relevant results found.", ""),
            ("empty", "no_relevant_results"),
        )
        self.assertEqual(
            doctor.validate_anysearch_probe(0, "No relevant results found.", "warning"),
            ("error", "unexpected_stderr"),
        )
        self.assertEqual(
            doctor.validate_anysearch_probe(0, "## Search Results (1 results, 100ms)\nError: backend unavailable", ""),
            ("error", "error_text_result"),
        )
        self.assertEqual(
            doctor.validate_anysearch_probe(0, "## Search Results (1 results, 100ms)\n- Example: https://example.com", ""),
            ("ok", "probe_ok"),
        )

    def test_doctor_reports_zero_healthy_agent_reach_channels(self) -> None:
        self.assertEqual(
            doctor.validate_agent_reach_channels(
                {"exa": {"status": "warn"}, "youtube": {"status": "off"}, "github": {"status": "error"}}
            ),
            ("empty", "no_healthy_channel", {"exa": "warn", "youtube": "off", "github": "error"}),
        )


if __name__ == "__main__":
    unittest.main()
