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
launcher = load_module("phase1_stock_data_launcher", Path(__file__).with_name("run_stock_data.py"))
doctor = load_module(
    "phase1_web_harvest_doctor", SKILLS / "web-harvest" / "scripts" / "doctor.py"
)
# AnySearch REST protocol contracts are owned by web-harvest/tests/test_response_contract.py.


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


def quote(
    source, market, code, price, market_at="2026-09-04T15:00:00",
    retrieved_at="2026-09-04T07:00:01Z", **metadata,
):
    payload = {
        "source": source,
        "market": market,
        "code": code,
        "price": price,
        "market_at": market_at,
        "retrieved_at": retrieved_at,
    }
    payload.update(metadata)
    return payload


def session(opened, closed, break_start=None, break_end=None):
    parse = lambda value: stock._parse_aware_datetime(value) if value else None
    return {
        "date": opened[:10], "open": parse(opened), "close": parse(closed),
        "break_start": parse(break_start), "break_end": parse(break_end),
    }


def bar(date, close=10.0):
    return {
        "date": date, "open": close - 0.5, "high": close + 1,
        "low": close - 1, "close": close, "volume": 100,
    }


class QuoteTests(unittest.TestCase):
    def test_primary_exception_uses_same_fallback_path(self):
        symbols = [stock.normalize_ticker("AAPL")]
        with mock.patch.object(stock, "yahoo_quotes", side_effect=RuntimeError("primary down")), \
             mock.patch.object(stock, "tencent_quotes", return_value={
                 "AAPL": quote("Tencent", "us", "AAPL", 250.0)
             }):
            report, exit_code = stock.build_quote_report(symbols)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["quotes"]["AAPL"]["source"], "Tencent")
        self.assertEqual(report["quotes"]["AAPL"]["status"], "ok")
        self.assertEqual(report["quotes"]["AAPL"]["reason_code"], "fallback_after_primary_error")
        self.assertEqual(report["quotes"]["AAPL"]["freshness_status"], "unknown")

    def test_missing_market_time_is_acquired_but_price_missing_falls_back(self):
        symbols = [stock.normalize_ticker("AAPL"), stock.normalize_ticker("MSFT")]
        primary = {
            "AAPL": quote("Yahoo", "us", "AAPL", 250.0, market_at=None),
            "MSFT": quote("Yahoo", "us", "MSFT", None),
        }
        fallback = {
            "AAPL": quote("Tencent", "us", "AAPL", 251.0),
            "MSFT": quote("Tencent", "us", "MSFT", 501.0),
        }
        with mock.patch.object(stock, "yahoo_quotes", return_value=primary), \
             mock.patch.object(stock, "tencent_quotes", return_value=fallback):
            report, exit_code = stock.build_quote_report(symbols)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["quotes"]["AAPL"]["reason_code"], "primary_ok")
        self.assertEqual(report["quotes"]["AAPL"]["acquisition_status"], "ok")
        self.assertEqual(report["quotes"]["AAPL"]["freshness_status"], "unknown")
        self.assertFalse(report["quotes"]["AAPL"]["t0_eligible"])
        self.assertEqual(report["quotes"]["MSFT"]["reason_code"], "fallback_after_price_missing")

    def test_mixed_success_failure_is_explicit(self):
        symbols = [stock.normalize_ticker("AAPL"), stock.normalize_ticker("MSFT")]
        with mock.patch.object(stock, "tencent_quotes", return_value={
                 "MSFT": quote("Tencent", "us", "MSFT", None)
             }), mock.patch.object(stock, "yahoo_quotes", return_value={
                 "AAPL": quote("Yahoo", "us", "AAPL", 250.0),
                 "MSFT": quote("Yahoo", "us", "MSFT", None),
             }):
            report, exit_code = stock.build_quote_report(symbols)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["quotes"]["AAPL"]["status"], "ok")
        self.assertEqual(report["quotes"]["MSFT"]["status"], "error")
        self.assertIsNone(report["as_of"])
        self.assertEqual(report["as_of_reason_code"], "no_certified_market_time")

    def test_all_failed_returns_nonzero(self):
        symbols = [stock.normalize_ticker("AAPL")]
        with mock.patch.object(stock, "tencent_quotes", return_value={}), \
             mock.patch.object(stock, "yahoo_quotes", return_value={}):
            report, exit_code = stock.build_quote_report(symbols)
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "error")
        self.assertIsNone(report["as_of"])

    def test_a_h_us_cross_timezone_intraday_freshness(self):
        cases = [
            ("cn", "Asia/Shanghai", "XSHG", "2026-09-07T10:00:00+08:00",
             "2026-09-07T02:05:00Z", "2026-09-07T01:30:00Z", "2026-09-07T07:00:00Z"),
            ("hk", "Asia/Hong_Kong", "XHKG", "2026-09-07T10:00:00+08:00",
             "2026-09-07T02:05:00Z", "2026-09-07T01:30:00Z", "2026-09-07T08:00:00Z"),
            ("us", "America/New_York", "XNYS", "2026-09-07T14:00:00Z",
             "2026-09-07T14:05:00Z", "2026-09-07T13:30:00Z", "2026-09-07T20:00:00Z"),
        ]
        for market, timezone, calendar, market_at, retrieved_at, opened, closed in cases:
            payload = quote(
                "source", market, "code", 10, market_at, retrieved_at,
                market_timezone=timezone, calendar_name=calendar,
            )
            with self.subTest(market=market), mock.patch.object(
                stock, "_market_calendar_sessions",
                return_value=([session(opened, closed)], "test_calendar"),
            ):
                result = stock._quote_freshness(payload)
            self.assertEqual(result["freshness_status"], "fresh")
            self.assertTrue(result["t0_eligible"])

    def test_latest_close_on_weekend_or_holiday_is_calendar_driven(self):
        payload = quote(
            "Tencent", "cn", "600519", 10, "2026-09-04T15:00:00+08:00",
            "2026-09-06T04:00:00Z", market_timezone="Asia/Shanghai",
            calendar_name="XSHG",
        )
        friday = session("2026-09-04T01:30:00Z", "2026-09-04T07:00:00Z")
        with mock.patch.object(
            stock, "_market_calendar_sessions", return_value=([friday], "test_calendar")
        ):
            result = stock._quote_freshness(payload)
        self.assertEqual(result["freshness_status"], "latest_close")
        self.assertEqual(result["freshness_reason_code"], "latest_completed_session")
        self.assertTrue(result["t0_eligible"])

    def test_pre_open_quote_cannot_be_fresh_after_open(self):
        trading = session("2026-09-07T01:30:00Z", "2026-09-07T07:00:00Z")
        payload = quote(
            "Tencent", "cn", "x", 1, "2026-09-07T09:29:00+08:00",
            "2026-09-07T01:31:00Z", market_timezone="Asia/Shanghai",
            calendar_name="XSHG",
        )
        with mock.patch.object(
            stock, "_market_calendar_sessions", return_value=([trading], "test_calendar")
        ):
            result = stock._quote_freshness(payload)
        self.assertEqual(result["freshness_status"], "unknown")
        self.assertEqual(result["freshness_reason_code"], "market_at_not_in_trading_session")
        self.assertFalse(result["t0_eligible"])

    def test_pre_close_quote_cannot_be_latest_completed_session(self):
        trading = session("2026-09-07T01:30:00Z", "2026-09-07T07:00:00Z")
        payload = quote(
            "Tencent", "cn", "x", 1, "2026-09-07T14:40:00+08:00",
            "2026-09-07T07:01:00Z", market_timezone="Asia/Shanghai",
            calendar_name="XSHG",
        )
        with mock.patch.object(
            stock, "_market_calendar_sessions", return_value=([trading], "test_calendar")
        ):
            result = stock._quote_freshness(payload)
        self.assertEqual(result["freshness_status"], "stale")
        self.assertEqual(result["freshness_reason_code"], "not_latest_completed_session")
        self.assertFalse(result["t0_eligible"])

    def test_pre_pause_quote_cannot_be_latest_market_pause(self):
        trading = session(
            "2026-09-07T01:30:00Z", "2026-09-07T07:00:00Z",
            "2026-09-07T03:30:00Z", "2026-09-07T05:00:00Z",
        )
        with mock.patch.object(
            stock, "_market_calendar_sessions", return_value=([trading], "test_calendar")
        ):
            before_pause = stock._quote_freshness(quote(
                "Tencent", "cn", "x", 1, "2026-09-07T11:10:00+08:00",
                "2026-09-07T03:31:00Z", market_timezone="Asia/Shanghai",
                calendar_name="XSHG",
            ))
            before_reopen = stock._quote_freshness(quote(
                "Tencent", "cn", "x", 1, "2026-09-07T12:59:00+08:00",
                "2026-09-07T05:01:00Z", market_timezone="Asia/Shanghai",
                calendar_name="XSHG",
            ))
        self.assertEqual(before_pause["freshness_status"], "stale")
        self.assertEqual(before_pause["freshness_reason_code"], "stale_during_market_pause")
        self.assertFalse(before_pause["t0_eligible"])
        self.assertEqual(before_reopen["freshness_status"], "stale")
        self.assertEqual(before_reopen["freshness_reason_code"], "stale_during_session")
        self.assertFalse(before_reopen["t0_eligible"])

    def test_exact_open_close_and_pause_boundaries_are_certified(self):
        trading = session(
            "2026-09-07T01:30:00Z", "2026-09-07T07:00:00Z",
            "2026-09-07T03:30:00Z", "2026-09-07T05:00:00Z",
        )
        cases = [
            ("2026-09-07T01:30:00Z", "2026-09-07T01:30:00Z", "fresh"),
            ("2026-09-07T03:30:00Z", "2026-09-07T03:30:00Z", "latest_close"),
            ("2026-09-07T05:00:00Z", "2026-09-07T05:00:00Z", "fresh"),
            ("2026-09-07T07:00:00Z", "2026-09-07T07:00:00Z", "latest_close"),
            ("2026-09-07T07:05:00Z", "2026-09-07T07:06:00Z", "latest_close"),
        ]
        with mock.patch.object(
            stock, "_market_calendar_sessions", return_value=([trading], "test_calendar")
        ):
            for market_at, retrieved_at, expected in cases:
                with self.subTest(market_at=market_at):
                    result = stock._quote_freshness(quote(
                        "source", "cn", "x", 1, market_at, retrieved_at,
                        market_timezone="Asia/Shanghai", calendar_name="XSHG",
                    ))
                    self.assertEqual(result["freshness_status"], expected)
                    self.assertTrue(result["t0_eligible"])

    def test_future_stale_invalid_and_non_trading_times_do_not_certify(self):
        trading = session("2026-09-07T01:30:00Z", "2026-09-07T07:00:00Z")
        payloads = [
            (quote("Tencent", "cn", "x", 1, "2026-09-07T10:10:01+08:00",
                   "2026-09-07T02:05:00Z", market_timezone="Asia/Shanghai",
                   calendar_name="XSHG"), "future"),
            (quote("Tencent", "cn", "x", 1, "2026-09-07T09:31:00+08:00",
                   "2026-09-07T03:00:00Z", market_timezone="Asia/Shanghai",
                   calendar_name="XSHG"), "stale"),
            (quote("Tencent", "cn", "x", 1, "invalid", "2026-09-07T03:00:00Z",
                   market_timezone="Asia/Shanghai", calendar_name="XSHG"), "unknown"),
            (quote("Tencent", "cn", "x", 1, "2026-09-06T12:00:00+08:00",
                   "2026-09-07T03:00:00Z", market_timezone="Asia/Shanghai",
                   calendar_name="XSHG"), "unknown"),
        ]
        with mock.patch.object(
            stock, "_market_calendar_sessions", return_value=([trading], "test_calendar")
        ):
            for payload, expected in payloads:
                with self.subTest(expected=expected, market_at=payload["market_at"]):
                    result = stock._quote_freshness(payload)
                    self.assertEqual(result["freshness_status"], expected)
                    self.assertFalse(result["t0_eligible"])

    def test_unknown_timezone_or_missing_calendar_library_is_not_t0(self):
        unknown_timezone = quote(
            "Tencent", "us", "AAPL", 10, "2026-09-07T10:00:00",
            "2026-09-07T14:05:00Z",
        )
        self.assertEqual(
            stock._quote_freshness(unknown_timezone)["freshness_reason_code"],
            "market_timezone_unknown",
        )
        known_clock = quote(
            "Yahoo", "us", "AAPL", 10, "2026-09-07T14:00:00Z",
            "2026-09-07T14:05:00Z", market_timezone="America/New_York",
            calendar_name="XNYS",
        )
        with mock.patch.object(
            stock, "_market_calendar_sessions",
            return_value=(None, "calendar_library_unavailable"),
        ):
            result = stock._quote_freshness(known_clock)
        self.assertEqual(result["freshness_status"], "unknown")
        self.assertEqual(result["calendar_status"], "calendar_library_unavailable")
        self.assertFalse(result["t0_eligible"])

    def test_mixed_markets_never_share_top_level_as_of(self):
        symbols = [stock.normalize_ticker("600519"), stock.normalize_ticker("00700")]
        primary = {
            "600519": quote("Tencent", "cn", "600519", 10,
                            "2026-09-07T10:00:00+08:00", "2026-09-07T02:05:00Z",
                            market_timezone="Asia/Shanghai", calendar_name="XSHG"),
            "00700": quote("Tencent", "hk", "00700", 20,
                           "2026-09-07T10:00:00+08:00", "2026-09-07T02:05:00Z",
                           market_timezone="Asia/Hong_Kong", calendar_name="XHKG"),
        }
        sessions = [session("2026-09-07T01:30:00Z", "2026-09-07T08:00:00Z")]
        with mock.patch.object(stock, "tencent_quotes", return_value=primary), \
             mock.patch.object(stock, "_market_calendar_sessions",
                               return_value=(sessions, "test_calendar")):
            report, exit_code = stock.build_quote_report(symbols)
        self.assertEqual(exit_code, 0)
        self.assertIsNone(report["as_of"])
        self.assertEqual(report["as_of_reason_code"], "mixed_markets_not_aggregated")
        self.assertEqual(set(report["as_of_by_market"]), {"cn", "hk"})

    def test_source_timestamp_semantics_are_explicit(self):
        self.assertEqual(
            stock._tencent_market_at("20260907100000", "Asia/Shanghai"),
            "2026-09-07T10:00:00+08:00",
        )
        self.assertEqual(stock._yahoo_market_at(0), "1970-01-01T00:00:00Z")

    def test_yahoo_exchange_mapping_does_not_treat_us_exchanges_as_synonyms(self):
        self.assertEqual(stock._yahoo_calendar_name("us", "NYQ"), "XNYS")
        for exchange in ("NMS", "NGM", "NCM"):
            self.assertEqual(stock._yahoo_calendar_name("us", exchange), "XNAS")
        self.assertEqual(stock._yahoo_calendar_name("cn", "SHH"), "XSHG")
        self.assertIsNone(stock._yahoo_calendar_name("cn", "SHZ"))
        self.assertIsNone(stock._yahoo_calendar_name("us", "ASE"))

    def test_yahoo_quotes_sends_crumb_and_keeps_valuation_fields(self):
        response = mock.Mock()
        response.json.return_value = {"quoteResponse": {"result": [{
            "symbol": "AAPL", "exchange": "NMS", "regularMarketPrice": 250.0,
            "regularMarketTime": 1793826001, "marketCap": 100, "trailingPE": 30.0,
            "exchangeTimezoneName": "America/New_York",
        }]}}
        session = mock.Mock(_crumb="test-crumb")
        session.get.return_value = response
        with mock.patch.object(stock, "_yahoo_session", return_value=session):
            result = stock.yahoo_quotes([stock.normalize_ticker("AAPL")])
        self.assertEqual(session.get.call_args.kwargs["params"]["crumb"], "test-crumb")
        self.assertEqual(result["AAPL"]["price"], 250.0)
        self.assertEqual(result["AAPL"]["market_cap"], 100)
        self.assertEqual(result["AAPL"]["pe_ttm"], 30.0)
        self.assertEqual(result["AAPL"]["calendar_name"], "XNAS")


@unittest.skipUnless(
    importlib.util.find_spec("exchange_calendars"),
    "exchange_calendars integration requires the stock-data runtime",
)
class ExchangeCalendarIntegrationTests(unittest.TestCase):
    def sessions(self, calendar, start, end):
        sessions, status = stock._market_calendar_sessions(
            calendar,
            stock._dt.date.fromisoformat(start),
            stock._dt.date.fromisoformat(end),
        )
        self.assertEqual(status, "exchange_calendars")
        self.assertIsNotNone(sessions)
        return sessions

    def test_a_h_breaks_and_hk_half_day_are_in_schedule(self):
        shanghai = self.sessions("XSHG", "2026-09-08", "2026-09-08")[0]
        self.assertEqual(shanghai["break_start"].isoformat(), "2026-09-08T03:30:00+00:00")
        self.assertEqual(shanghai["break_end"].isoformat(), "2026-09-08T05:00:00+00:00")

        hong_kong = self.sessions("XHKG", "2026-09-08", "2026-09-08")[0]
        self.assertEqual(hong_kong["break_start"].isoformat(), "2026-09-08T04:00:00+00:00")
        self.assertEqual(hong_kong["break_end"].isoformat(), "2026-09-08T05:00:00+00:00")

        hk_half_day = self.sessions("XHKG", "2026-02-16", "2026-02-16")[0]
        self.assertEqual(hk_half_day["close"].isoformat(), "2026-02-16T04:00:00+00:00")
        self.assertIsNone(hk_half_day["break_start"])
        self.assertIsNone(hk_half_day["break_end"])

    def test_labor_day_latest_close_is_september_four(self):
        sessions = self.sessions("XNYS", "2026-09-03", "2026-09-08")
        self.assertEqual([item["date"] for item in sessions], [
            "2026-09-03", "2026-09-04", "2026-09-08",
        ])
        payload = quote(
            "Yahoo", "us", "AAPL", 10, "2026-09-04T20:00:00Z",
            "2026-09-08T00:30:00Z", market_timezone="America/New_York",
            calendar_name="XNYS",
        )
        result = stock._quote_freshness(payload)
        self.assertEqual(result["freshness_status"], "latest_close")
        self.assertEqual(result["freshness_reason_code"], "latest_completed_session")
        self.assertTrue(result["t0_eligible"])

    def test_nasdaq_and_nyse_capture_dst_and_early_close(self):
        for calendar in ("XNYS", "XNAS"):
            with self.subTest(calendar=calendar):
                early_close = self.sessions(calendar, "2026-11-27", "2026-11-27")[0]
                self.assertEqual(early_close["open"].isoformat(), "2026-11-27T14:30:00+00:00")
                self.assertEqual(early_close["close"].isoformat(), "2026-11-27T18:00:00+00:00")

    def test_calendar_lookup_failure_remains_unknown(self):
        payload = quote(
            "Yahoo", "us", "AAPL", 10, "2026-09-04T20:00:00Z",
            "2026-09-08T00:30:00Z", market_timezone="America/New_York",
            calendar_name="NOT_A_REAL_EXCHANGE",
        )
        result = stock._quote_freshness(payload)
        self.assertEqual(result["freshness_status"], "unknown")
        self.assertEqual(result["calendar_status"], "calendar_lookup_failed")
        self.assertFalse(result["t0_eligible"])

class HongKongQfqTests(unittest.TestCase):
    DAY = 86400
    START = 1793839800  # 2026-11-05 09:30 HKT 附近的固定时间戳

    def chart(self, closes, dividends=None, granularity="1d", symbol="0700.HK", adjclose=None):
        timestamps = [self.START + i * self.DAY for i in range(len(closes))]
        indicators = {"quote": [{
            "open": closes, "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes], "close": closes, "volume": [10] * len(closes),
        }]}
        if adjclose:
            indicators["adjclose"] = [{"adjclose": adjclose}]
        response = mock.Mock()
        response.json.return_value = {"chart": {"result": [{
            "meta": {"symbol": symbol, "dataGranularity": granularity, "gmtoffset": 28800,
                     "shortName": "TEST"},
            "timestamp": timestamps,
            "events": {"dividends": {
                str(timestamps[i]): {"date": timestamps[i], "amount": amount}
                for i, amount in (dividends or {}).items()
            }},
            "indicators": indicators,
        }]}}
        return response

    def fetch(self, response, count=10, ktype=9, symbol="00700"):
        with mock.patch.object(stock.requests, "get", return_value=response) as get:
            result = stock.adjusted_kline(symbol, count=count, ktype=ktype)
        return result, get

    def test_yahoo_hk_symbols_are_zero_padded(self):
        self.assertEqual(stock.normalize_ticker("00700").yahoo, "0700.HK")
        self.assertEqual(stock.normalize_ticker("00005").yahoo, "0005.HK")
        self.assertEqual(stock.normalize_ticker("09988").yahoo, "9988.HK")
        self.assertEqual(stock.normalize_ticker("0700.HK").code, "00700")

    def test_dividend_scales_only_bars_before_ex_date(self):
        result, _ = self.fetch(self.chart([100.0, 100.0, 90.0, 95.0], dividends={2: 10.0}))
        closes = [row["close"] for row in result["rows"]]
        self.assertEqual(closes, [90.0, 90.0, 90.0, 95.0])
        self.assertEqual(result["adjustment"], "qfq")
        self.assertEqual(result["adjustment_method"], "ratio")
        self.assertEqual(result["dividend_events_applied"], 1)

    def test_adjclose_is_ignored_because_usd_dividends_are_mispriced(self):
        result, _ = self.fetch(self.chart(
            [100.0, 90.0], dividends={1: 10.0}, adjclose=[98.7, 90.0],
        ))
        self.assertEqual(result["rows"][0]["close"], 90.0)

    def test_multiple_dividends_compound(self):
        result, _ = self.fetch(self.chart(
            [100.0, 100.0, 100.0], dividends={1: 10.0, 2: 50.0},
        ))
        self.assertEqual([row["close"] for row in result["rows"]], [45.0, 50.0, 100.0])

    def test_dividend_outside_window_is_not_applied(self):
        result, _ = self.fetch(self.chart([100.0, 90.0], dividends={0: 10.0}))
        self.assertEqual([row["close"] for row in result["rows"]], [100.0, 90.0])
        self.assertEqual(result["dividend_events_applied"], 0)

    def test_impossible_dividend_fails_closed(self):
        for amount in (0, -1, 100.0, 500.0):
            with self.subTest(amount=amount), self.assertRaisesRegex(ValueError, "dividend out of range"):
                self.fetch(self.chart([100.0, 90.0], dividends={1: amount}))

    def test_contract_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "interval mismatch"):
            self.fetch(self.chart([100.0], granularity="1mo"))
        with self.assertRaisesRegex(ValueError, "symbol mismatch"):
            self.fetch(self.chart([100.0], symbol="0005.HK"))

    def test_request_uses_explicit_window_because_range_max_degrades(self):
        _, get = self.fetch(self.chart([100.0, 101.0]))
        params = get.call_args.kwargs["params"]
        self.assertNotIn("range", params)
        self.assertEqual(params["interval"], "1d")
        self.assertIn("period1", params)

    def test_weekly_bars_aggregate_adjusted_daily_rows(self):
        closes = [100.0, 100.0, 90.0, 92.0, 94.0, 96.0, 98.0, 99.0]
        result, _ = self.fetch(self.chart(closes, dividends={2: 10.0}), ktype=102)
        self.assertEqual(result["period"], "week")
        rows = result["rows"]
        self.assertEqual(rows[-1]["close"], 99.0)
        self.assertEqual(sum(row["volume"] for row in rows), 80)
        self.assertLess(len(rows), len(closes))

    def test_a_share_and_hk_unadjusted_stay_on_tencent(self):
        with mock.patch.object(stock, "tencent_akline", return_value={"rows": []}) as tencent, \
             mock.patch.object(stock, "yahoo_hk_qfq_kline") as yahoo:
            stock.adjusted_kline("600519", count=1, ktype=9)
            stock.adjusted_kline("00700", count=1, ktype=101)
        self.assertEqual(tencent.call_count, 2)
        yahoo.assert_not_called()


class EastmoneyFallbackTests(unittest.TestCase):
    def kline_response(self, closes, code="600519", rc=0, data_ok=True):
        lines = [
            f"2026-11-0{i + 1},{c},{c},{c + 1},{c - 1},{100 * (i + 1)},0" for i, c in enumerate(closes)
        ]
        response = mock.Mock()
        response.json.return_value = {"rc": rc, "data": (
            {"code": code, "name": "TEST", "klines": lines} if data_ok else None
        )}
        return response

    def fetch(self, closes, factors=(), events=None, count=10, ktype=9, **kwargs):
        with mock.patch.object(stock.requests, "get", return_value=self.kline_response(closes, **kwargs)), \
             mock.patch.object(stock, "_baostock_fore_factors", return_value=list(factors)) as fore, \
             mock.patch.object(stock, "_cn_dividend_events", return_value=events or {}):
            result = stock.eastmoney_kline("600519", count=count, ktype=ktype)
        return result, fore

    def test_factor_applies_from_the_latest_event_not_after_the_date(self):
        # 事件 11-02 因子 0.5、11-04 因子 1.0；早于首个事件的日期用首个事件的因子
        result, _ = self.fetch([100.0, 100.0, 100.0, 100.0],
                               factors=[("2026-11-02", 0.5), ("2026-11-04", 1.0)])
        self.assertEqual([row["close"] for row in result["rows"]], [50.0, 50.0, 50.0, 100.0])
        self.assertEqual(result["adjustment"], "qfq")
        self.assertEqual(result["adjustment_method"], "ratio")
        self.assertEqual(result["adjustment_events_in_window"], 2)
        self.assertEqual(result["volume_unit"], "手")
        self.assertEqual(result["stale_check"], "ok")

    def test_stock_without_events_keeps_raw_prices(self):
        result, _ = self.fetch([100.0, 90.0])
        self.assertEqual([row["close"] for row in result["rows"]], [100.0, 90.0])

    def test_unadjusted_ktype_does_not_touch_baostock(self):
        result, fore = self.fetch([100.0, 90.0], factors=[("2026-11-02", 0.5)], ktype=101)
        self.assertEqual([row["close"] for row in result["rows"]], [100.0, 90.0])
        self.assertEqual(result["adjustment"], "none")
        fore.assert_not_called()

    def test_new_ex_date_missing_from_baostock_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "尚未收录.*2026-11-02"):
            self.fetch([100.0, 90.0], factors=[("2026-10-01", 1.0)],
                       events={"2026-11-02": (0.4, 0.0)})

    def test_events_after_the_last_bar_or_already_in_baostock_are_ignored(self):
        result, _ = self.fetch([100.0, 90.0], factors=[("2026-11-02", 1.0)],
                               events={"2026-11-02": (0.4, 0.0), "2026-12-30": (0.4, 0.0)})
        self.assertEqual(result["stale_check"], "ok")

    def test_stale_check_failure_is_reported_not_hidden(self):
        with mock.patch.object(stock.requests, "get", return_value=self.kline_response([100.0, 90.0])), \
             mock.patch.object(stock, "_baostock_fore_factors", return_value=[]), \
             mock.patch.object(stock, "_cn_dividend_events", side_effect=RuntimeError("datacenter down")):
            result = stock.eastmoney_kline("600519", count=5)
        self.assertTrue(result["stale_check"].startswith("skipped"))

    def test_baostock_failure_propagates(self):
        with mock.patch.object(stock.requests, "get", return_value=self.kline_response([100.0])), \
             mock.patch.object(stock, "_baostock_fore_factors", side_effect=RuntimeError("baostock down")):
            with self.assertRaisesRegex(RuntimeError, "baostock down"):
                stock.eastmoney_kline("600519", count=5)

    def test_contract_failures_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "no K-line data"):
            self.fetch([100.0], data_ok=False, rc=102)
        with self.assertRaisesRegex(ValueError, "symbol mismatch"):
            self.fetch([100.0], code="000001")

    def test_tencent_failure_falls_back_with_provenance(self):
        eastmoney = {"rows": [], "source": "Eastmoney"}
        with mock.patch.object(stock, "tencent_akline", side_effect=RuntimeError("501 Not Implemented")), \
             mock.patch.object(stock, "eastmoney_kline", return_value=eastmoney) as fallback:
            result = stock.adjusted_kline("600519", count=5)
        fallback.assert_called_once()
        self.assertIn("501", result["fallback_from"])

    def test_healthy_tencent_does_not_touch_eastmoney(self):
        with mock.patch.object(stock, "tencent_akline", return_value={"rows": []}), \
             mock.patch.object(stock, "eastmoney_kline") as fallback:
            stock.adjusted_kline("600519", count=5)
        fallback.assert_not_called()

    def test_fallback_is_not_used_for_unsupported_requests(self):
        with mock.patch.object(stock, "tencent_akline", side_effect=ValueError("minute not enabled")), \
             mock.patch.object(stock, "eastmoney_kline") as fallback:
            with self.assertRaises(ValueError):
                stock.adjusted_kline("600519", count=5, ktype=5)
        fallback.assert_not_called()

    def test_both_sources_failing_reports_both(self):
        with mock.patch.object(stock, "tencent_akline", side_effect=RuntimeError("tencent down")), \
             mock.patch.object(stock, "eastmoney_kline", side_effect=RuntimeError("em down")):
            with self.assertRaisesRegex(RuntimeError, "tencent down.*em down"):
                stock.adjusted_kline("600519", count=5)

    def test_hong_kong_only_falls_back_for_unadjusted_bars(self):
        with mock.patch.object(stock, "tencent_akline", side_effect=RuntimeError("501")), \
             mock.patch.object(stock, "eastmoney_kline", return_value={"rows": []}) as fallback:
            stock.adjusted_kline("00700", count=5, ktype=101)
        fallback.assert_called_once()
        with self.assertRaisesRegex(ValueError, "yahoo_hk_qfq_kline"):
            stock.eastmoney_kline("00700", count=5, ktype=9)


class CalendarCoverageTests(unittest.TestCase):
    def test_frozen_finite_calendar_rejects_uncovered_dates(self):
        class LimitedCalendar:
            first_session = stock._dt.date(2026, 12, 30)
            last_session = stock._dt.date(2026, 12, 31)

            @property
            def schedule(self):
                raise AssertionError("out-of-range lookup must not slice the schedule")

        with mock.patch("exchange_calendars.get_calendar", return_value=LimitedCalendar()):
            sessions, status = stock._market_calendar_sessions(
                "XSHG", stock._dt.date(2026, 12, 30), stock._dt.date(2027, 1, 1)
            )
        self.assertIsNone(sessions)
        self.assertEqual(status, "calendar_out_of_range")

    def test_real_xshg_coverage_end_cannot_certify_latest_close(self):
        payload = quote(
            "Tencent", "cn", "600519", 10, "2026-12-31T15:00:00+08:00",
            "2027-01-04T00:00:00Z", market_timezone="Asia/Shanghai",
            calendar_name="XSHG",
        )
        result = stock._quote_freshness(payload)
        self.assertEqual(result["freshness_status"], "unknown")
        self.assertEqual(result["calendar_status"], "calendar_out_of_range")
        self.assertEqual(result["freshness_reason_code"], "calendar_out_of_range")
        self.assertFalse(result["t0_eligible"])


class KlineContractTests(unittest.TestCase):
    @staticmethod
    def _tencent_response(rows, key="qfqday"):
        return FakeResponse({"data": {"sh600519": {key: rows}}})

    def test_tencent_count_is_exact_max_for_day_and_week(self):
        raw = [
            [f"2026-09-{day:02d}", str(day), str(day + 0.5),
             str(day + 1), str(day - 1), "100"]
            for day in range(1, 7)
        ]
        for ktype, key in ((9, "qfqday"), (102, "qfqweek")):
            with self.subTest(ktype=ktype), mock.patch.object(
                stock.requests, "get", return_value=self._tencent_response(raw, key)
            ):
                result = stock.tencent_akline("600519", count=5, ktype=ktype)
            self.assertEqual(len(result["rows"]), 5)
            self.assertEqual(result["rows"][0]["date"], "2026-09-02")
            self.assertEqual(result["source_returned_count"], 6)
            self.assertEqual(result["requested_count"], 5)
            self.assertEqual(result["returned_count"], 5)
            self.assertEqual(result["adjustment_method"], "price_difference")

    def test_invalid_duplicate_and_unsorted_rows_cannot_define_latest_window(self):
        rows = [bar("2026-09-05", 5), bar("bad-date", 9), bar("2026-09-02", 2),
                bar("2026-09-04", 4), bar("2026-09-04", 4.5), bar("2026-09-03", 3)]
        selected, metadata = stock._validated_recent_bars(rows, 3)
        self.assertEqual([row["date"] for row in selected], [
            "2026-09-03", "2026-09-04", "2026-09-05",
        ])
        self.assertEqual(selected[1]["close"], 4.5)
        self.assertEqual(metadata["source_order"], "unsorted")
        self.assertEqual(metadata["invalid_row_count"], 1)
        self.assertEqual(metadata["duplicate_row_count"], 1)

    def test_fewer_valid_rows_are_returned_without_padding(self):
        selected, metadata = stock._validated_recent_bars([bar("2026-09-01"), bar("2026-09-02")], 5)
        self.assertEqual(len(selected), 2)
        self.assertEqual(metadata["returned_count"], 2)
        self.assertEqual(metadata["requested_count"], 5)

    def test_invalid_count_and_minute_reject_before_request(self):
        for count in (0, -1, True, "5"):
            with self.subTest(count=count), mock.patch.object(stock.requests, "get") as get:
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    stock.tencent_akline("600519", count=count)
                get.assert_not_called()
        with mock.patch.object(stock.requests, "get") as get:
            with self.assertRaisesRegex(ValueError, "minute"):
                stock.tencent_akline("600519", count=5, ktype=5)
            get.assert_not_called()

    def test_period_adjustment_key_must_match_exactly(self):
        response = self._tencent_response([["2026-09-01", 9, 10, 11, 8, 100]], "day")
        with mock.patch.object(stock.requests, "get", return_value=response):
            with self.assertRaisesRegex(ValueError, "expected exact key='qfqday'"):
                stock.tencent_akline("600519", count=1, ktype=9)

    def test_yahoo_cli_applies_same_count_contract(self):
        args = mock.Mock(symbol="AAPL", period="1mo", interval="1d", count=5)
        source_rows = [bar(f"2026-09-{day:02d}", day) for day in range(1, 7)]
        with mock.patch.object(stock, "yahoo_kline", return_value=source_rows), \
             mock.patch.object(stock, "print_json") as print_json:
            self.assertEqual(stock.cmd_kline(args), 0)
        output = print_json.call_args.args[0]
        self.assertEqual(len(output["rows"]), 5)
        self.assertEqual(output["source_returned_count"], 6)
        self.assertEqual(output["returned_count"], 5)

    def test_yahoo_cli_rejects_all_invalid_rows(self):
        args = mock.Mock(symbol="AAPL", period="1mo", interval="1d", count=5)
        with mock.patch.object(stock, "yahoo_kline", return_value=[bar("invalid")]), \
             mock.patch.object(stock, "print_json") as print_json:
            with self.assertRaisesRegex(ValueError, "no valid K-line rows"):
                stock.cmd_kline(args)
        print_json.assert_not_called()


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


class LauncherTests(unittest.TestCase):
    def test_bootstrap_subprocess_stdout_is_redirected_to_stderr(self):
        runtime = Path("/tmp/stock-data-test-runtime/bin/python")
        marker = mock.Mock()
        with mock.patch.object(launcher, "_runtime_python", return_value=runtime), \
             mock.patch.object(launcher, "_bootstrap_python", return_value="/usr/bin/python3"), \
             mock.patch.object(launcher, "_marker_matches", return_value=False), \
             mock.patch.object(launcher, "_installed_versions_match", return_value=False), \
             mock.patch.object(launcher, "MARKER", marker), \
             mock.patch.object(launcher.Path, "is_file", return_value=False), \
             mock.patch.object(launcher.subprocess, "run") as run:
            self.assertEqual(launcher._ensure_runtime(), runtime)

        self.assertEqual(run.call_count, 2)
        for subprocess_call in run.call_args_list:
            self.assertIs(subprocess_call.kwargs["stdout"], sys.stderr)
        self.assertEqual(run.call_args_list[1].args[0][2:4], ["pip", "install"])
        marker.write_text.assert_called_once()


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
