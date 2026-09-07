"""
beauty_score_check.py — v6.1 反偷懒 A5：选丑审计 + 协议级冲突检测

算法（v6.0 第 5 项 audit + v6.1 升级）：
  1. 从 watchlist md 提取所有 ticker
  2. 对照 beauty_<date>.json，watchlist 中的 ticker 必须 ≥ 70 分
  3. 任何 < 70 分的 ticker 出现在 watchlist → verdict=FAIL（5 号 supervisor 必须 REJECT）
  4. 任何 ticker 缺失 beauty_score 数据 → verdict=FAIL（数据缺失等同于"偷懒未跑评分"）

  v6.1 新增（z-score 协议）：
  5. 检测 v1.0 / v1.1 双结果一致性：consensus=CONFLICT 时挂 PROTOCOL_CONFLICT 标签
  6. 输出 conflict 列表给 5 号 supervisor，由其在 audit 5 区块里主动暴露

CLI:
  python beauty_score_check.py outputs/02_industry/02_Watchlist.md \
      [--beauty-file engine/data/finance/beauty_<date>.json] \
      [--review-id N] [--target-role 2]

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
DATA_DIR = Path(os.environ.get(
    "INVESTMENT_TEAM_DATA_DIR",
    SKILL_HOME / "engine" / "data"
))
BEAUTY_DIR = DATA_DIR / "finance"

# 从 watchlist md 提取 6 位代码（个股，A 股）+ 5 位（港股 hk03033）
TICKER_PATTERN = re.compile(r"\b((?:sh|sz|hk|us)?(?:\d{6}|\d{5}))\b", re.IGNORECASE)
# 排除明显非 ticker 数字（年份、价格等）
YEAR_PATTERN = re.compile(r"^(19|20)\d{2}$")


def extract_tickers_from_watchlist(md_path: Path) -> list[str]:
    """从 watchlist md 中提取股票代码"""
    if not md_path.exists():
        raise FileNotFoundError(f"watchlist 文件不存在: {md_path}")
    content = md_path.read_text(encoding="utf-8")
    raw = TICKER_PATTERN.findall(content)
    # 去重保序 + 过滤年份
    seen = set()
    result = []
    for t in raw:
        t_clean = re.sub(r"^(sh|sz|hk|us)", "", t, flags=re.IGNORECASE)
        if YEAR_PATTERN.match(t_clean):
            continue
        if t_clean in seen:
            continue
        seen.add(t_clean)
        result.append(t_clean)
    return result


def check(watchlist_path: Path, beauty_file: Path | None = None) -> dict:
    today = date.today().isoformat()
    if beauty_file is None:
        beauty_file = BEAUTY_DIR / f"beauty_{today}.json"
    if not beauty_file.exists():
        return {
            "watchlist": str(watchlist_path),
            "beauty_file": str(beauty_file),
            "verdict": "FAIL",
            "fail_reason": f"beauty_<date>.json 不存在；2 号未跑选美评分（A5 偷懒）",
            "missing_beauty_file": True,
            "tickers_checked": [],
            "ugly_tickers": [],
            "missing_data_tickers": [],
        }

    beauty = json.loads(beauty_file.read_text(encoding="utf-8"))
    beauty_tickers = beauty.get("tickers", {})

    watchlist_tickers = extract_tickers_from_watchlist(watchlist_path)

    ugly = []          # 极端淘汰（v1.2）/ 选丑（v1.0/1.1）—— 这些是真要 REJECT 的
    risky = []         # v1.2 中性/真丑等：风险偏高但允许进 watchlist（仅披露）
    pass_tickers = []  # v1.2 顶美/一线/丑小鸭 / v1.0-1.1 ≥70 分通过
    missing = []       # watchlist 中但 beauty_<date> 没数据
    protocol_conflicts = []  # v6.1: v1.0/v1.1 不一致

    for t in watchlist_tickers:
        if t not in beauty_tickers:
            missing.append(t)
            continue

        r = beauty_tickers[t]
        score = r.get("score", 0)
        tag = r.get("tag")  # v1.2 字段；老协议无此字段
        v12_meta = r.get("v12_meta") or {}
        is_v12_extreme_reject = v12_meta.get("decision_mode") == "REJECT"

        # 协议冲突（v1.0 vs v1.1）
        if r.get("audit_flag") or r.get("consensus_v10_v11") == "CONFLICT":
            protocol_conflicts.append({
                "ticker": t,
                "v10_grade": (r.get("v10_result") or {}).get("grade"),
                "v11_grade": (r.get("v11_result") or {}).get("grade"),
                "v12_tag": tag,
                "decision_protocol": r.get("decision_protocol"),
                "audit_flag": r.get("audit_flag"),
            })

        # v1.2 分类逻辑：极端淘汰 → ugly（FAIL）；其它 → 披露但不 REJECT
        if is_v12_extreme_reject:
            ugly.append({
                "ticker": t,
                "score": score,
                "tag": tag or "极端淘汰",
                "title": r.get("title", ""),
                "weakness": r.get("weakness", ""),
                "extreme_reasons": v12_meta.get("extreme_reasons") or r.get("hard_filter_reasons", []),
            })
        elif tag in ("顶美", "一线", "丑小鸭"):
            pass_tickers.append({
                "ticker": t,
                "score": score,
                "tag": tag,
                "title": r.get("title", ""),
                "position_pct_suggest": r.get("position_cap_pct_suggest", 0),
                "tag_narrative": r.get("tag_narrative", ""),
            })
        elif tag in ("中性", "真丑"):
            risky.append({
                "ticker": t,
                "score": score,
                "tag": tag,
                "title": r.get("title", ""),
                "position_pct_suggest": r.get("position_cap_pct_suggest", 0),
                "risk_disclosure": v12_meta.get("risk_disclosure", []),
                "opportunity_signals": v12_meta.get("opportunity_signals", []),
            })
        elif r.get("grade") == "C" or score < 70:
            # v1.0/v1.1 老协议：score<70=C 仍按老逻辑 FAIL
            ugly.append({
                "ticker": t,
                "score": score,
                "grade": r.get("grade", "C"),
                "title": r.get("title", ""),
                "weakness": r.get("weakness", ""),
                "hard_filter_reasons": r.get("hard_filter_reasons", []),
            })
        else:
            pass_tickers.append({
                "ticker": t,
                "score": score,
                "grade": r.get("grade"),
                "title": r.get("title", ""),
                "position_cap_pct": r.get("position_cap_pct", 0),
            })

    # v1.2: verdict 仅在"极端淘汰被列入 watchlist"时 FAIL；中性/真丑只是 WARN
    has_violation = bool(ugly) or bool(missing)
    if has_violation:
        verdict = "FAIL"
    elif risky:
        verdict = "WARN"
    else:
        verdict = "PASS"

    fail_reasons = []
    if ugly:
        fail_reasons.append(f"watchlist 含 {len(ugly)} 个极端淘汰/老协议丑女标的")
    if missing:
        fail_reasons.append(f"watchlist 含 {len(missing)} 个缺失 beauty_score 数据的标的")

    warn_reasons = []
    if risky:
        warn_reasons.append(
            f"watchlist 含 {len(risky)} 个 v1.2 中性/真丑标的（不强制 REJECT，但 5 号需主动披露风险）"
        )

    protocol_warning = None
    if protocol_conflicts:
        protocol_warning = (
            f"⚠️ v6.1 协议级冲突 {len(protocol_conflicts)} 起；"
            f"决策依据 v1.2，5 号需在 audit 5 主动暴露"
        )

    return {
        "watchlist": str(watchlist_path),
        "beauty_file": str(beauty_file),
        "audit_date": today,
        "verdict": verdict,
        "fail_reason": "; ".join(fail_reasons) if fail_reasons else None,
        "warn_reason": "; ".join(warn_reasons) if warn_reasons else None,
        "tickers_checked": watchlist_tickers,
        "pass_tickers": pass_tickers,
        "ugly_tickers": ugly,                # v1.2 仅含极端淘汰
        "risky_tickers": risky,              # v1.2 新增：中性/真丑披露
        "missing_data_tickers": missing,
        "protocol_conflicts": protocol_conflicts,
        "protocol_warning": protocol_warning,
        "summary": {
            "total": len(watchlist_tickers),
            "pass": len(pass_tickers),
            "risky_disclosed": len(risky),
            "ugly_extreme": len(ugly),
            "missing": len(missing),
            "v10_v11_conflicts": len(protocol_conflicts),
        },
        "threshold_rule": (
            "v1.2 风险披露版：仅 watchlist 含'极端淘汰'/缺数据 → FAIL；"
            "含'中性/真丑' → WARN（披露不强制）；其它 → PASS"
        ),
    }


def write_audit_log(result: dict, review_id: int | None, target_role: str):
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO audit_log (review_id, script_name, target_role, target_artifact, verdict, detail_json, audit_date)
        VALUES (?, 'beauty_score_check', ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            target_role,
            result["watchlist"],
            result["verdict"],
            json.dumps(result, ensure_ascii=False),
            result["audit_date"],
        ),
    )
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="v6.0 反偷懒 A5：选丑审计")
    parser.add_argument("watchlist", help="watchlist md 文件路径")
    parser.add_argument("--beauty-file", help="指定 beauty_<date>.json")
    parser.add_argument("--review-id", type=int, default=None)
    parser.add_argument("--target-role", default="2")
    args = parser.parse_args()

    wl = Path(args.watchlist)
    bf = Path(args.beauty_file) if args.beauty_file else None
    result = check(wl, beauty_file=bf)

    # 控制台简报
    icon = {"PASS": "✅", "WARN": "🟨", "FAIL": "❌"}.get(result["verdict"], "❓")
    print(f"{icon} beauty_score_check | {wl.name}")
    print(f"   verdict={result['verdict']}")
    s = result["summary"]
    print(f"   {s['pass']} 通过 | {s.get('risky_disclosed', 0)} 风险披露 | {s.get('ugly_extreme', s.get('ugly', 0))} 极端淘汰 | {s['missing']} 缺数据 | 共 {s['total']}")
    if result.get("ugly_tickers"):
        print(f"   ⛔ 极端淘汰（不应出现在 watchlist）：")
        for u in result["ugly_tickers"]:
            label = u.get('tag') or u.get('grade', 'C')
            print(f"      {u['ticker']} score={u['score']:.1f} {label} | {u.get('weakness', '')}")
    if result.get("risky_tickers"):
        print(f"   🟨 风险披露（v1.2 中性/真丑，允许在 watchlist 但需主动暴露风险）：")
        for r_ in result["risky_tickers"]:
            print(f"      {r_['ticker']} score={r_['score']:.1f} {r_['tag']} | 建议 ≤{r_.get('position_pct_suggest', 0)}%")
            for risk in (r_.get("risk_disclosure") or [])[:2]:
                print(f"         {risk}")
    if result["missing_data_tickers"]:
        print(f"   ⚠️  缺数据：{', '.join(result['missing_data_tickers'])}")
    if result.get("protocol_warning"):
        print(f"   {result['protocol_warning']}")
        for c in result.get("protocol_conflicts", []):
            print(f"      • {c['ticker']}: v1.0={c['v10_grade']} ↔ v1.1={c['v11_grade']}  v1.2 tag={c.get('v12_tag')}")

    print(json.dumps(result, ensure_ascii=False, indent=2))

    write_audit_log(result, args.review_id, args.target_role)

    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
