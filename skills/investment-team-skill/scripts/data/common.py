# 适配形态: agent + bot
"""
v6.2 数据层公共工具
- DataCollectionError 异常
- 路径常量
- requests UA 反爬补丁
- akshare/pandas 延迟 import
- 指数退避 retry
"""
from __future__ import annotations

import http.client
import os
import sys
import time
from pathlib import Path


SKILL_HOME = Path(os.environ.get(
    "INVESTMENT_TEAM_HOME",
    str(Path(__file__).resolve().parents[2])
))
DATA_DIR = Path(os.environ.get(
    "INVESTMENT_TEAM_DATA_DIR",
    SKILL_HOME / "engine" / "data"
))


class DataCollectionError(Exception):
    """v6.0+ 真实数据采集失败 — 不允许 fallback fixture，cycle 必须 ABORT"""
    def __init__(self, source: str, reason: str):
        self.source = source
        self.reason = reason
        super().__init__(f"DataCollectionError(source={source}, reason={reason})")


def patch_requests_user_agent() -> None:
    """v6.0.1 反爬补丁：eastmoney 升级反爬封了 'python-requests/*' 默认 UA。
    在 akshare import 前把 requests 全局 UA 换成 Chrome。
    必须在第一次 import requests 之后、第一次 akshare 调用之前执行。
    """
    try:
        import requests
        import requests.utils as _ru
    except ImportError:
        return
    _UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    _orig_default_headers = _ru.default_headers
    def _patched_default_headers():
        h = _orig_default_headers()
        h["User-Agent"] = _UA
        return h
    _ru.default_headers = _patched_default_headers

    _orig_session_init = requests.Session.__init__
    def _patched_session_init(self, *args, **kwargs):
        _orig_session_init(self, *args, **kwargs)
        self.headers["User-Agent"] = _UA
    requests.Session.__init__ = _patched_session_init


def import_akshare():
    """延迟 import + 友好错误。在 import 前自动跑 UA 补丁。"""
    patch_requests_user_agent()
    try:
        import akshare as ak
        return ak
    except ImportError:
        raise DataCollectionError(
            source="akshare_import",
            reason="akshare 未安装。请执行：pip install -r requirements.txt（v6.2 已纳入核心依赖）",
        )


def import_pandas():
    try:
        import pandas as pd
        return pd
    except ImportError:
        raise DataCollectionError(
            source="pandas_import",
            reason="pandas 未安装",
        )


def call_with_retry(fn, *args, max_retries: int = 3, base_delay: float = 0.5, **kwargs):
    """akshare 后端偶发 keep-alive 半死连接，会抛 RemoteDisconnected/ProtocolError。
    包一层指数退避（0.5s → 1.0s → 2.0s），其它异常立即抛。
    """
    connection_errors: tuple = (
        http.client.RemoteDisconnected,
        ConnectionResetError,
        TimeoutError,
    )
    try:
        import requests.exceptions as _rex
        import urllib3.exceptions as _u3ex
        connection_errors = connection_errors + (
            _rex.ConnectionError,
            _rex.ChunkedEncodingError,
            _rex.ReadTimeout,
            _u3ex.ProtocolError,
        )
    except ImportError:
        pass

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except connection_errors as e:
            last_err = e
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    if last_err:
        raise last_err  # pragma: no cover
