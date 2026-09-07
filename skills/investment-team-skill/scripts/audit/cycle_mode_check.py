"""
cycle_mode_check.py — v6.1 反偷懒 A6：5 号职责 E（cycle 模式声明）机器化检查

背景（v6.0.3 引入 / v6.1 正式）：
  Phase 0 数据采集器支持 4 种模式（portfolio/stock/etf/macro），不同模式跳过不同步骤。
  5 号 audit 协议（roles/05_supervisor.md 职责 E）要求在 audit 输出主动声明本次 cycle 的模式
  与跳过项，**不允许静默 fallback**。

  本脚本是机器化兜底——5 号自己漏报 mode → 红牌 + 工头公开纠偏。

算法：
  1. 从 5 号 audit 输出（outputs/05_supervisor/05_审核.md 或最新 .v*.md）读取
  2. 检查是否包含 [CYCLE MODE] 区块
  3. 检查 mode 值是否在 {portfolio, stock, etf, macro} 之一
  4. 检查 [SKIPPED] 区块是否存在（mode != portfolio 时必有）
  5. 与 cycle_state.notes 或 message_log 中 foreman 播的 mode 对账
  6. verdict = PASS / FAIL / WARN

CLI:
  python cycle_mode_check.py outputs/05_supervisor/05_审核.md \
      [--cycle-id N] [--review-id N]

输出 JSON 到 stdout + 写 audit_log
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

SKILL_HOME = Path(os.environ.get(
    "INVESTMENT_TEAM_HOME",
    str(Path(__file__).resolve().parents[2])
))
DB_PATH = Path(os.environ.get(
    "INVESTMENT_TEAM_DB",
    SKILL_HOME / "engine" / "data" / "trading.db"
))

VALID_MODES = {"portfolio", "stock", "etf", "macro"}

# 在 audit md 里识别 [CYCLE MODE] 区块（容错：CYCLE_MODE / Cycle Mode 等）
# 正则：在 [CYCLE MODE] 同一行的尾部找 4 个合法 mode 关键词之一
CYCLE_MODE_PATTERN = re.compile(
    r"\[\s*CYCLE[\s_]?MODE\s*\][^\n]*?\b(portfolio|stock|etf|macro)\b",
    re.IGNORECASE
)
TARGET_PATTERN = re.compile(
    r"target\s*[=：]\s*(\S+)",
    re.IGNORECASE
)
SKIPPED_BLOCK_PATTERN = re.compile(
    r"\[\s*SKIPPED\s*\][^\n]*",
    re.IGNORECASE
)


def _read_audit_md(audit_path: Path) -> str | None:
    """读取 5 号最新 audit md（自动找 .v*.md 中编号最大的）"""
    if audit_path.is_file():
        return audit_path.read_text(encoding="utf-8")
    # 找同目录下编号最大的 .v*.md
    if audit_path.is_dir() or audit_path.name.endswith(".md"):
        parent = audit_path.parent if audit_path.suffix else audit_path
        candidates = sorted(parent.glob("05_审核.v*.md")) if parent.is_dir() else []
        if not candidates:
            candidates = sorted(parent.glob("05_*.md")) if parent.is_dir() else []
        if candidates:
            return candidates[-1].read_text(encoding="utf-8")
    return None


def _get_expected_mode(cycle_id: int | None) -> str | None:
    """从 cycle_state 表读取 cycle 启动时实际用的 mode（解析 message_log foreman 那条）"""
    if cycle_id is None or not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            """
            SELECT raw_text FROM message_log
            WHERE cycle_id = ? AND msg_type IN ('FOREMAN_NOTICE', 'SYSTEM')
              AND raw_text LIKE '%mode=%'
            ORDER BY id ASC LIMIT 1
            """,
            (cycle_id,),
        ).fetchall()
        conn.close()
        if rows:
            text = rows[0][0]
            m = re.search(r"mode\s*=\s*(\w+)", text)
            if m and m.group(1).lower() in VALID_MODES:
                return m.group(1).lower()
    except Exception:
        pass
    return None


def check(audit_path: Path, cycle_id: int | None = None) -> dict:
    """检查 5 号 audit 输出是否含 [CYCLE MODE] 区块"""
    today = date.today().isoformat()

    text = _read_audit_md(audit_path)
    if text is None:
        return {
            "audit_path": str(audit_path),
            "audit_date": today,
            "verdict": "FAIL",
            "fail_reason": "5 号 audit md 不存在或不可读 → 5 号偷懒未输出审核",
            "declared_mode": None,
            "expected_mode": None,
            "consistency": "UNKNOWN",
        }

    # 匹配 [CYCLE MODE]
    mode_match = CYCLE_MODE_PATTERN.search(text)
    declared_mode = mode_match.group(1).lower() if mode_match else None

    target_match = TARGET_PATTERN.search(text) if mode_match else None
    declared_target = target_match.group(1) if target_match else None

    # 检查 [SKIPPED] 区块（非 portfolio 时必须）
    has_skipped_block = bool(SKIPPED_BLOCK_PATTERN.search(text))

    # 与 cycle_state 对账
    expected_mode = _get_expected_mode(cycle_id)

    issues: list[str] = []
    warnings: list[str] = []

    if declared_mode is None:
        issues.append("5 号 audit 输出缺 [CYCLE MODE] 区块（职责 E 漏报）")
    elif declared_mode not in VALID_MODES:
        issues.append(f"declared mode={declared_mode!r} 不在合法值 {sorted(VALID_MODES)} 内")

    if declared_mode and declared_mode != "portfolio" and not has_skipped_block:
        warnings.append(f"declared mode={declared_mode}，应有 [SKIPPED] 区块说明跳过项")

    consistency = "UNKNOWN"
    if expected_mode is not None and declared_mode is not None:
        consistency = "MATCH" if declared_mode == expected_mode else "MISMATCH"
        if consistency == "MISMATCH":
            issues.append(
                f"declared mode={declared_mode} 与 cycle 实际 mode={expected_mode} 不一致"
                f"（5 号谎报或漏改）"
            )

    if issues:
        verdict = "FAIL"
    elif warnings:
        verdict = "WARN"
    else:
        verdict = "PASS"

    return {
        "audit_path": str(audit_path),
        "audit_date": today,
        "cycle_id": cycle_id,
        "verdict": verdict,
        "fail_reason": "; ".join(issues) if issues else None,
        "warnings": warnings,
        "declared_mode": declared_mode,
        "declared_target": declared_target,
        "expected_mode": expected_mode,
        "has_skipped_block": has_skipped_block,
        "consistency": consistency,
        "rule": "5 号 audit 必须有 [CYCLE MODE] mode=X 区块；非 portfolio 时还需 [SKIPPED] 区块",
    }


def write_audit_log(result: dict, review_id: int | None, target_role: str = "5"):
    """写入 audit_log 表"""
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO audit_log (review_id, script_name, target_role, target_artifact, verdict, detail_json, audit_date)
        VALUES (?, 'cycle_mode_check', ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            target_role,
            result["audit_path"],
            result["verdict"],
            json.dumps(result, ensure_ascii=False),
            result["audit_date"],
        ),
    )
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="v6.1 反偷懒 A6：5 号 cycle 模式声明检查")
    parser.add_argument("audit_path", help="5 号 audit md 文件路径")
    parser.add_argument("--cycle-id", type=int, default=None,
                        help="cycle_id（用于与 cycle_state 实际 mode 对账）")
    parser.add_argument("--review-id", type=int, default=None)
    parser.add_argument("--no-db", action="store_true")
    args = parser.parse_args()

    result = check(Path(args.audit_path), cycle_id=args.cycle_id)

    icon = {"PASS": "✅", "WARN": "🟨", "FAIL": "❌"}.get(result["verdict"], "❓")
    print(f"{icon} cycle_mode_check | {Path(args.audit_path).name}")
    print(f"   verdict       = {result['verdict']}")
    print(f"   declared_mode = {result['declared_mode']}  target={result.get('declared_target')}")
    print(f"   expected_mode = {result['expected_mode']}")
    print(f"   consistency   = {result['consistency']}")
    if result.get("fail_reason"):
        print(f"   ⛔ {result['fail_reason']}")
    for w in result.get("warnings", []):
        print(f"   🟨 {w}")

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not args.no_db:
        write_audit_log(result, args.review_id)

    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
