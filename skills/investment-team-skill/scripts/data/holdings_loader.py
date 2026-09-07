# 适配形态: agent + bot
"""
v6.2 持仓快照封装（不动 v5.1 逻辑）
"""
from __future__ import annotations

import sys
from pathlib import Path

from .common import SKILL_HOME


def load_holdings(today: str) -> dict | None:
    """读取 holdings_latest.json（如不存在则返回 None）。
    保留 v5.1 行为：不重写持仓文件，由用户 holdings.csv 上游维护。
    """
    sys.path.insert(0, str(SKILL_HOME / "scripts" / "calc"))
    holdings_path = SKILL_HOME / "engine" / "data" / "holdings" / "holdings_latest.json"
    if not holdings_path.exists():
        return None
    import json
    return json.loads(holdings_path.read_text(encoding="utf-8"))
