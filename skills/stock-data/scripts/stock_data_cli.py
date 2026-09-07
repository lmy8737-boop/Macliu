#!/usr/bin/env python3
"""Executable helpers for the stock-data skill (v5.2, 增量 2026-09-04).

本次更新只新增两类此前标可达但未沉淀的能力:
1) A股日K连板复算 — 腾讯 fqkline (`web.ifzq.gtimg.cn`)
2) 龙虎榜 / 融资融券 — 东财 datacenter-web (`datacenter-web.eastmoney.com`)

其余能力（板块排名 / 资金流 / 热点 / 新闻 / 公告 / 概念 / 研报）已在
SKILL.md 的 references/ 文档中记录, 按需后续单独沉淀到 CLI。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path as _Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import requests
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: requests. Install with `pip install requests`.") from exc


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
SEC_HEADERS = {"User-Agent": "stock-data skill/5.2 contact@example.com"}

# 新增的两个端点基址（2026-09-04 实测沙箱可达）
TENCENT_AKLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


@dataclass(frozen=True)
class NormalizedTicker:
    raw: str
    market: str
    code: str
    yahoo: str
    tencent: str | None = None
    eastmoney: str | None = None


def normalize_ticker(raw: str) -> NormalizedTicker:
    """Normalize A/H/US tickers.

    Fixes a common pitfall from older docs: `00700` should route to HK, not A股.
    Six-digit numeric inputs remain A股 unless explicitly suffixed `.HK`.
    """
    value = raw.strip()
    upper = value.upper()

    if upper.startswith("^"):
        return NormalizedTicker(raw=value, market="index", code=upper, yahoo=upper)

    hk_match = re.match(r"^(?:HK)?0*(\d{1,5})(?:\.HK)?$", upper)
    if upper.startswith("HK") or upper.endswith(".HK") or (hk_match and len(re.sub(r"\D", "", upper)) < 6):
        digits = re.sub(r"\D", "", upper).zfill(5)
        yahoo_num = str(int(digits)) if int(digits) else digits
        return NormalizedTicker(
            raw=value, market="hk", code=digits, yahoo=f"{yahoo_num}.HK",
            tencent=f"hk{digits}", eastmoney=f"116.{digits}",
        )

    a_match = re.match(r"^(?:SH|SZ|BJ)?(\d{6})(?:\.(SH|SZ|BJ))?$", upper)
    if a_match:
        code = a_match.group(1)
        suffix = a_match.group(2)
        if suffix:
            prefix = suffix.lower()
        elif code.startswith(("4", "8", "92")):
            # 北交所号段 43/83/87/92xxxx；必须先于 "9" 判定，否则 920xxx 会被
            # 下面的 sh 分支误吞（同一 bug 上游 a-stock-data 在 v3.5.1/v3.6.0/
            # v3.7.2 反复修过，920 是 2023 年后启用的北交所新号段，非上证 B 股）。
            prefix = "bj"
        elif code.startswith(("6", "9")):
            prefix = "sh"
        else:
            prefix = "sz"
        em_prefix = "1" if prefix == "sh" else "0"
        yahoo_suffix = "SS" if prefix == "sh" else "SZ"
        return NormalizedTicker(
            raw=value, market="cn", code=code, yahoo=f"{code}.{yahoo_suffix}",
            tencent=f"{prefix}{code}", eastmoney=f"{em_prefix}.{code}",
        )

    us_match = re.match(r"^[A-Z]{1,6}(?:[.-][A-Z])?$", upper)
    if us_match:
        ticker = upper.replace(".", "-")
        return NormalizedTicker(raw=value, market="us", code=ticker, yahoo=ticker, tencent=f"us{ticker}")

    raise ValueError(f"Unsupported ticker format: {raw}")


def _float(values: list[str], idx: int) -> float | None:
    try:
        value = values[idx]
        return float(value) if value not in ("", "-") else None
    except (IndexError, ValueError):
        return None


def _seq(values: list[Any] | None, idx: int) -> Any:
    return values[idx] if values and idx < len(values) else None


def _round(value: Any, digits: int = 4) -> float | None:
    return round(float(value), digits) if value is not None else None


def _round2(value: Any) -> float | None:
    return round(float(value), 2) if value is not None else None


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _tencent_market_at(value: str | None, timezone_name: str | None = None) -> str | None:
    """Normalize Tencent's wall-clock field only when its timezone is known."""
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 14:
        try:
            parsed = _dt.datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
            if timezone_name:
                parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
            return parsed.isoformat(timespec="seconds")
        except (ValueError, ZoneInfoNotFoundError):
            pass
    return value.strip() or None


def _yahoo_market_at(value: Any) -> str | None:
    if value is None:
        return None


_TENCENT_MARKET_CLOCKS = {
    "cn": ("Asia/Shanghai", "XSHG"),
    "hk": ("Asia/Hong_Kong", "XHKG"),
}
_YAHOO_US_EXCHANGES = {"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS"}


def _parse_aware_datetime(value: Any, timezone_name: str | None = None) -> _dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            if not timezone_name:
                return None
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        return parsed.astimezone(_dt.timezone.utc)
    except (ValueError, ZoneInfoNotFoundError):
        return None


def _as_utc_datetime(value: Any) -> _dt.datetime | None:
    if value is None:
        return None
    try:
        parsed = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
        if not isinstance(parsed, _dt.datetime) or parsed.tzinfo is None:
            return None
        return parsed.astimezone(_dt.timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _market_calendar_sessions(
    calendar_name: str, start_date: _dt.date, end_date: _dt.date,
) -> tuple[list[dict[str, Any]] | None, str]:
    """Read sessions from exchange_calendars; absence is an explicit unknown."""
    try:
        import exchange_calendars as xcals
    except ModuleNotFoundError:
        return None, "calendar_library_unavailable"

    try:
        calendar = xcals.get_calendar(calendar_name)
        schedule = calendar.schedule.loc[start_date.isoformat():end_date.isoformat()]
        sessions = []
        for label, row in schedule.iterrows():
            opened = _as_utc_datetime(row.get("open", row.get("market_open")))
            closed = _as_utc_datetime(row.get("close", row.get("market_close")))
            if opened is None or closed is None:
                return None, "calendar_schedule_malformed"
            session = {
                "date": label.date().isoformat(),
                "open": opened,
                "close": closed,
                "break_start": _as_utc_datetime(row.get("break_start")),
                "break_end": _as_utc_datetime(row.get("break_end")),
            }
            sessions.append(session)
        return sessions, "exchange_calendars"
    except Exception:
        return None, "calendar_lookup_failed"


def _quote_freshness(payload: dict[str, Any]) -> dict[str, Any]:
    timezone_name = payload.get("market_timezone")
    market_at = _parse_aware_datetime(payload.get("market_at"), timezone_name)
    retrieved_at = _parse_aware_datetime(payload.get("retrieved_at"))
    base = {
        "freshness_status": "unknown",
        "freshness_reason_code": "timestamp_unverifiable",
        "t0_eligible": False,
        "market_timezone": timezone_name or "unknown",
        "calendar_name": payload.get("calendar_name") or "unknown",
        "calendar_status": "not_checked",
        "delay_seconds": None,
    }
    if market_at is None:
        base["freshness_reason_code"] = (
            "market_timezone_unknown" if payload.get("market_at") else "market_at_missing"
        )
        return base
    if retrieved_at is None:
        base["freshness_reason_code"] = "retrieved_at_invalid"
        return base

    delay = (retrieved_at - market_at).total_seconds()
    base["delay_seconds"] = round(delay, 3)
    if delay < -120:
        base.update(
            freshness_status="future", freshness_reason_code="market_at_in_future",
            calendar_status="not_checked",
        )
        return base

    calendar_name = payload.get("calendar_name")
    if not calendar_name:
        base["freshness_reason_code"] = "exchange_calendar_unknown"
        return base
    sessions, calendar_status = _market_calendar_sessions(
        calendar_name, retrieved_at.date() - _dt.timedelta(days=10),
        retrieved_at.date() + _dt.timedelta(days=1),
    )
    base["calendar_status"] = calendar_status
    if sessions is None:
        base["freshness_reason_code"] = calendar_status
        return base

    tolerance = _dt.timedelta(minutes=30)
    matching = next(
        (s for s in sessions if s["open"] - tolerance <= market_at <= s["close"] + tolerance),
        None,
    )
    if matching is None:
        base["freshness_reason_code"] = "market_at_not_in_trading_session"
        return base

    active = next(
        (s for s in sessions if s["open"] <= retrieved_at <= s["close"]), None
    )
    if active:
        break_start, break_end = active.get("break_start"), active.get("break_end")
        if break_start and break_end and break_start <= retrieved_at <= break_end:
            if matching is active and abs((market_at - break_start).total_seconds()) <= 1800:
                base.update(
                    freshness_status="latest_close", freshness_reason_code="latest_market_pause",
                    t0_eligible=True,
                )
            else:
                base.update(freshness_status="stale", freshness_reason_code="stale_during_market_pause")
            return base
        if matching is active and -120 <= delay <= 900:
            base.update(
                freshness_status="fresh", freshness_reason_code="fresh_during_session",
                t0_eligible=True,
            )
        else:
            base.update(freshness_status="stale", freshness_reason_code="stale_during_session")
        return base

    completed = [s for s in sessions if s["close"] <= retrieved_at]
    latest = max(completed, key=lambda s: s["close"]) if completed else None
    if latest and matching is latest and abs((market_at - latest["close"]).total_seconds()) <= 1800:
        base.update(
            freshness_status="latest_close", freshness_reason_code="latest_completed_session",
            t0_eligible=True,
        )
    else:
        base.update(freshness_status="stale", freshness_reason_code="not_latest_completed_session")
    return base


def _validated_recent_bars(
    rows: list[Any], count: int, *, intraday: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("K-line count must be a positive integer")

    parsed_rows: list[tuple[_dt.datetime, dict[str, Any]]] = []
    invalid_count = 0
    date_format = "%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d"
    for row in rows:
        try:
            if not isinstance(row, dict):
                raise ValueError
            date_value = row.get("date")
            parsed_date = _dt.datetime.strptime(date_value, date_format)
            values = {field: float(row[field]) for field in ("open", "high", "low", "close")}
            volume = float(row.get("volume", 0))
            if not all(math.isfinite(v) for v in (*values.values(), volume)) or volume < 0:
                raise ValueError
            if values["high"] < max(values["open"], values["close"], values["low"]):
                raise ValueError
            if values["low"] > min(values["open"], values["close"], values["high"]):
                raise ValueError
            normalized = dict(row)
            normalized.update({field: round(value, 4) for field, value in values.items()})
            normalized["volume"] = int(volume)
            parsed_rows.append((parsed_date, normalized))
        except (KeyError, TypeError, ValueError, OverflowError):
            invalid_count += 1

    source_dates = [item[0] for item in parsed_rows]
    if source_dates == sorted(source_dates):
        source_order = "ascending"
    elif source_dates == sorted(source_dates, reverse=True):
        source_order = "descending"
    else:
        source_order = "unsorted"

    by_date: dict[_dt.datetime, dict[str, Any]] = {}
    for parsed_date, row in parsed_rows:
        by_date[parsed_date] = row
    duplicate_count = len(parsed_rows) - len(by_date)
    valid_rows = [by_date[key] for key in sorted(by_date)]
    selected = valid_rows[-count:]
    return selected, {
        "requested_count": count,
        "source_returned_count": len(rows),
        "source_valid_count": len(parsed_rows),
        "available_valid_count": len(valid_rows),
        "returned_count": len(selected),
        "invalid_row_count": invalid_count,
        "duplicate_row_count": duplicate_count,
        "source_order": source_order,
    }
    try:
        return _dt.datetime.fromtimestamp(float(value), _dt.timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def parse_tencent_line(text: str) -> list[str]:
    match = re.search(r'"(.*)"', text)
    return match.group(1).split("~") if match else []


def tencent_quotes(symbols: list[NormalizedTicker]) -> dict[str, dict[str, Any]]:
    prefixed = [s.tencent for s in symbols if s.tencent]
    if not prefixed:
        return {}
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode("gbk", errors="replace")
    retrieved_at = _utc_now_iso()

    result: dict[str, dict[str, Any]] = {}
    symbol_by_tencent = {s.tencent: s for s in symbols if s.tencent}
    for line in raw.split(";"):
        if not line.strip() or "=" not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = parse_tencent_line(line)
        meta = symbol_by_tencent.get(key)
        if not meta or len(vals) < 40:
            continue
        if meta.market == "hk":
            payload = {
                "source": "Tencent", "market": "hk", "code": meta.code,
                "name": vals[1], "price": _float(vals, 3),
                "prev_close": _float(vals, 4), "open": _float(vals, 5),
                "change": _float(vals, 31), "change_pct": _float(vals, 32),
                "high": _float(vals, 33), "low": _float(vals, 34),
                "volume": _float(vals, 36), "amount_wan": _float(vals, 37),
                "pe_ttm": _float(vals, 39), "market_cap_yi": _float(vals, 44),
                "pb": _float(vals, 46), "currency": "HKD",
            }
        elif meta.market == "us":
            payload = {
                "source": "Tencent", "market": "us", "code": meta.code,
                "name": vals[1], "price": _float(vals, 3),
                "prev_close": _float(vals, 4), "open": _float(vals, 5),
                "change": _float(vals, 31), "change_pct": _float(vals, 32),
                "high": _float(vals, 33), "low": _float(vals, 34),
                "volume": _float(vals, 36), "currency": "USD",
            }
        else:
            payload = {
                "source": "Tencent", "market": "cn", "code": meta.code,
                "name": vals[1], "price": _float(vals, 3),
                "prev_close": _float(vals, 4), "open": _float(vals, 5),
                "change": _float(vals, 31), "change_pct": _float(vals, 32),
                "high": _float(vals, 33), "low": _float(vals, 34),
                "amount_wan": _float(vals, 37),
                "turnover_pct": _float(vals, 38),
                "pe_ttm": _float(vals, 39),
                "market_cap_yi": _float(vals, 44),
                "float_market_cap_yi": _float(vals, 45),
                "pb": _float(vals, 46),
                "limit_up": _float(vals, 47),
                "limit_down": _float(vals, 48),
                "currency": "CNY",
            }
        market_at_raw = vals[30] if len(vals) > 30 else None
        timezone_name, calendar_name = _TENCENT_MARKET_CLOCKS.get(meta.market, (None, None))
        payload["market_at_raw"] = market_at_raw
        payload["market_at"] = _tencent_market_at(market_at_raw, timezone_name)
        payload["market_at_basis"] = "exchange_local" if timezone_name else "unknown"
        payload["market_timezone"] = timezone_name
        payload["calendar_name"] = calendar_name
        payload["retrieved_at"] = retrieved_at
        result[meta.raw] = payload
    return result


def yahoo_quotes(symbols: list[NormalizedTicker]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    params = {"symbols": ",".join(s.yahoo for s in symbols)}
    resp = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
    resp.raise_for_status()
    retrieved_at = _utc_now_iso()
    by_symbol = {item.get("symbol"): item for item in resp.json().get("quoteResponse", {}).get("result", [])}
    out: dict[str, dict[str, Any]] = {}
    for s in symbols:
        item = by_symbol.get(s.yahoo, {})
        exchange = item.get("exchange")
        calendar_name = None
        if s.market == "hk" and exchange in {"HKG", "HKGD"}:
            calendar_name = "XHKG"
        elif s.market == "cn" and exchange in {"SHH", "SHZ"}:
            calendar_name = "XSHG" if exchange == "SHH" else None
        elif s.market == "us" and exchange in _YAHOO_US_EXCHANGES:
            calendar_name = "XNYS"
        out[s.raw] = {
            "source": "Yahoo", "market": s.market, "code": s.code,
            "symbol": s.yahoo, "name": item.get("shortName") or item.get("longName"),
            "price": item.get("regularMarketPrice"),
            "change": item.get("regularMarketChange"),
            "change_pct": item.get("regularMarketChangePercent"),
            "volume": item.get("regularMarketVolume"),
            "market_cap": item.get("marketCap"),
            "pe_ttm": item.get("trailingPE"),
            "pb": item.get("priceToBook"),
            "currency": item.get("currency"),
            "market_time": item.get("regularMarketTime"),
            "market_at": _yahoo_market_at(item.get("regularMarketTime")),
            "market_at_basis": "unix_epoch_utc",
            "market_timezone": item.get("exchangeTimezoneName"),
            "exchange": exchange,
            "calendar_name": calendar_name,
            "retrieved_at": retrieved_at,
        }
    return out


def yahoo_kline(symbol: str, period: str, interval: str) -> list[dict[str, Any]]:
    ticker = normalize_ticker(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker.yahoo)}"
    resp = requests.get(
        url,
        params={"range": period, "interval": interval, "includePrePost": "false"},
        headers={"User-Agent": UA}, timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("chart", {}).get("result") or []
    if not results:
        raise ValueError(f"Yahoo returned no K-line result for {ticker.yahoo}")
    chart = results[0]
    chart_meta = chart.get("meta") or {}
    actual_symbol = chart_meta.get("symbol")
    if not actual_symbol or str(actual_symbol).upper() != ticker.yahoo.upper():
        raise ValueError(
            f"Yahoo K-line symbol mismatch: requested={ticker.yahoo}, returned={actual_symbol!r}"
        )
    actual_interval = chart_meta.get("dataGranularity")
    if actual_interval != interval:
        raise ValueError(
            f"Yahoo K-line interval mismatch: requested={interval}, returned={actual_interval!r}"
        )
    timestamps = chart.get("timestamp") or []
    quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
    rows = []
    for i, ts in enumerate(timestamps):
        close = _seq(quote.get("close"), i)
        if close is None:
            continue
        date_fmt = "%Y-%m-%d %H:%M" if re.fullmatch(r"\d+[mh]", interval) else "%Y-%m-%d"
        rows.append({
            "date": _dt.datetime.fromtimestamp(ts).strftime(date_fmt),
            "open": _round(_seq(quote.get("open"), i)),
            "high": _round(_seq(quote.get("high"), i)),
            "low": _round(_seq(quote.get("low"), i)),
            "close": _round(close),
            "volume": int(_seq(quote.get("volume"), i) or 0),
        })
    if not rows:
        raise ValueError(f"Yahoo returned no usable K-line rows for {ticker.yahoo}, interval={interval}")
    return rows


# ===========================================================================
# 新增: 腾讯 fqkline — A股/港股 K线 (前复权)
# ===========================================================================

def tencent_akline(symbol: str, count: int = 250, ktype: int = 9) -> dict[str, Any]:
    """腾讯 fqkline A股/港股 K线 (前复权).

    沙箱实测 (2026-09-04), 关键契约:
    - A股: param `sh600519,day,,,20,qfq` -> 返回 data["sh600519"]["qfqday"]
    - 港股: param `hk00700,day,,,20,qfq` -> 返回 data["hk00700"]["qfqday"]
           (注意: 港股符号是 `hk00700`, 不是 `r_hk00700`, 后者返回空)
    - 参数格式: <sym>,<period>,<start>,<end>,<count>,<末位flag> = 6 字段
    - 不复权日线: 末位传 "9" -> 返回键 "day" (前复权末位传 "qfq" -> 键 "qfqday")
    - 行结构 (A股): [date, open, close, high, low, vol] 仅 6 字段, 无 amount
    - 行结构 (港股): [date, open, close, high, low, vol, <event dict>] 7 字段

    参数 ktype: 9=前复权日线(default), 101=不复权日线, 102=周, 103=月；
                1/5/15/30/60 分钟参数保留兼容，但在上游契约确认前明确拒绝。
    """
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("K-line count must be a positive integer")
    meta = normalize_ticker(symbol)
    if meta.market not in {"cn", "hk"}:
        raise ValueError(
            f"tencent_akline 只支持 A股 / 港股 (got market={meta.market}); "
            f"美股/指数请用 yahoo_kline"
        )
    # 腾讯 fqkline 符号: A股 sh600519 / 港股 hk00700 (meta.tencent 已正确)
    tencent_sym = meta.tencent
    # ktype -> (period, 末位flag, 返回键)
    if ktype == 9:
        period, fqt, key = "day", "qfq", "qfqday"
    elif ktype == 101:
        period, fqt, key = "day", "9", "day"
    elif ktype == 102:
        period, fqt, key = "week", "qfq", "qfqweek"
    elif ktype == 103:
        period, fqt, key = "month", "qfq", "qfqmonth"
    elif ktype in (1, 5, 15, 30, 60):
        raise ValueError(
            f"Tencent minute ktype={ktype} is not enabled: the upstream parameter/response "
            "contract has not been confirmed, and implicit resampling is forbidden"
        )
    else:
        raise ValueError(f"Unsupported Tencent K-line ktype: {ktype}")
    # 6 字段: <sym>,<period>,<start>,<end>,<count>,<fqt>
    param = f"{tencent_sym},{period},,,{count},{fqt}"
    resp = requests.get(
        TENCENT_AKLINE_URL, params={"param": param},
        headers={"User-Agent": UA}, timeout=15,
    )
    resp.raise_for_status()
    d = resp.json()
    # 真实结构: d["data"][symbol][raw_key]
    data_node = (d.get("data") or {}).get(tencent_sym) or {}
    if key not in data_node:
        raise ValueError(
            f"Tencent K-line contract mismatch for {tencent_sym}: expected exact key={key!r} "
            f"for period={period}, adjustment={fqt}"
        )
    rows_raw = data_node[key]
    if not isinstance(rows_raw, list) or not rows_raw:
        raise ValueError(
            f"Tencent returned empty/malformed K-line rows for {tencent_sym}, "
            f"period={period}, adjustment={fqt}"
        )
    candidate_rows: list[dict[str, Any]] = []
    for row in rows_raw:
        if isinstance(row, (list, tuple)) and len(row) >= 6:
            candidate_rows.append({
                "date": row[0], "open": row[1], "close": row[2],
                "high": row[3], "low": row[4], "volume": row[5],
            })
        else:
            candidate_rows.append({})
    rows, row_metadata = _validated_recent_bars(candidate_rows, count)
    if not rows:
        raise ValueError(
            f"Tencent returned no usable K-line rows for {tencent_sym}, "
            f"period={period}, adjustment={fqt}"
        )
    # 名称: 从 qt 节点尽力提取
    name = None
    qt = (data_node.get("qt") or {}).get(tencent_sym)
    if qt:
        first = qt[0] if isinstance(qt, (list, tuple)) else qt
        if isinstance(first, str) and "~" in first:
            parts = first.split("~")
            name = parts[1] if len(parts) > 1 else None
        elif isinstance(qt, (list, tuple)) and len(qt) > 1 and isinstance(qt[1], str):
            name = qt[1]
    return {
        "rows": rows,
        "code": meta.code,
        "name": name,
        "market": meta.market,
        "source": "Tencent fqkline (前复权)" if fqt == "qfq" else "Tencent fqkline",
        "ktype": ktype,
        "period": period,
        "adjustment": "qfq" if fqt == "qfq" else "none",
        "count": len(rows),
        "request_param": param,
        "response_key": key,
        **row_metadata,
        "period_start": rows[0]["date"] if rows else None,
        "period_end": rows[-1]["date"] if rows else None,
    }


# ===========================================================================
# 新增: 东财 datacenter-web — 龙虎榜 / 融资融券 (共用 helper)
# ===========================================================================

def eastmoney_datacenter(
    report_name: str, columns: str = "ALL",
    filter_str: str = "", page_size: int = 50,
    sort_columns: str = "", sort_types: int = -1,
) -> list[dict[str, Any]]:
    """东财数据中心统一查询 — 龙虎榜 / 融资融券 / 解禁 / 大宗 / 分红 / 股东户数 共用.

    沙箱实测 (2026-09-04):
  - RPT_DAILYBILLBOARD_DETAILSNEW (龙虎榜) ✅
  - RPTA_WEB_RZRQ_GGMX (融资融券) ✅
  - RPT_LIFT_STAGE (解禁) ✅
  - RPT_HOLDERNUMLATEST (股东户数) ✅
  - RPT_SHAREBONUS_DET (分红) ✅
  - RPT_DATA_BLOCKTRADE (大宗交易) ✅
    """
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": str(sort_types),
        "source": "WEB", "client": "WEB",
    }
    r = requests.get(DATACENTER_URL, params=params,
                     headers={"User-Agent": UA}, timeout=15)
    r.raise_for_status()
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


def longhubang_daily(trade_date: str | None = None,
                     min_net_buy_wan: float | None = None) -> dict[str, Any]:
    """全市场龙虎榜 (东财 datacenter-web).

    参数:
      trade_date: YYYY-MM-DD, 默认今天
      min_net_buy_wan: 净买入下限 (万元), None=不过滤
    返回: {date, total, stocks: [{code, name, reason, close, change_pct,
            net_buy_wan, buy_wan, sell_wan, turnover_pct}],}
    """
    if trade_date is None:
        trade_date = _dt.date.today().strftime("%Y-%m-%d")
    rows = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
        page_size=500, sort_columns="BILLBOARD_NET_AMT", sort_types=-1,
    )
    if not rows:
        return {"date": trade_date, "total": 0, "stocks": [],
                "note": "无数据（非交易日或盘后未更新）"}
    actual_date = str(rows[0].get("TRADE_DATE", ""))[:10]
    stocks = []
    for row in rows:
        net_buy_wan = (row.get("BILLBOARD_NET_AMT") or 0) / 10000
        if min_net_buy_wan is not None and net_buy_wan < min_net_buy_wan:
            continue
        stocks.append({
            "code": row.get("SECURITY_CODE", ""),
            "name": row.get("SECURITY_NAME_ABBR", ""),
            "reason": row.get("EXPLANATION", ""),
            "close": row.get("CLOSE_PRICE"),
            "change_pct": _round2(row.get("CHANGE_RATE")),
            "net_buy_wan": _round2(net_buy_wan),
            "buy_wan": _round2((row.get("BILLBOARD_BUY_AMT") or 0) / 10000),
            "sell_wan": _round2((row.get("BILLBOARD_SELL_AMT") or 0) / 10000),
            "turnover_pct": _round2(row.get("TURNOVERRATE")),
        })
    return {"date": actual_date, "total": len(stocks), "stocks": stocks}


def longhubang_stock(code: str, days: int = 30) -> dict[str, Any]:
    """个股龙虎榜 (上榜记录 + 买卖席位 + 机构动向)."""
    today = _dt.date.today().strftime("%Y-%m-%d")
    start = (_dt.date.today() - _dt.timedelta(days=days)).strftime("%Y-%m-%d")

    records_raw = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{start}')(TRADE_DATE<='{today}')(SECURITY_CODE=\"{code}\")",
        page_size=50, sort_columns="TRADE_DATE", sort_types=-1,
    )
    records = [{
        "date": str(r.get("TRADE_DATE", ""))[:10],
        "reason": r.get("EXPLANATION", ""),
        "net_buy_wan": _round2((r.get("BILLBOARD_NET_AMT") or 0) / 10000),
        "turnover_pct": _round2(r.get("TURNOVERRATE")),
    } for r in records_raw]

    seats: dict[str, list[dict[str, Any]]] = {"buy": [], "sell": []}
    institution = {"buy_amt": 0, "sell_amt": 0, "net_amt": 0}
    buy_raw: list[dict[str, Any]] = []
    sell_raw: list[dict[str, Any]] = []
    if records:
        latest_date = records[0]["date"]
        buy_raw = eastmoney_datacenter(
            "RPT_BILLBOARD_DAILYDETAILSBUY",
            filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
            page_size=10, sort_columns="BUY", sort_types=-1,
        )
        sell_raw = eastmoney_datacenter(
            "RPT_BILLBOARD_DAILYDETAILSSELL",
            filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
            page_size=10, sort_columns="SELL", sort_types=-1,
        )
        for r in buy_raw[:5]:
            seats["buy"].append({
                "name": r.get("OPERATEDEPT_NAME", ""),
                "buy_amt_wan": _round2((r.get("BUY") or 0) / 10000),
                "sell_amt_wan": _round2((r.get("SELL") or 0) / 10000),
                "net_wan": _round2((r.get("NET") or 0) / 10000),
            })
        for r in sell_raw[:5]:
            seats["sell"].append({
                "name": r.get("OPERATEDEPT_NAME", ""),
                "buy_amt_wan": _round2((r.get("BUY") or 0) / 10000),
                "sell_amt_wan": _round2((r.get("SELL") or 0) / 10000),
                "net_wan": _round2((r.get("NET") or 0) / 10000),
            })
        buy_ids = {id(r) for r in buy_raw}
        for r in buy_raw:
            if str(r.get("OPERATEDEPT_CODE", "")) == "0":
                institution["buy_amt"] += (r.get("BUY") or 0)
        for r in sell_raw:
            if str(r.get("OPERATEDEPT_CODE", "")) == "0":
                institution["sell_amt"] += (r.get("SELL") or 0)
        institution["buy_amt"] = _round2(institution["buy_amt"] / 10000)
        institution["sell_amt"] = _round2(institution["sell_amt"] / 10000)
        institution["net_amt"] = _round2(institution["buy_amt"] - institution["sell_amt"])

    return {
        "code": code, "records_count": len(records),
        "records": records, "seats": seats, "institution": institution,
    }


def margin_trading(code: str, days: int = 30) -> list[dict[str, Any]]:
    """个股融资融券明细 (日级, 东财 datacenter-web). 单位: 元.

    沙箱实测 (2026-09-04): SCODE="600519" 可正常拉到 30 日明细 ✅
    """
    rows = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        filter_str=f'(SCODE="{code}")',
        page_size=days, sort_columns="DATE", sort_types=-1,
    )
    return [{
        "date": str(r.get("DATE", ""))[:10],
        "rz_balance_yuan": r.get("RZYE"),       # 融资余额 (元)
        "rz_buy_yuan": r.get("RZMRE"),         # 融资买入额
        "rz_repay_yuan": r.get("RZCHE"),       # 融资偿还额
        "rq_balance_yuan": r.get("RQYE"),      # 融券余额 (元)
        "rq_sell_shares": r.get("RQMCL"),      # 融券卖出量 (股)
        "rq_repay_shares": r.get("RQCHL"),     # 融券偿还量
        "rzrq_total_yuan": r.get("RZRQYE"),    # 融资融券余额合计
    } for r in rows]


# ===========================================================================
# corpaction (2026-09-04 新增：解禁/大宗交易/分红/股东户数)
# 复用已有 eastmoney_datacenter helper，过滤字段统一实测为 SECURITY_CODE。
# ===========================================================================

def lockup_expiry(code: str, page_size: int = 20) -> list[dict[str, Any]]:
    """限售解禁批次。茅台这类无近期解禁计划的老公司返回空属正常，非接口坏。"""
    rows = eastmoney_datacenter(
        "RPT_LIFT_STAGE", filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size, sort_columns="FREE_DATE", sort_types=-1,
    )
    return [{
        "free_date": str(r.get("FREE_DATE", ""))[:10],
        "free_shares_wan": _round2(r.get("FREE_SHARES")),
        "free_ratio_pct": _round2(r.get("FREE_RATIO")),
        "lift_market_cap_wan": _round2(r.get("LIFT_MARKET_CAP")),
        "shares_type": r.get("FREE_SHARES_TYPE"),
        "holder_count": r.get("BATCH_HOLDER_NUM"),
    } for r in rows]


def block_trades(code: str, page_size: int = 20) -> list[dict[str, Any]]:
    """大宗交易明细。"""
    rows = eastmoney_datacenter(
        "RPT_DATA_BLOCKTRADE", filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size, sort_columns="TRADE_DATE", sort_types=-1,
    )
    return [{
        "date": str(r.get("TRADE_DATE", ""))[:10],
        "deal_price": r.get("DEAL_PRICE"),
        "close_price": r.get("CLOSE_PRICE"),
        "premium_pct": _round2((r.get("PREMIUM_RATIO") or 0) * 100),
        "deal_volume_shares": r.get("DEAL_VOLUME"),
        "deal_amt_yuan": r.get("DEAL_AMT"),
        "buyer": r.get("BUYER_NAME"),
        "seller": r.get("SELLER_NAME"),
    } for r in rows]


def dividend_history(code: str, page_size: int = 20) -> list[dict[str, Any]]:
    """分红送转历史。"""
    rows = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET", filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size, sort_columns="PLAN_NOTICE_DATE", sort_types=-1,
    )
    return [{
        "plan_notice_date": str(r.get("PLAN_NOTICE_DATE", ""))[:10],
        "ex_dividend_date": str(r.get("EX_DIVIDEND_DATE", ""))[:10] if r.get("EX_DIVIDEND_DATE") else None,
        "bonus_ratio_per10": r.get("BONUS_RATIO"),      # 每10股送股
        "transfer_ratio_per10": r.get("BONUS_IT_RATIO"), # 每10股转增
        "cash_per10_yuan": r.get("PRETAX_BONUS_RMB"),    # 每10股派息(税前)
        "progress": r.get("ASSIGN_PROGRESS"),
    } for r in rows]


def holder_count_history(code: str, page_size: int = 20) -> list[dict[str, Any]]:
    """股东户数变化(筹码集中度信号)。"""
    rows = eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST", filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size, sort_columns="END_DATE", sort_types=-1,
    )
    return [{
        "end_date": str(r.get("END_DATE", ""))[:10],
        "holder_num": r.get("HOLDER_NUM"),
        "holder_num_change": r.get("HOLDER_NUM_CHANGE"),
        "holder_num_change_pct": _round2(r.get("HOLDER_NUM_RATIO")),
        "avg_hold_shares": r.get("AVG_HOLD_NUM"),
        "avg_market_cap_yuan": r.get("AVG_MARKET_CAP"),
    } for r in rows]


# ===========================================================================
# announcements (2026-09-04 新增：巨潮公告全文检索)
# ===========================================================================

def cninfo_announcements(code: str, page_size: int = 30) -> list[dict[str, Any]]:
    """巨潮公告全文检索。已知边界：688 科创板部分标的实测返回 0 条（688017 验证，
    非该股无公告——同一 orgId 构造模式对主板 600519 返回 1684 条），怀疑科创板
    org_id 前缀或需额外 plate 参数，未查清，遇到 688 段查询返回空时不要断言"无公告"，
    改用 web-harvest 查 cninfo 官网核实。"""
    code = str(code).zfill(6)
    if code.startswith(("4", "8", "92")):
        org_id = f"gsbj0{code}"  # 北交所；沿用 normalize_ticker 里验证过的号段判定
    elif code.startswith(("6", "9")):
        org_id = f"gssh0{code}"
    else:
        org_id = f"gssz0{code}"
    resp = requests.post(
        "https://www.cninfo.com.cn/new/hisAnnouncement/query",
        data={
            "stock": f"{code},{org_id}", "tabName": "fulltext",
            "pageSize": str(page_size), "pageNum": "1",
            "column": "", "category": "", "plate": "", "seDate": "",
            "searchkey": "", "secid": "", "sortName": "", "sortType": "",
            "isHLtitle": "true",
        },
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded",
                 "Referer": "https://www.cninfo.com.cn/new/disclosure",
                 "Origin": "https://www.cninfo.com.cn"},
        timeout=15,
    )
    resp.raise_for_status()
    d = resp.json()
    rows = []
    for item in d.get("announcements") or []:
        ts = item.get("announcementTime")
        date_str = _dt.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else None
        rows.append({
            "title": item.get("announcementTitle", ""),
            "type": item.get("announcementTypeName") or item.get("columnName"),
            "date": date_str,
            "url": f"https://www.cninfo.com.cn/new/disclosure/detail?annoId={item.get('announcementId', '')}",
        })
    return rows


# ===========================================================================
# institutional_holders (2026-09-04 新增：机构持仓，仅美股/港股，Yahoo quoteSummary)
# ===========================================================================

_YAHOO_SESSION: requests.Session | None = None


def _yahoo_session() -> requests.Session:
    """带 crumb 的 Yahoo session，跨调用复用（同一 CLI 进程内）。
    实测 2026-09-04：fc.yahoo.com 首步返回 404 不影响后续 crumb 获取，
    该步骤只是种 cookie，不是硬依赖，故意不对它的状态码做校验。"""
    global _YAHOO_SESSION
    if _YAHOO_SESSION is not None:
        return _YAHOO_SESSION
    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.get("https://fc.yahoo.com", timeout=10)
    r = s.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10)
    r.raise_for_status()
    s._crumb = r.text  # type: ignore[attr-defined]
    _YAHOO_SESSION = s
    return s


def institutional_holders(symbol: str) -> dict[str, Any]:
    """机构持仓概览 + 前10大机构。symbol: 'AAPL' 或 '0700.HK'（仅美股/港股，A股无覆盖）。"""
    s = _yahoo_session()
    resp = s.get(f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}",
                 params={"modules": "institutionOwnership,majorHoldersBreakdown",
                         "crumb": s._crumb}, timeout=15)  # type: ignore[attr-defined]
    resp.raise_for_status()
    results = resp.json().get("quoteSummary", {}).get("result") or [{}]
    data = results[0]
    mhb = data.get("majorHoldersBreakdown", {})

    def _v(d: dict, key: str) -> Any:
        v = d.get(key, {})
        return v.get("raw") if isinstance(v, dict) else v

    overview = {
        "insiders_pct": _round2((_v(mhb, "insidersPercentHeld") or 0) * 100),
        "institutions_pct": _round2((_v(mhb, "institutionsPercentHeld") or 0) * 100),
        "institutions_float_pct": _round2((_v(mhb, "institutionsFloatPercentHeld") or 0) * 100),
        "institutions_count": _v(mhb, "institutionsCount"),
    }
    top_holders = [{
        "name": h.get("organization"),
        "shares": _v(h, "position"),
        "value_usd": _v(h, "value"),
        "pct_held": _round2((_v(h, "pctHeld") or 0) * 100),
        "report_date": (h.get("reportDate") or {}).get("fmt") if isinstance(h.get("reportDate"), dict) else None,
    } for h in (data.get("institutionOwnership", {}).get("ownershipList") or [])[:10]]
    return {"symbol": symbol, "overview": overview, "top_holders": top_holders}


def eastmoney_reports(code: str, max_pages: int = 3) -> list[dict[str, Any]]:
    """东财个股研报列表(卖方观点，P2，不是事实——引用时必须标机构+日期，
    不得把评级/目标价/EPS预测写成既定结论)。含盈利预测(今年/明年/后年EPS+PE)和评级。"""
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Referer": "https://data.eastmoney.com/"})
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "50", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2000-01-01", "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": str(page), "pageNum": str(page), "pageNumber": str(page),
        }
        resp = session.get("https://reportapi.eastmoney.com/report/list",
                            params=params, timeout=30)
        resp.raise_for_status()
        d = resp.json()
        page_rows = d.get("data") or []
        if not page_rows:
            break
        for r in page_rows:
            rows.append({
                "title": r.get("title"),
                "org": r.get("orgSName"),
                "date": (r.get("publishDate") or "")[:10],
                "rating": r.get("emRatingName"),
                "rating_change": r.get("ratingChange"),  # 1新增/2维持/3调高/4调低/5首次覆盖等
                "researcher": r.get("researcher"),
                "eps_this_year": r.get("predictThisYearEps"),
                "eps_next_year": r.get("predictNextYearEps"),
                "pe_this_year": r.get("predictThisYearPe"),
                "pe_next_year": r.get("predictNextYearPe"),
                "pdf_url": f"https://pdf.dfcfw.com/pdf/H3_{r.get('infoCode', '')}_1.pdf" if r.get("infoCode") else None,
            })
        if page >= (d.get("TotalPage", 1) or 1):
            break
    return rows


def options_chain(symbol: str, expiration: int | None = None) -> dict[str, Any]:
    """期权链 calls+puts，仅美股(港股不在Yahoo期权覆盖范围会返回空)。
    expiration: Unix时间戳，不传则用最近到期日；expiration_dates给出全部可选到期日。"""
    s = _yahoo_session()
    params = {"crumb": s._crumb}  # type: ignore[attr-defined]
    if expiration:
        params["date"] = expiration
    resp = s.get(f"https://query2.finance.yahoo.com/v7/finance/options/{symbol}",
                 params=params, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("optionChain", {}).get("result") or [{}]
    oc = results[0]
    options = (oc.get("options") or [{}])[0] if oc.get("options") else {}

    def _v(o: dict, key: str) -> Any:
        v = o.get(key, {})
        return v.get("raw") if isinstance(v, dict) else v

    def _parse(opts: list) -> list[dict[str, Any]]:
        return [{
            "strike": _v(o, "strike"), "last_price": _v(o, "lastPrice"),
            "bid": _v(o, "bid"), "ask": _v(o, "ask"),
            "volume": _v(o, "volume"), "open_interest": _v(o, "openInterest"),
            "implied_volatility": _round2((_v(o, "impliedVolatility") or 0) * 100),
            "in_the_money": o.get("inTheMoney"), "contract_symbol": o.get("contractSymbol"),
        } for o in opts]

    return {
        "symbol": symbol, "underlying_price": oc.get("quote", {}).get("regularMarketPrice"),
        "expiration_dates": oc.get("expirationDates", []),
        "calls": _parse(options.get("calls") or []),
        "puts": _parse(options.get("puts") or []),
    }


# ===========================================================================
# fundflow / boardrank / hotstocks (2026-09-04 新增)
#
# push2.eastmoney.com / push2his.eastmoney.com 从本沙箱网络当前不可达
# （Remote end closed，非限流，见 SKILL.md「已知不可达源」）。同一 API 家族的
# push2delay.eastmoney.com（延迟行情域名）实测连通，clist/get 与
# stock/fflow/kline/get 两个端点在该域名下返回正常数据，改走这条路由。
# push2his 的日级 120 日资金流暂无可用替代域名（push2hisdelay 只返回网页,
# 非API），本次只接分钟级。
# ===========================================================================

PUSH2DELAY_URL = "https://push2delay.eastmoney.com"


def fund_flow_minute(code: str) -> list[dict[str, Any]]:
    """个股资金流向(分钟级,当日盘中)。单位:元。"""
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    resp = requests.get(
        f"{PUSH2DELAY_URL}/api/qt/stock/fflow/kline/get",
        params={"secid": secid, "klt": 1, "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57"},
        headers={"User-Agent": UA}, timeout=15,
    )
    resp.raise_for_status()
    klines = resp.json().get("data", {}).get("klines") or []
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 6:
            rows.append({
                "time": parts[0],
                "main_net_yuan": _float(parts, 1),
                "small_net_yuan": _float(parts, 2),
                "mid_net_yuan": _float(parts, 3),
                "large_net_yuan": _float(parts, 4),
                "super_net_yuan": _float(parts, 5),
            })
    return rows


_BOARD_FS = {"industry": "m:90 t:2", "concept": "m:90 t:3", "region": "m:90 t:1"}


def board_rank(kind: str, count: int = 20) -> list[dict[str, Any]]:
    """板块涨跌幅排名。kind: industry(行业) / concept(概念) / region(地域)。"""
    resp = requests.get(
        f"{PUSH2DELAY_URL}/api/qt/clist/get",
        params={"pn": 1, "pz": count, "po": 1, "fltt": 2, "invt": 2, "fid": "f3",
                "fields": "f12,f14,f3,f62", "fs": _BOARD_FS[kind]},
        headers={"User-Agent": UA}, timeout=15,
    )
    resp.raise_for_status()
    diff = resp.json().get("data", {}).get("diff") or {}
    items = diff.values() if isinstance(diff, dict) else diff
    return [{
        "code": it.get("f12"), "name": it.get("f14"),
        "change_pct": it.get("f3"), "main_net_yuan": it.get("f62"),
    } for it in items]


def ths_hot_reason(date: str | None = None) -> list[dict[str, Any]]:
    """同花顺当日强势股题材归因——不只告诉你"哪些走强"，还告诉你"为什么走强"
    （编辑部人工运营的题材标签，无近似替代源）。date: YYYY-MM-DD，默认今天。"""
    date = date or _dt.date.today().isoformat()
    resp = requests.get(
        f"http://zx.10jqka.com.cn/event/api/getharden/date/{date}/orderby/date/orderway/desc/charset/GBK/",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"},
        timeout=10,
    )
    resp.raise_for_status()
    d = resp.json()
    if d.get("errocode", 0) != 0:
        raise RuntimeError(f"同花顺热点错误: {d.get('errormsg', '')}")
    return [{
        "code": r.get("code"), "name": r.get("name"), "reason": r.get("reason"),
    } for r in (d.get("data") or [])]


# ===========================================================================
# indicator (2026-09-04 新增：技术指标 MA/MACD/RSI/KDJ/布林带)
# 纯本地计算，不调用新数据源；内部复用已有 kline 路由(A股/港股走腾讯fqkline，
# 美股/指数走Yahoo)取K线喂给指标函数，用户不必自己先拉K线再传参。
# ===========================================================================

def _ema_series(values: list[float], period: int) -> list[float]:
    result = [values[0]]
    k = 2 / (period + 1)
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _klines_for_indicator(symbol: str, count: int) -> list[dict[str, Any]]:
    meta = normalize_ticker(symbol)
    if meta.market in {"cn", "hk"}:
        return tencent_akline(symbol, count=count)["rows"]
    # Yahoo 用 period 而非 count；粗略换算，多取一些防止指标热身期不够
    days_needed = max(count * 2, 120)
    period = f"{days_needed}d" if days_needed <= 730 else "5y"
    return yahoo_kline(symbol, period, "1d")[-count:]


def calc_ma(klines: list[dict], periods: list[int] | None = None) -> list[dict[str, Any]]:
    periods = periods or [5, 10, 20, 60]
    closes = [k["close"] for k in klines]
    ema12, ema26 = _ema_series(closes, 12), _ema_series(closes, 26)
    result = []
    for i, k in enumerate(klines):
        row = {"date": k["date"], "close": k["close"]}
        for p in periods:
            row[f"ma{p}"] = round(sum(closes[i - p + 1:i + 1]) / p, 4) if i >= p - 1 else None
        row["ema12"], row["ema26"] = round(ema12[i], 4), round(ema26[i], 4)
        result.append(row)
    return result


def calc_macd(klines: list[dict], fast: int = 12, slow: int = 26, signal: int = 9) -> list[dict[str, Any]]:
    """dif=EMA(fast)-EMA(slow)，dea=EMA(signal) of dif，macd_hist=(dif-dea)*2。
    金叉/死叉看 dif 穿越 dea。"""
    closes = [k["close"] for k in klines]
    ema_fast, ema_slow = _ema_series(closes, fast), _ema_series(closes, slow)
    dif = [round(f - s, 4) for f, s in zip(ema_fast, ema_slow)]
    dea = _ema_series(dif, signal)
    return [{"date": k["date"], "close": k["close"], "dif": round(dif[i], 4),
             "dea": round(dea[i], 4), "macd_hist": round((dif[i] - dea[i]) * 2, 4)}
            for i, k in enumerate(klines)]


def calc_rsi(klines: list[dict], periods: list[int] | None = None) -> list[dict[str, Any]]:
    """>70 超买，<30 超卖。"""
    periods = periods or [6, 12, 24]
    closes = [k["close"] for k in klines]
    changes = [0.0] + [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    result = []
    for i, k in enumerate(klines):
        row = {"date": k["date"], "close": k["close"]}
        for p in periods:
            if i < p:
                row[f"rsi{p}"] = None
                continue
            avg_gain = sum(gains[i - p + 1:i + 1]) / p
            avg_loss = sum(losses[i - p + 1:i + 1]) / p
            row[f"rsi{p}"] = 100.0 if avg_loss == 0 else round(100 - 100 / (1 + avg_gain / avg_loss), 2)
        result.append(row)
    return result


def calc_kdj(klines: list[dict], n: int = 9, m1: int = 3, m2: int = 3) -> list[dict[str, Any]]:
    """K/D>80 超买，<20 超卖；J>100 或 J<0 极端；K上穿D金叉。"""
    k_val, d_val = 50.0, 50.0
    result = []
    for i, kline in enumerate(klines):
        if i < n - 1:
            result.append({"date": kline["date"], "close": kline["close"], "k": None, "d": None, "j": None})
            continue
        window = klines[i - n + 1:i + 1]
        high_n = max(w["high"] for w in window)
        low_n = min(w["low"] for w in window)
        rsv = (kline["close"] - low_n) / (high_n - low_n) * 100 if high_n != low_n else 50.0
        k_val = (1 / m1) * rsv + (1 - 1 / m1) * k_val
        d_val = (1 / m2) * k_val + (1 - 1 / m2) * d_val
        result.append({"date": kline["date"], "close": kline["close"],
                       "k": round(k_val, 2), "d": round(d_val, 2), "j": round(3 * k_val - 2 * d_val, 2)})
    return result


def calc_boll(klines: list[dict], period: int = 20, num_std: float = 2.0) -> list[dict[str, Any]]:
    """触 upper 超买/触 lower 超卖；bandwidth 收窄→即将变盘。"""
    closes = [k["close"] for k in klines]
    result = []
    for i, k in enumerate(klines):
        if i < period - 1:
            result.append({"date": k["date"], "close": k["close"],
                           "upper": None, "middle": None, "lower": None, "bandwidth": None})
            continue
        window = closes[i - period + 1:i + 1]
        ma = sum(window) / period
        std = (sum((x - ma) ** 2 for x in window) / period) ** 0.5
        upper, lower = ma + num_std * std, ma - num_std * std
        result.append({"date": k["date"], "close": k["close"], "upper": round(upper, 4),
                       "middle": round(ma, 4), "lower": round(lower, 4),
                       "bandwidth": round((upper - lower) / ma * 100, 2) if ma else None})
    return result


_INDICATOR_FUNCS = {"ma": calc_ma, "macd": calc_macd, "rsi": calc_rsi,
                     "kdj": calc_kdj, "boll": calc_boll}


# ===========================================================================
# search / sec (保留, 未改动)
# ===========================================================================

def eastmoney_search(keyword: str, count: int) -> list[dict[str, Any]]:
    """全球股票代码搜索。

    2026-09-04 替换：原东财 searchapi.eastmoney.com/api/suggest/get?type=14 端点
    已被后端改造为股吧用户/帖子搜索（返回 passportWeb 结构，与股票代码无关），
    对任意输入都返回同一组缓存结果，说明该 type=14 语义已失效，非临时抖动。
    改用腾讯 smartbox（与本 skill A股/港股/美股行情同源，见 SKILL.md 数据源优先级），
    零鉴权，返回 market~code~name~pinyin~type 竖线分隔多结果。
    """
    resp = requests.get(
        "http://smartbox.gtimg.cn/s3/",
        params={"t": "all", "q": keyword},
        headers={"User-Agent": UA}, timeout=10,
    )
    resp.raise_for_status()
    market_map = {
        "sh": "A股沪市", "sz": "A股深市", "bj": "A股北交所",
        "hk": "HK", "us": "US", "jj": "基金",
    }
    text = resp.text
    start = text.find('"')
    end = text.rfind('"')
    # smartbox 用 JS 字符串字面量转义中文（\uXXXX），与 JSON 字符串转义语法相同，
    # 直接用 json 解码整个带引号片段即可还原真实汉字，不用手写 unicode_escape。
    body = json.loads(text[start:end + 1]) if start != -1 and end > start else ""
    rows = []
    for entry in body.split("^"):
        if not entry:
            continue
        parts = entry.split("~")
        if len(parts) < 5:
            continue
        mkt, code, name, pinyin, sec_type = parts[0], parts[1], parts[2], parts[3], parts[4]
        rows.append({
            "code": code, "name": name, "pinyin": pinyin,
            "market": market_map.get(mkt, mkt), "security_type": sec_type,
        })
        if len(rows) >= count:
            break
    return rows


_CIK_CACHE: dict[str, Any] | None = None


def ticker_to_cik(ticker: str) -> dict[str, Any]:
    global _CIK_CACHE
    if _CIK_CACHE is None:
        resp = requests.get("https://www.sec.gov/files/company_tickers.json",
                            headers=SEC_HEADERS, timeout=15)
        resp.raise_for_status()
        _CIK_CACHE = resp.json()
    ticker_upper = ticker.upper().replace("-", ".")
    for item in _CIK_CACHE.values():
        if item.get("ticker") == ticker_upper:
            return {"ticker": ticker_upper,
                    "cik": str(item["cik_str"]).zfill(10),
                    "company": item.get("title")}
    return {}


def sec_xbrl(cik: str, metrics: list[str]) -> dict[str, Any]:
    resp = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                        headers=SEC_HEADERS, timeout=20)
    resp.raise_for_status()
    facts = resp.json()
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    result = {}
    metric_metadata = {}
    if not metrics:
        available_metrics = [
            {
                "name": name,
                "label": fact.get("label", name),
                "units": list(fact.get("units", {}).keys()),
            }
            for name, fact in us_gaap.items()
        ]
        return {"company": facts.get("entityName"),
                "total_metrics": len(available_metrics),
                "available_metrics": available_metrics,
                "available_metric_names": sorted(us_gaap.keys())}
    for metric in metrics:
        units = us_gaap.get(metric, {}).get("units", {})
        if not units:
            result[metric] = []
            metric_metadata[metric] = {
                "source_entries": 0,
                "returned_entries": 0,
                "filtered_out_entries": 0,
                "truncated": False,
                "units": [],
                "derivation": "none",
            }
            continue
        entries = []
        for unit, unit_entries in units.items():
            for entry in unit_entries:
                if entry.get("form") not in {"10-K", "10-Q"}:
                    continue
                # Keep the old flat list and preserve every upstream fact field in place.
                preserved = {"concept": metric, "unit": unit, **entry}
                for field in ("start", "end", "val", "filed", "accn", "form", "fy", "fp", "frame"):
                    preserved.setdefault(field, None)
                entries.append(preserved)
        result[metric] = entries
        metric_metadata[metric] = {
            "source_entries": sum(len(v) for v in units.values()),
            "returned_entries": len(entries),
            "filtered_out_entries": sum(len(v) for v in units.values()) - len(entries),
            "truncated": False,
            "units": list(units.keys()),
            "derivation": "none",
        }
    return {
        "company": facts.get("entityName"),
        "metrics": result,
        "metric_metadata": metric_metadata,
    }


# ===========================================================================
# swindustry (2026-09-04 新增：申万行业分类变迁史，消除回测前视偏差)
# ===========================================================================

SW_URL = "https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls"
# swsresearch.com 服务端只发叶子证书、不发中间证书（openssl s_client 实测确认），
# 违反 TLS 最佳实践但站点本身有效；requests/urllib3 不像浏览器会自动通过 AIA 补链。
# 从叶子证书 Authority Information Access 字段取官方中间证书 URL 补全验证链，
# 而不是 verify=False 关闭校验——这是修复根因，不是绕过安全检查。
SW_INTERMEDIATE_CA_URL = "http://cacerts.digicert.cn/GeoTrustG2TLSCNRSA4096SHA2562022CA1.crt"
_SW_CACHE_DIR = _Path(__file__).parent / ".cache"
_SW_CACHE_FILE = _SW_CACHE_DIR / "sw_industry_history.json"
_SW_CACHE_TTL_DAYS = 7  # 申万行业调整频率低，一周内复用缓存，不必每次拉 1.1MB


def _sw_ca_bundle() -> str:
    """certifi 默认包 + swsresearch.com 缺失的中间证书，合并成一份可复用的 CA bundle。"""
    bundle_path = _SW_CACHE_DIR / "combined_ca_bundle.pem"
    if bundle_path.exists():
        return str(bundle_path)
    import certifi
    _SW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    intermediate = requests.get(SW_INTERMEDIATE_CA_URL, timeout=15)
    intermediate.raise_for_status()
    # DigiCert CA Issuers URL 返回 DER 编码，需转 PEM 才能拼进证书包
    import ssl as _ssl
    pem_intermediate = _ssl.DER_cert_to_PEM_cert(intermediate.content)
    with open(certifi.where(), "rb") as f:
        base = f.read()
    with open(bundle_path, "wb") as f:
        f.write(base + b"\n" + pem_intermediate.encode())
    return str(bundle_path)


def sw_industry_history(force_refresh: bool = False) -> list[dict[str, Any]]:
    """申万行业归属变迁史：每只股票每次行业调整一行。零第三方 pip 依赖之外
    只用已内置的 pandas/xlrd/openpyxl（无需新装）。磁盘缓存 7 天。"""
    if not force_refresh and _SW_CACHE_FILE.exists():
        age_days = (time.time() - _SW_CACHE_FILE.stat().st_mtime) / 86400
        if age_days < _SW_CACHE_TTL_DAYS:
            return json.loads(_SW_CACHE_FILE.read_text())

    import pandas as pd
    resp = requests.get(SW_URL, headers={"User-Agent": UA}, timeout=60,
                         verify=_sw_ca_bundle())
    resp.raise_for_status()
    import io as _io
    df = pd.read_excel(_io.BytesIO(resp.content))
    df = df.rename(columns={"股票代码": "code", "计入日期": "start_date",
                             "行业代码": "industry_code", "更新日期": "update_date"})
    missing = {"code", "start_date", "industry_code"} - set(df.columns)
    if missing:
        raise RuntimeError(f"申万表结构变了，缺列 {sorted(missing)}；实际列={list(df.columns)}")
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["industry_code"] = df["industry_code"].astype(str).str.zfill(6)
    df["l1_code"] = df["industry_code"].str[:2] + "0000"
    df["l2_code"] = df["industry_code"].str[:4] + "00"
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df = df.sort_values(["code", "start_date"]).reset_index(drop=True)
    rows = [{
        "code": r["code"], "industry_code": r["industry_code"],
        "l1_code": r["l1_code"], "l2_code": r["l2_code"],
        "start_date": r["start_date"].strftime("%Y-%m-%d") if pd.notna(r["start_date"]) else None,
    } for _, r in df.iterrows()]

    _SW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _SW_CACHE_FILE.write_text(json.dumps(rows, ensure_ascii=False))
    return rows


def sw_industry_as_of(code: str, as_of: str | None = None) -> dict[str, Any] | None:
    """某只股票在 as_of 日（默认今天）所属的申万行业，取不晚于该日的最后一次调整。
    用于避免行业轮动回测的前视偏差——不是查"现在属于哪个行业"，是查"当时属于哪个行业"。"""
    code = str(code).zfill(6)
    as_of = as_of or _dt.date.today().isoformat()
    rows = sw_industry_history()
    candidates = [r for r in rows if r["code"] == code and r["start_date"] and r["start_date"] <= as_of]
    if not candidates:
        return None
    return sorted(candidates, key=lambda r: r["start_date"])[-1]


# ===========================================================================
# baostock (2026-09-04 新增：估值历史 PE/PB/PS/PCF + 上市/退市日期。
# 作者已确认安装 baostock pip 包，装在系统 python3（非 quant-check 隔离venv）。
# baostock 不支持北交所（服务端报 10004011），调用前拦截并给出明确错误。
# ===========================================================================

def _bs_code(code: str) -> str:
    code = str(code).zfill(6)
    if code[:2] in ("60", "68", "90"):
        return f"sh.{code}"
    if code[:2] in ("00", "30", "20"):
        return f"sz.{code}"
    raise ValueError(f"baostock 不支持北交所标的: {code}（服务端错误码 10004011），"
                      f"估值历史/上市退市日期这两项对北交所标的没有替代源")


class _bs_session:
    """baostock 登录会话；默认往 stdout 打登录横幅，会污染 CLI 的 JSON 输出，
    进出都吞掉打印内容，只保留真实异常。"""

    def __enter__(self):
        import baostock as bs
        import contextlib
        import io as _io
        self._bs = bs
        with contextlib.redirect_stdout(_io.StringIO()):
            lg = bs.login()
        if lg.error_code != "0":
            raise RuntimeError(f"baostock 登录失败: {lg.error_code} {lg.error_msg}")
        return bs

    def __exit__(self, *exc):
        import contextlib
        import io as _io
        with contextlib.redirect_stdout(_io.StringIO()):
            self._bs.logout()
        return False


_BS_VALUATION_FIELDS = "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn,tradestatus,isST"


def baostock_valuation_history(code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """估值历史序列：date/pe/pb/ps/pcf/换手率/ST/停牌，可回溯到 2016 年附近。

    2026-09-04 修正：一开始按上游文档写成 `query_estimate_detail`，实测该函数在
    当前 baostock 包里不存在（`hasattr(bs, ...)` 返回 False）；真实入口是
    `query_history_k_data_plus` 传 PE/PB/PS/PCF 相关 fields，字段名（peTTM 等）
    经实测有效，adjustflag=3(不复权) 因为估值比率要对应真实收盘价而非复权价。
    """
    bs_code = _bs_code(code)
    with _bs_session() as bs:
        rs = bs.query_history_k_data_plus(
            bs_code, _BS_VALUATION_FIELDS,
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="3",
        )
        if rs.error_code != "0":
            raise RuntimeError(f"查询失败: {rs.error_code} {rs.error_msg}")
        fields = rs.fields
        rows = []
        while rs.next():
            row = dict(zip(fields, rs.get_row_data()))
            rows.append({
                "date": row.get("date"),
                "close": _float([row.get("close", "")], 0),
                "pe": _float([row.get("peTTM", "")], 0),
                "pb": _float([row.get("pbMRQ", "")], 0),
                "ps": _float([row.get("psTTM", "")], 0),
                "pcf": _float([row.get("pcfNcfTTM", "")], 0),
                "turnover_rate": _float([row.get("turn", "")], 0),
                "is_st": row.get("isST") == "1",
                "trade_status": "正常" if row.get("tradestatus") == "1" else "停牌",
            })
    return rows


def baostock_stock_basic(code: str) -> dict[str, Any]:
    """标的基本信息：上市日、退市日（空=仍在市）、状态。"""
    bs_code = _bs_code(code)
    with _bs_session() as bs:
        rs = bs.query_stock_basic(code=bs_code)
        if rs.error_code != "0":
            raise RuntimeError(f"查询失败: {rs.error_code} {rs.error_msg}")
        if not rs.next():
            raise ValueError(f"标的未找到: {code}")
        row = dict(zip(rs.fields, rs.get_row_data()))
    return {
        "code": row.get("code"), "name": row.get("code_name"),
        "ipo_date": row.get("ipoDate") or None,
        "delist_date": row.get("outDate") or None,
        "status": "正常" if row.get("status") == "1" else "已退市",
    }


# ===========================================================================
# chip_distribution (2026-09-04 新增：筹码分布，纯本地推演)
#
# 自己按公开通用算法实现，不是从任何第三方源转述——本会话已两次发现 WebFetch
# 对第三方文档做 AI 摘要时会编造细节（申万行业史 URL、baostock 函数名），
# 这次摘要给的筹码分布代码依赖一个未给出定义的 _triangular_weights 辅助函数，
# 无法验证正确性，故未采用，改自己写。算法是标准公开方法：每日成交按换手率对
# 现有筹码分布做"以新换旧"混合，新增部分在当日 [low, high] 区间内按三角分布
# （峰值在 (high+low+close)/3）撒开。数据源用 baostock（已验证的 valuation
# 命令同一入口），一次拿到 date/high/low/close/turn，不必再拼接两个数据源。
# ===========================================================================

def _triangular_weights(grid: "np.ndarray", low: float, high: float, peak: float) -> "np.ndarray":
    """三角分布权重：[low, high] 区间内 0，峰值在 peak，两侧线性递减到 0。"""
    import numpy as np
    w = np.zeros_like(grid)
    if high <= low:
        idx = (np.abs(grid - low)).argmin()
        w[idx] = 1.0
        return w
    peak = min(max(peak, low), high)
    left = (grid >= low) & (grid <= peak)
    right = (grid > peak) & (grid <= high)
    if peak > low:
        w[left] = (grid[left] - low) / (peak - low)
    else:
        w[left] = 1.0
    if high > peak:
        w[right] = (high - grid[right]) / (high - peak)
    else:
        w[right] = 1.0
    return w


def chip_distribution(code: str, start_date: str, end_date: str,
                       grid_size: int = 300) -> dict[str, Any]:
    """筹码分布：获利比例、平均成本、90%/70%成本集中区间、筹码峰值价。
    不支持北交所（同 baostock 限制）。历史区间越长越接近真实筹码结构，
    但早期换手会被后续交易持续稀释，一般 1-2 年历史足够收敛。"""
    import numpy as np
    bs_code = _bs_code(code)
    with _bs_session() as bs:
        rs = bs.query_history_k_data_plus(
            bs_code, "date,high,low,close,turn,tradestatus",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="3",
        )
        if rs.error_code != "0":
            raise RuntimeError(f"查询失败: {rs.error_code} {rs.error_msg}")
        fields = rs.fields
        days = []
        while rs.next():
            row = dict(zip(fields, rs.get_row_data()))
            if row.get("tradestatus") != "1":
                continue  # 停牌日无真实换手，跳过
            try:
                days.append({
                    "date": row["date"], "high": float(row["high"]),
                    "low": float(row["low"]), "close": float(row["close"]),
                    "turn": float(row["turn"]),
                })
            except (ValueError, KeyError):
                continue
    if len(days) < 5:
        raise ValueError(f"{code} 有效交易日不足5天({len(days)})，筹码分布不可靠")

    lo = min(d["low"] for d in days)
    hi = max(d["high"] for d in days)
    pad = (hi - lo) * 0.02 or max(lo * 0.02, 0.01)
    grid = np.linspace(lo - pad, hi + pad, grid_size)

    chips: "np.ndarray | None" = None
    for d in days:
        turn_frac = min(max(d["turn"] / 100.0, 0.0), 1.0)
        peak = (d["high"] + d["low"] + d["close"]) / 3.0
        day_w = _triangular_weights(grid, d["low"], d["high"], peak)
        if day_w.sum() <= 0:
            continue
        day_w = day_w / day_w.sum()
        chips = day_w if chips is None else chips * (1.0 - turn_frac) + day_w * turn_frac

    if chips is None or chips.sum() <= 0:
        raise RuntimeError(f"{code} 换手率数据全为0或缺失，无法推演筹码分布")
    chips = chips / chips.sum()

    last_price = days[-1]["close"]
    cum = np.cumsum(chips)

    def _price_at(q: float) -> float:
        return float(np.interp(q, cum, grid))

    peak_idx = int(np.argmax(chips))
    return {
        "code": code, "as_of": days[-1]["date"], "price": last_price,
        "profit_ratio_pct": _round2(float(chips[grid <= last_price].sum()) * 100),
        "avg_cost": _round2(float((grid * chips).sum())),
        "cost_90pct_low": _round2(_price_at(0.05)), "cost_90pct_high": _round2(_price_at(0.95)),
        "cost_70pct_low": _round2(_price_at(0.15)), "cost_70pct_high": _round2(_price_at(0.85)),
        "peak_price": _round2(float(grid[peak_idx])),
        "days_used": len(days),
    }


# ===========================================================================
# market_margin (2026-09-04 新增：全市场两融余额历史)
# 已有 margin 命令是个股明细；这是全 A 汇总，页面 JS 反查到真实 reportName，
# 未曾发布在任何公开文档，属本次现场发现。
# ===========================================================================

def market_margin_history(days: int = 20) -> list[dict[str, Any]]:
    """全 A 两融余额历史（沪深北合计）。RZYE=融资余额, RQYE=融券余额,
    RZRQYE=两融总余额, RZYEZB=融资余额占流通市值比例(%)。单位:元。"""
    rows = eastmoney_datacenter(
        "RPTA_RZRQ_LSHJ", page_size=days,
        sort_columns="DIM_DATE", sort_types=-1,
    )
    return [{
        "date": str(r.get("DIM_DATE", ""))[:10],
        "rz_balance_yuan": r.get("RZYE"),
        "rz_balance_pct_of_float_cap": _round2(r.get("RZYEZB")),
        "rz_buy_yuan": r.get("RZMRE"),
        "rz_net_buy_yuan": r.get("RZJME"),
        "rq_balance_yuan": r.get("RQYE"),
        "rzrq_total_yuan": r.get("RZRQYE"),
        "rzrq_total_change_yuan": r.get("RZRQYECZ"),
    } for r in rows]


# ===========================================================================
# newsflash (2026-09-04 新增：全市场实时快讯，替换失效的财联社电报)
# ===========================================================================

NEWSFLASH_URL = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"


def eastmoney_newsflash(count: int = 20) -> list[dict[str, Any]]:
    """全市场实时快讯。原财联社电报 `cls.cn/nodeapi/telegraphList` 已 404（接口废弃，
    非签名过期），换东财 np-weblist（与个股新闻同一服务簇），已实测返回真实快讯，
    含关联股票代码 `related_codes`。"""
    resp = requests.get(
        NEWSFLASH_URL,
        params={"client": "web", "biz": "web_724", "fastColumn": 102,
                "sortEnd": "", "pageSize": count, "req_trace": "1"},
        headers={"User-Agent": UA, "Referer": "https://finance.eastmoney.com/"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    rows = []
    for item in data.get("fastNewsList", []) or []:
        rows.append({
            "time": item.get("showTime"),
            "title": item.get("title"),
            "summary": item.get("summary"),
            "related_codes": item.get("stockList") or [],
        })
    return rows


# ===========================================================================
# CLI
# ===========================================================================

_QUOTE_REQUIRED_FIELDS = ("source", "market", "code", "price", "market_at")


def _quote_validation_reason(payload: Any) -> str | None:
    if not isinstance(payload, dict) or not payload:
        return "quote_missing"
    for field in _QUOTE_REQUIRED_FIELDS:
        if payload.get(field) is None or payload.get(field) == "":
            return f"{field}_missing"
    return None


def build_quote_report(symbols: list[NormalizedTicker]) -> tuple[dict[str, Any], int]:
    """Fetch quotes with per-ticker validation while preserving the legacy quote fields."""
    retrieved_at = _utc_now_iso()
    primary: dict[str, dict[str, Any]] = {}
    primary_reasons: dict[str, str] = {}
    primary_errors: dict[str, str] = {}
    tencent_symbols = [s for s in symbols if s.market in {"cn", "hk", "us"}]
    yahoo_primary_symbols = [s for s in symbols if s.market == "index"]

    if tencent_symbols:
        try:
            primary.update(tencent_quotes(tencent_symbols))
        except Exception as exc:
            for symbol in tencent_symbols:
                primary_reasons[symbol.raw] = "primary_error"
                primary_errors[symbol.raw] = str(exc)[:300]
    if yahoo_primary_symbols:
        try:
            primary.update(yahoo_quotes(yahoo_primary_symbols))
        except Exception as exc:
            for symbol in yahoo_primary_symbols:
                primary_reasons[symbol.raw] = "primary_error"
                primary_errors[symbol.raw] = str(exc)[:300]

    for symbol in symbols:
        primary_reasons.setdefault(symbol.raw, _quote_validation_reason(primary.get(symbol.raw)) or "primary_ok")

    fallback_targets = [
        symbol for symbol in tencent_symbols if primary_reasons[symbol.raw] != "primary_ok"
    ]
    fallback: dict[str, dict[str, Any]] = {}
    fallback_error: str | None = None
    if fallback_targets:
        try:
            fallback = yahoo_quotes(fallback_targets)
        except Exception as exc:
            fallback_error = str(exc)[:300]

    quotes: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        primary_reason = primary_reasons[symbol.raw]
        if primary_reason == "primary_ok":
            payload = dict(primary[symbol.raw])
            status = "ok"
            reason_code = "primary_ok"
            reason = None
        elif symbol in fallback_targets:
            fallback_payload = fallback.get(symbol.raw)
            fallback_reason = _quote_validation_reason(fallback_payload)
            if fallback_reason is None:
                payload = dict(fallback_payload or {})
                status = "ok"
                reason_code = f"fallback_after_{primary_reason}"
                reason = primary_errors.get(symbol.raw)
            else:
                payload = dict(fallback_payload or primary.get(symbol.raw) or {})
                status = "error"
                reason_code = (
                    "fallback_error_after_" + primary_reason
                    if fallback_error
                    else f"fallback_{fallback_reason}_after_{primary_reason}"
                )
                reason = fallback_error or primary_errors.get(symbol.raw)
        else:
            payload = dict(primary.get(symbol.raw) or {})
            status = "error"
            reason_code = f"{primary_reason}_no_fallback"
            reason = primary_errors.get(symbol.raw)

        # Compatibility: retain legacy fields and add uniform provenance/status keys.
        payload.setdefault("source", None)
        payload.setdefault("market", symbol.market)
        payload.setdefault("code", symbol.code)
        payload.setdefault("market_at", None)
        if not payload.get("retrieved_at"):
            payload["retrieved_at"] = retrieved_at
        payload["status"] = status
        payload["reason_code"] = reason_code
        if reason:
            payload["reason"] = reason
        quotes[symbol.raw] = payload

    ok_count = sum(1 for quote in quotes.values() if quote["status"] == "ok")
    error_count = len(quotes) - ok_count
    status = "ok" if not error_count else "partial" if ok_count else "error"
    market_times = [
        quote["market_at"] for quote in quotes.values()
        if quote["status"] == "ok" and quote.get("market_at")
    ]
    report = {
        # Legacy `as_of` remains, but now comes only from upstream market timestamps.
        "as_of": max(market_times) if market_times else None,
        "retrieved_at": retrieved_at,
        "status": status,
        "reason_code": {
            "ok": "all_quotes_ok", "partial": "some_quotes_failed", "error": "all_quotes_failed",
        }[status],
        "ok_count": ok_count,
        "error_count": error_count,
        "quotes": quotes,
    }
    return report, 0 if ok_count else 1


def cmd_quote(args: argparse.Namespace) -> int:
    symbols = [normalize_ticker(s) for s in args.symbols]
    report, exit_code = build_quote_report(symbols)
    print_json(report)
    return exit_code


def cmd_kline(args: argparse.Namespace) -> int:
    """智能路由 K线: A股/港股 → 腾讯 fqkline (前复权), 美股/指数 → Yahoo.

    沙箱实测 (2026-09-04): A股/港股走 fqkline 准确度优于 Yahoo (Yahoo A股数据残缺/延迟).
    """
    meta = normalize_ticker(args.symbol)
    if meta.market in {"cn", "hk"}:
        interval_to_ktype = {"1d": 9, "1wk": 102, "1mo": 103}
        minute_to_ktype = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}
        if args.interval in minute_to_ktype:
            ktype = minute_to_ktype[args.interval]
        elif args.interval in interval_to_ktype:
            ktype = interval_to_ktype[args.interval]
        else:
            raise ValueError(f"Unsupported A/H K-line interval: {args.interval}")
        result = tencent_akline(args.symbol, count=args.count, ktype=ktype)
        # 拆分 result 字段以便与 Yahoo kline 输出兼容
        rows = result.pop("rows")
        print_json({
            "symbol": args.symbol, "market": meta.market,
            "source": result.pop("source"),
            "code": result.get("code"), "name": result.get("name"),
            "period_start": result.get("period_start"),
            "period_end": result.get("period_end"),
            "ktype": result.get("ktype"),
            "period": result.get("period"),
            "interval": args.interval,
            "adjustment": result.get("adjustment"),
            "rows": rows,
        })
    else:
        rows = yahoo_kline(args.symbol, args.period, args.interval)
        print_json({"symbol": args.symbol, "source": "Yahoo",
                    "period": args.period, "interval": args.interval,
                    "adjustment": "none", "rows": rows})
    return 0


def cmd_akline(args: argparse.Namespace) -> int:
    """显式调用腾讯 fqkline (A股/港股 前复权 K线)."""
    result = tencent_akline(args.symbol, count=args.count, ktype=args.ktype)
    print_json({"symbol": args.symbol, **result})
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    print_json({"keyword": args.keyword, "results": eastmoney_search(args.keyword, args.count)})
    return 0


def cmd_sec(args: argparse.Namespace) -> int:
    info = ticker_to_cik(args.ticker)
    if not info:
        raise SystemExit(f"CIK not found for ticker: {args.ticker}")
    payload = {"company": info}
    if args.metrics is not None:
        payload["xbrl"] = sec_xbrl(info["cik"], args.metrics)
    print_json(payload)
    return 0


def cmd_longhubang(args: argparse.Namespace) -> int:
    """龙虎榜 — 全市场 (默认) / 个股 (传 --code).

    用法:
      longhubang                       # 今日全市场龙虎榜
      longhubang --date 2026-09-03     # 指定日期
      longhubang --min-net-buy 5000    # 净买入 > 5000 万
      longhubang --code 002475 --days 30  # 个股近 30 日
    """
    if args.code:
        result = longhubang_stock(args.code, days=args.days)
    else:
        result = longhubang_daily(
            args.date,
            min_net_buy_wan=args.min_net_buy if args.min_net_buy > 0 else None,
        )
    print_json(result)
    return 0


def cmd_margin(args: argparse.Namespace) -> int:
    """个股融资融券明细 (日级). 用法: margin 600519 --days 30."""
    print_json({"code": args.code,
                "rows": margin_trading(args.code, days=args.days)})
    return 0


def cmd_swindustry(args: argparse.Namespace) -> int:
    """申万行业分类变迁史（避免回测/归因前视偏差）。

    用法:
      swindustry --code 000001 --asof 2016-01-01   # 该日归属哪个申万行业
      swindustry --code 000001                     # 默认查今天
      swindustry --dump                            # 全量导出（约1.3万行，慎用）
      swindustry --refresh --code 000001           # 强制重新下载(忽略7天缓存)
    """
    if args.refresh:
        sw_industry_history(force_refresh=True)
    if args.dump:
        rows = sw_industry_history()
        print_json({"count": len(rows), "rows": rows})
        return 0
    if not args.code:
        raise SystemExit("swindustry 需要 --code 或 --dump 之一")
    result = sw_industry_as_of(args.code, args.asof)
    print_json({"code": args.code, "as_of": args.asof or _dt.date.today().isoformat(),
                "industry": result})
    return 0


def cmd_valuation(args: argparse.Namespace) -> int:
    """估值历史(PE/PB/PS/PCF). 用法: valuation 600519 --start 2020-01-01 --end 2026-08-19."""
    rows = baostock_valuation_history(args.code, args.start, args.end)
    print_json({"code": args.code, "start": args.start, "end": args.end,
                "count": len(rows), "rows": rows})
    return 0


def cmd_basic(args: argparse.Namespace) -> int:
    """上市/退市日期与状态. 用法: basic 600519."""
    print_json(baostock_stock_basic(args.code))
    return 0


def cmd_chip(args: argparse.Namespace) -> int:
    """筹码分布(获利比例/成本区间/峰值价). 用法: chip 600519 --start 2025-01-01."""
    print_json(chip_distribution(args.code, args.start, args.end))
    return 0


def cmd_marketmargin(args: argparse.Namespace) -> int:
    """全A两融余额历史(沪深北合计). 用法: marketmargin --days 20."""
    print_json({"days": args.days, "rows": market_margin_history(args.days)})
    return 0


def cmd_newsflash(args: argparse.Namespace) -> int:
    """全市场实时快讯(替代已404的财联社电报). 用法: newsflash --count 20."""
    print_json({"count": args.count, "rows": eastmoney_newsflash(args.count)})
    return 0


_CORPACTION_FUNCS = {
    "lockup": lockup_expiry, "block": block_trades,
    "dividend": dividend_history, "holders": holder_count_history,
}


def cmd_corpaction(args: argparse.Namespace) -> int:
    """解禁(lockup) / 大宗交易(block) / 分红(dividend) / 股东户数(holders).
    用法: corpaction 600519 --type lockup"""
    fn = _CORPACTION_FUNCS[args.type]
    print_json({"code": args.code, "type": args.type,
                "rows": fn(args.code, args.count)})
    return 0


def cmd_announcements(args: argparse.Namespace) -> int:
    """巨潮公告全文检索. 用法: announcements 600519 --count 20."""
    print_json({"code": args.code, "rows": cninfo_announcements(args.code, args.count)})
    return 0


def cmd_holders(args: argparse.Namespace) -> int:
    """机构持仓(仅美股/港股). 用法: holders AAPL / holders 0700.HK."""
    print_json(institutional_holders(args.symbol))
    return 0


def cmd_fundflow(args: argparse.Namespace) -> int:
    """个股资金流分钟级(当日盘中). 用法: fundflow 600519."""
    print_json({"code": args.code, "rows": fund_flow_minute(args.code)})
    return 0


def cmd_boardrank(args: argparse.Namespace) -> int:
    """板块涨跌幅排名. 用法: boardrank --kind concept --count 20."""
    print_json({"kind": args.kind, "rows": board_rank(args.kind, args.count)})
    return 0


def cmd_hotstocks(args: argparse.Namespace) -> int:
    """当日强势股题材归因(同花顺). 用法: hotstocks --date 2026-09-04."""
    print_json({"date": args.date or _dt.date.today().isoformat(),
                "rows": ths_hot_reason(args.date)})
    return 0


def cmd_indicator(args: argparse.Namespace) -> int:
    """技术指标 MA/MACD/RSI/KDJ/布林带(纯本地计算,自动取K线).
    用法: indicator 600519 --type macd --tail 30"""
    klines = _klines_for_indicator(args.symbol, args.count)
    fn = _INDICATOR_FUNCS[args.type]
    rows = fn(klines)
    if args.tail:
        rows = rows[-args.tail:]
    print_json({"symbol": args.symbol, "type": args.type, "rows": rows})
    return 0


def cmd_options(args: argparse.Namespace) -> int:
    """期权链(仅美股). 用法: options AAPL."""
    print_json(options_chain(args.symbol, args.expiration))
    return 0


def cmd_reports(args: argparse.Namespace) -> int:
    """东财研报列表(卖方观点P2, 含评级/EPS预测). 用法: reports 600519."""
    print_json({"code": args.code, "rows": eastmoney_reports(args.code, args.max_pages)})
    return 0


def _health_value_is_empty(value: Any) -> bool:
    if value is None or value is False:
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    if isinstance(value, (str, bytes, list, tuple, set, dict)):
        return len(value) == 0
    return False


def run_health_checks(check_specs: list[tuple[str, Any, bool]]) -> list[dict[str, Any]]:
    """Run health probes; `allow_empty` marks valid no-event responses explicitly."""
    checks: list[dict[str, Any]] = []
    for name, fn, allow_empty in check_specs:
        started = time.time()
        try:
            value = fn()
            status = "empty" if _health_value_is_empty(value) else "ok"
            acceptable = status == "ok" or allow_empty
            check = {
                "name": name,
                "status": status,
                "ok": acceptable,
                "allow_empty": allow_empty,
                "reason_code": "empty_allowed" if status == "empty" and allow_empty else (
                    "empty_unexpected" if status == "empty" else "probe_ok"
                ),
                "elapsed_sec": round(time.time() - started, 2),
            }
        except Exception as exc:
            check = {
                "name": name,
                "status": "error",
                "ok": False,
                "allow_empty": allow_empty,
                "reason_code": "probe_error",
                "elapsed_sec": round(time.time() - started, 2),
                "error": str(exc)[:300],
            }
        checks.append(check)
    return checks


def build_health_report(checks: list[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    n_ok = sum(1 for check in checks if check["ok"])
    n_empty = sum(1 for check in checks if check["status"] == "empty")
    n_error = sum(1 for check in checks if check["status"] == "error")
    n_failed = len(checks) - n_ok
    report = {
        "as_of": _dt.datetime.now().isoformat(timespec="seconds"),
        "ok_count": n_ok,
        "total": len(checks),
        "empty_count": n_empty,
        "error_count": n_error,
        "failed_count": n_failed,
        "ok": n_failed == 0,
        "status": "ok" if n_failed == 0 else "error",
        "checks": checks,
    }
    return report, 0 if n_failed == 0 else 1


def cmd_healthcheck(args: argparse.Namespace) -> int:
    specs: list[tuple[str, Any, bool]] = [
        ("quote_cn_tencent", lambda: [
            q for q in tencent_quotes([normalize_ticker("600519")]).values()
            if _quote_validation_reason(q) is None
        ], False),
        ("quote_hk_tencent", lambda: [
            q for q in tencent_quotes([normalize_ticker("00700")]).values()
            if _quote_validation_reason(q) is None
        ], False),
        ("kline_yahoo", lambda: yahoo_kline("AAPL", "5d", "1d"), False),
        ("eastmoney_search", lambda: eastmoney_search("英伟达", 3), False),
        ("sec_cik", lambda: ticker_to_cik("AAPL").get("cik"), False),
        ("akline_cn_tencent", lambda: tencent_akline("600519", count=20)["rows"], False),
        ("akline_hk_tencent", lambda: tencent_akline("00700", count=20)["rows"], False),
        ("longhubang_daily", lambda: longhubang_daily("2026-09-03")["stocks"], False),
        ("longhubang_stock", lambda: longhubang_stock("002475", days=30)["records"], True),
        ("margin_trading", lambda: margin_trading("600519", days=10), False),
        ("bj_920_routing_fix", lambda: normalize_ticker("920001").tencent == "bj920001", False),
    ]
    if not args.skip_slow:
        specs.extend([
            ("swindustry (首次跑约1.3万行, 会建证书缓存)",
             lambda: sw_industry_as_of("600519", "2026-08-18"), False),
            ("baostock_valuation",
             lambda: baostock_valuation_history("600519", "2026-08-01", "2026-08-10"), False),
            ("baostock_basic", lambda: baostock_stock_basic("600519").get("ipo_date"), False),
        ])
    specs.extend([
        ("newsflash", lambda: eastmoney_newsflash(3), False),
        ("corpaction_dividend", lambda: dividend_history("600519", 3), False),
        ("corpaction_holders", lambda: holder_count_history("600519", 3), False),
        ("corpaction_block", lambda: block_trades("600519", 3), True),
        ("corpaction_lockup", lambda: lockup_expiry("688017", 3), True),
        ("announcements", lambda: cninfo_announcements("600519", 3), False),
        ("institutional_holders_us", lambda: institutional_holders("AAPL")["top_holders"], False),
        ("fundflow_minute", lambda: fund_flow_minute("600519"), False),
        ("boardrank_concept", lambda: board_rank("concept", 5), False),
        ("boardrank_industry", lambda: board_rank("industry", 5), False),
        ("hotstocks_ths", lambda: ths_hot_reason(), True),
        ("indicator_macd", lambda: calc_macd(_klines_for_indicator("600519", 60)), False),
        ("options_chain_us", lambda: options_chain("AAPL")["calls"], False),
        ("reports_eastmoney", lambda: eastmoney_reports("600519", 1), False),
    ])
    if not args.skip_slow:
        specs.append(("chip_distribution",
                      lambda: chip_distribution("600519", "2026-06-01", "2026-09-04")["days_used"],
                      False))
    specs.append(("market_margin", lambda: market_margin_history(3), False))

    checks = run_health_checks(specs)
    report, exit_code = build_health_report(checks)
    print_json(report)
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="stock-data skill CLI (v5.2)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("quote", help="Fetch realtime quotes (A/H/US via Tencent)")
    p.add_argument("symbols", nargs="+")
    p.set_defaults(func=cmd_quote)

    p = sub.add_parser("kline", help="K线: A股/港股→腾讯 fqkline (前复权), 美股→Yahoo")
    p.add_argument("symbol")
    p.add_argument("--count", type=int, default=250,
                   help="A股/港股: K线根数 (default 250)")
    p.add_argument("--period", default="6mo", help="美股/指数: Yahoo range")
    p.add_argument(
        "--interval", default="1d",
        help="K线周期；A/H仅支持1d/1wk/1mo，美股/指数使用Yahoo interval",
    )
    p.set_defaults(func=cmd_kline)

    p = sub.add_parser("akline",
                       help="[新] A股/港股 K线 (腾讯 fqkline 前复权, 显式)")
    p.add_argument("symbol")
    p.add_argument("--count", type=int, default=250)
    p.add_argument("--ktype", type=int, default=9,
                   help="9=前复权日线 (default), 101=不复权日线, 102=周, 103=月；"
                        "分钟参数1/5/15/30/60当前明确报错（上游契约未确认）")
    p.set_defaults(func=cmd_akline)

    p = sub.add_parser("search", help="全球股票代码搜索 (腾讯 smartbox, 2026-09-04 从失效的东财接口切换)")
    p.add_argument("keyword")
    p.add_argument("--count", type=int, default=10)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("sec", help="美股 SEC EDGAR CIK + XBRL")
    p.add_argument("ticker")
    p.add_argument("--metrics", nargs="*", default=None)
    p.set_defaults(func=cmd_sec)

    p = sub.add_parser("longhubang",
                       help="[新] 龙虎榜 — 全市场 (默认) / 个股 (传 --code)")
    p.add_argument("--code", help="个股 6位代码, 不传=全市场")
    p.add_argument("--date", help="全市场查询日期 YYYY-MM-DD, 默认今天")
    p.add_argument("--days", type=int, default=30,
                   help="个股查询回看天数")
    p.add_argument("--min-net-buy", type=float, default=0,
                   help="全市场查询: 最低净买入 (万元), 0=不过滤")
    p.set_defaults(func=cmd_longhubang)

    p = sub.add_parser("margin",
                       help="[新] 个股融资融券明细 (日级, 东财 datacenter)")
    p.add_argument("code")
    p.add_argument("--days", type=int, default=30)
    p.set_defaults(func=cmd_margin)

    p = sub.add_parser("swindustry",
                       help="[新] 申万行业分类变迁史 (避免行业轮动回测前视偏差)")
    p.add_argument("--code", help="6位代码")
    p.add_argument("--asof", help="查询日期 YYYY-MM-DD, 默认今天")
    p.add_argument("--dump", action="store_true", help="全量导出(约1.3万行)")
    p.add_argument("--refresh", action="store_true", help="强制重新下载,忽略7天缓存")
    p.set_defaults(func=cmd_swindustry)

    p = sub.add_parser("valuation",
                       help="[新] 估值历史 PE/PB/PS/PCF (baostock, 不支持北交所)")
    p.add_argument("code")
    p.add_argument("--start", default="2016-01-01")
    p.add_argument("--end", default=_dt.date.today().isoformat())
    p.set_defaults(func=cmd_valuation)

    p = sub.add_parser("basic",
                       help="[新] 上市/退市日期与状态 (baostock, 不支持北交所)")
    p.add_argument("code")
    p.set_defaults(func=cmd_basic)

    p = sub.add_parser("chip",
                       help="[新] 筹码分布 (获利比例/成本区间/峰值价, baostock, 不支持北交所)")
    p.add_argument("code")
    p.add_argument("--start", default="2025-01-01")
    p.add_argument("--end", default=_dt.date.today().isoformat())
    p.set_defaults(func=cmd_chip)

    p = sub.add_parser("marketmargin",
                       help="[新] 全A两融余额历史 (沪深北合计, 东财)")
    p.add_argument("--days", type=int, default=20)
    p.set_defaults(func=cmd_marketmargin)

    p = sub.add_parser("newsflash",
                       help="[新] 全市场实时快讯 (东财, 替代已404的财联社电报)")
    p.add_argument("--count", type=int, default=20)
    p.set_defaults(func=cmd_newsflash)

    p = sub.add_parser("corpaction",
                       help="[新] 解禁/大宗交易/分红/股东户数 (东财 datacenter)")
    p.add_argument("code")
    p.add_argument("--type", choices=list(_CORPACTION_FUNCS.keys()), required=True)
    p.add_argument("--count", type=int, default=20)
    p.set_defaults(func=cmd_corpaction)

    p = sub.add_parser("announcements",
                       help="[新] 巨潮公告全文检索 (688科创板部分标的已知边界见函数docstring)")
    p.add_argument("code")
    p.add_argument("--count", type=int, default=20)
    p.set_defaults(func=cmd_announcements)

    p = sub.add_parser("holders",
                       help="[新] 机构持仓 (仅美股/港股, Yahoo)")
    p.add_argument("symbol")
    p.set_defaults(func=cmd_holders)

    p = sub.add_parser("fundflow",
                       help="[新] 个股资金流分钟级 (push2delay, 主力/超大单/大单/中单/小单)")
    p.add_argument("code")
    p.set_defaults(func=cmd_fundflow)

    p = sub.add_parser("boardrank",
                       help="[新] 板块涨跌幅排名 (push2delay)")
    p.add_argument("--kind", choices=list(_BOARD_FS.keys()), default="concept")
    p.add_argument("--count", type=int, default=20)
    p.set_defaults(func=cmd_boardrank)

    p = sub.add_parser("hotstocks",
                       help="[新] 当日强势股题材归因 (同花顺, 编辑部人工标签)")
    p.add_argument("--date", default=None)
    p.set_defaults(func=cmd_hotstocks)

    p = sub.add_parser("indicator",
                       help="[新] 技术指标 MA/MACD/RSI/KDJ/布林带 (纯本地计算, 全市场)")
    p.add_argument("symbol")
    p.add_argument("--type", choices=list(_INDICATOR_FUNCS.keys()), required=True)
    p.add_argument("--count", type=int, default=120, help="取K线根数(含指标热身期)")
    p.add_argument("--tail", type=int, default=30, help="只返回最后N行, 0=全部")
    p.set_defaults(func=cmd_indicator)

    p = sub.add_parser("options",
                       help="[新] 期权链 (仅美股, Yahoo)")
    p.add_argument("symbol")
    p.add_argument("--expiration", type=int, default=None, help="Unix时间戳, 不传=最近到期日")
    p.set_defaults(func=cmd_options)

    p = sub.add_parser("reports",
                       help="[新] 东财研报列表 (卖方观点P2, 含评级/EPS预测)")
    p.add_argument("code")
    p.add_argument("--max-pages", type=int, default=3)
    p.set_defaults(func=cmd_reports)

    p = sub.add_parser("healthcheck",
                       help="运行全部端点健康检查")
    p.add_argument("--skip-slow", action="store_true",
                   help="跳过 swindustry 检查(首次跑要下载1.1MB建证书缓存,较慢)")
    p.set_defaults(func=cmd_healthcheck)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
