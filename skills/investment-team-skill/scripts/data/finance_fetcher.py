# 适配形态: agent + bot
"""
v6.2 财务数据封装
- 调用 scripts/calc/finance_collector.py（已有实现）
- 提供统一调用入口
"""
from __future__ import annotations

import sys
from pathlib import Path

from .common import DataCollectionError, SKILL_HOME


def collect_finance_for_tickers(tickers: list[str], today: str) -> dict:
    """调用 finance_collector.py 拉取财务指标。

    Args:
        tickers: ["601138", "603296", ...]（纯代码）
        today: 'YYYY-MM-DD'
    Returns:
        finance_<date>.json 的 dict
    """
    sys.path.insert(0, str(SKILL_HOME / "scripts" / "calc"))
    try:
        from finance_collector import collect_finance as _fc  # type: ignore
    except ImportError as e:
        raise DataCollectionError(
            source="finance_collector_import",
            reason=f"无法 import finance_collector.py: {e}",
        )

    if not tickers:
        return {
            "date": today,
            "generated_by": "v6.2 finance_fetcher [empty]",
            "tickers": {},
        }
    return _fc(tickers, today=today)
