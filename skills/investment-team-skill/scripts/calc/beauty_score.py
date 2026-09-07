"""
beauty_score.py — v6.0 选美评分（"选股要像 KTV 选小姐一样选最漂亮的"）

算法（详见 references/beauty_scoring.md）：
  1. 4 条硬过滤（任一不通过 → grade=C 直接淘汰）
  2. 100 分加权评分：盈利 30 + 成长 35 + 财务安全 25 + 估值 10
  3. 4 级分级：S(90+)/A(80-89)/B(70-79)/C(<70)

CLI:
  python beauty_score.py --tickers 600519 000858 300750
  python beauty_score.py --finance-file engine/data/finance/finance_2026-05-31.json
  python beauty_score.py --watchlist  # 自动从 02_Watchlist.md 提取

输出：engine/data/finance/beauty_<date>.json + audit_log 表
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

SKILL_HOME = Path(os.environ.get(
    "INVESTMENT_TEAM_HOME",
    str(Path(__file__).resolve().parents[2])
))
DATA_DIR = Path(os.environ.get(
    "INVESTMENT_TEAM_DATA_DIR",
    SKILL_HOME / "engine" / "data"
))
DB_PATH = Path(os.environ.get(
    "INVESTMENT_TEAM_DB",
    DATA_DIR / "trading.db"
))
FINANCE_DIR = DATA_DIR / "finance"


# ========================== 硬过滤 ==========================

def hard_filter(f: dict, industry: str = "") -> tuple[bool, list[str]]:
    """4 条硬过滤
    返回 (是否通过, 不通过原因列表)
    """
    reasons = []
    is_finance = "银行" in industry or "证券" in industry or "保险" in industry
    is_realestate = "房地产" in industry

    # 1. ROE 近 3 年均值
    roe_3y = f.get("roe_3y_avg", 0) or f.get("roe_ttm", 0)
    threshold_roe = 10 if is_finance else 12
    if roe_3y < threshold_roe:
        reasons.append(f"ROE 近3年均值 {roe_3y:.1f}% < {threshold_roe}%")

    # 2. 资产负债率
    debt = f.get("debt_ratio", 0)
    if is_finance:
        threshold_debt = 90
    elif is_realestate:
        threshold_debt = 80
    else:
        threshold_debt = 70
    if debt > threshold_debt:
        reasons.append(f"资产负债率 {debt:.1f}% > {threshold_debt}%")

    # 3. 经营现金流 / 净利润
    cfo_np = f.get("cfo_to_np", 0)
    if not is_finance:  # 金融业不考核
        threshold_cfo = 0.5 if "周期" in industry else 0.8
        if cfo_np < threshold_cfo:
            reasons.append(f"CFO/净利润 {cfo_np:.2f} < {threshold_cfo}")

    # 4. 营收 YoY
    rev_yoy = f.get("rev_yoy_latest", 0)
    if rev_yoy <= 0:
        reasons.append(f"营收 YoY {rev_yoy:.1f}% ≤ 0")

    passed = len(reasons) == 0
    return passed, reasons


# ========================== v1.1 行业 z-score 硬过滤（v6.1 新增） ==========================
# 协议来源：references/beauty_scoring.md 章节五·之二（v1.1 正式启用 2026-06-01）

# v1.1 绝对值兜底红线（无论行业多烂都不能突破）
V11_ABSOLUTE_REDLINES = {
    "debt_ratio_max":  85.0,   # 资产负债率绝对上限
    "roe_3y_min":       8.0,   # ROE 3 年均值绝对下限
    "cfo_to_np_min":    0.3,   # CFO/NP 绝对下限
}

# v1.1 z-score 阈值（按指标方向）
V11_ZSCORE_RULES = {
    "roe_3y":      {"direction": "higher_better", "reject_z": -2.0, "warn_z": -1.0},
    "debt_ratio":  {"direction": "lower_better",  "reject_z": +2.0, "warn_z": +1.0},
    "cfo_to_np":   {"direction": "higher_better", "reject_z": -2.0, "warn_z": -1.0},
}

# 行业池最小样本数（不含 target；统计学最小有效样本）→ 不足时退化回 v1.0
V11_MIN_POOL_SIZE = 5


_PEERS_YAML_CACHE: dict | None = None


def _load_peers_yaml() -> dict:
    """读 references/industry_peers.yaml；模块级缓存"""
    global _PEERS_YAML_CACHE
    if _PEERS_YAML_CACHE is not None:
        return _PEERS_YAML_CACHE
    try:
        import yaml
    except ImportError:
        return {}
    yaml_path = SKILL_HOME / "references" / "industry_peers.yaml"
    if not yaml_path.exists():
        return {}
    with open(yaml_path, "r", encoding="utf-8") as f:
        _PEERS_YAML_CACHE = yaml.safe_load(f) or {}
    return _PEERS_YAML_CACHE


def _industry_pool_for(target: str, finance_data: dict) -> tuple[list[dict], str | None]:
    """根据 target ticker 取同行业 peers 的财务数据列表（含 target 自己）"""
    peers_yaml = _load_peers_yaml()
    group_key = (peers_yaml.get("ticker_to_group") or {}).get(str(target))
    if not group_key:
        return [], None
    members = (peers_yaml.get(group_key) or {}).get("members") or []
    pool: list[dict] = []
    for code in members:
        code_s = str(code)
        if code_s in finance_data:
            d = dict(finance_data[code_s])
            d["_ticker"] = code_s
            pool.append(d)
    return pool, group_key


def _safe_float(v, default: float = 0.0) -> float:
    """财务字段缺失/None/字符串 → default"""
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def compute_zscores(target_finance: dict, pool: list[dict]) -> dict:
    """对目标股的关键指标，相对行业池算 z-score。

    若行业池 <V11_MIN_POOL_SIZE 家，返回 {"_pool_too_small": True, "pool_size": n}
    """
    n = len(pool)
    if n < V11_MIN_POOL_SIZE:
        return {"_pool_too_small": True, "pool_size": n}

    metrics = ["roe_3y", "debt_ratio", "cfo_to_np"]
    z = {"_pool_too_small": False, "pool_size": n}
    for m in metrics:
        if m == "roe_3y":
            target_val = _safe_float(target_finance.get("roe_3y_avg") or target_finance.get("roe_ttm"))
            pool_vals = [_safe_float(p.get("roe_3y_avg") or p.get("roe_ttm")) for p in pool]
        else:
            target_val = _safe_float(target_finance.get(m))
            pool_vals = [_safe_float(p.get(m)) for p in pool]
        valid = [v for v in pool_vals if v != 0]
        if len(valid) < 3:
            z[m] = {"target": target_val, "mean": 0, "std": 0, "z": 0, "_invalid_pool": True}
            continue
        mean = sum(valid) / len(valid)
        var = sum((v - mean) ** 2 for v in valid) / len(valid)
        std = var ** 0.5
        if std == 0:
            z[m] = {"target": target_val, "mean": mean, "std": 0, "z": 0}
        else:
            z[m] = {
                "target": round(target_val, 2),
                "mean": round(mean, 2),
                "std": round(std, 2),
                "z": round((target_val - mean) / std, 2),
            }
    return z


def hard_filter_v11(f: dict, pool: list[dict]) -> dict:
    """v1.1 z-score 主导 + 绝对值兜底硬过滤"""
    z = compute_zscores(f, pool)
    pool_size = z.get("pool_size", 0)

    if z.get("_pool_too_small"):
        return {
            "passed": False,
            "reasons": [],
            "warnings": [],
            "z_scores": {},
            "absolute_violations": [],
            "fallback_to_v10": True,
            "industry_pool_size": pool_size,
        }

    reasons: list[str] = []
    warnings: list[str] = []
    abs_violations: list[str] = []

    # 1. 绝对值兜底红线
    debt = _safe_float(f.get("debt_ratio"))
    if debt > V11_ABSOLUTE_REDLINES["debt_ratio_max"]:
        abs_violations.append(f"资产负债率 {debt:.1f}% > 绝对红线 {V11_ABSOLUTE_REDLINES['debt_ratio_max']}%")

    roe_3y = _safe_float(f.get("roe_3y_avg") or f.get("roe_ttm"))
    if roe_3y < V11_ABSOLUTE_REDLINES["roe_3y_min"]:
        abs_violations.append(f"ROE 3 年均值 {roe_3y:.1f}% < 绝对红线 {V11_ABSOLUTE_REDLINES['roe_3y_min']}%")

    cfo_np = _safe_float(f.get("cfo_to_np"))
    if cfo_np < V11_ABSOLUTE_REDLINES["cfo_to_np_min"]:
        abs_violations.append(f"CFO/NP {cfo_np:.2f} < 绝对红线 {V11_ABSOLUTE_REDLINES['cfo_to_np_min']}")

    if abs_violations:
        reasons.extend([f"[绝对红线] {v}" for v in abs_violations])

    # 2. z-score 主层判定
    for metric, rule in V11_ZSCORE_RULES.items():
        if metric not in z or z[metric].get("_invalid_pool"):
            continue
        zv = z[metric]["z"]
        direction = rule["direction"]
        if direction == "higher_better":
            if zv <= rule["reject_z"]:
                reasons.append(f"[{metric}] z={zv} ≤ {rule['reject_z']}σ（行业内极差）")
            elif zv <= rule["warn_z"]:
                warnings.append(f"[{metric}] z={zv} ≤ {rule['warn_z']}σ（行业内偏差）")
        else:  # lower_better
            if zv >= rule["reject_z"]:
                reasons.append(f"[{metric}] z={zv} ≥ +{rule['reject_z']}σ（行业内极差）")
            elif zv >= rule["warn_z"]:
                warnings.append(f"[{metric}] z={zv} ≥ +{rule['warn_z']}σ（行业内偏差）")

    # 3. 营收 YoY（v1.0 规则不变）
    rev_yoy = _safe_float(f.get("rev_yoy_latest"))
    if rev_yoy <= 0:
        reasons.append(f"[营收 YoY] {rev_yoy:.1f}% ≤ 0%（z-score 不适用此项）")

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "warnings": warnings,
        "z_scores": z,
        "absolute_violations": abs_violations,
        "fallback_to_v10": False,
        "industry_pool_size": pool_size,
    }


def compare_v10_v11(v10: dict, v11: dict) -> dict:
    """对比 v1.0 / v1.1 评分结果，给出 consensus 标签和决策依据"""
    consensus = "AGREE" if v10["grade"] == v11["grade"] else "CONFLICT"
    fallback = (v11.get("v11_meta") or {}).get("fallback_to_v10", False)
    decision_grade = v10["grade"] if fallback else v11["grade"]
    decision_protocol = "v1.0 (fallback)" if fallback else "v1.1"

    audit_flag = None
    if consensus == "CONFLICT":
        audit_flag = (
            f"⚠️ 协议级冲突: v1.0={v10['grade']} vs v1.1={v11['grade']}; "
            f"决策依据 {decision_protocol}"
        )

    return {
        "consensus": consensus,
        "decision_grade": decision_grade,
        "decision_protocol": decision_protocol,
        "audit_flag": audit_flag,
    }


# ========================== v1.2 风险披露版（v6.1 引入；2026-06-01 加） ==========================
# 协议哲学：选美评分从"准入门槛"改为"风险披露"；只过滤"特别丑"，其它全部进 watchlist
# 哲学转折：很多公司不是顶美，但在变美的路上 —— 选美评分应该展示风险维度，决策权回归老板

# v1.2 极端硬过滤（任一触发才 REJECT；强调"持续性 + 极端值"双重确认）
V12_EXTREME_REDLINES = {
    "debt_ratio_max":           90.0,   # 资产负债率绝对上限（极端高杠杆）
    "roe_3y_avg_min":            5.0,   # ROE 3 年均值绝对下限（连续 3 年不赚钱）
    "rev_yoy_neg_consecutive":   2,     # 营收 YoY 连续 N 年 <0%
    "cfo_to_np_low_consecutive": 2,     # CFO/NP 连续 N 年 <0.2
    "net_loss_consecutive":      2,     # 净利润连续 N 年亏损
    "cfo_to_np_extreme":         0.2,   # CFO/NP 极低阈值
}

# v1.2 风险标签 + 仓位建议（仅建议不强制）
V12_TIER_THRESHOLDS = {
    "顶美":   {"score_min": 85, "position_pct_suggest": 7, "emoji": "🌟"},
    "一线":   {"score_min": 70, "position_pct_suggest": 5, "emoji": "💎"},
    "丑小鸭": {"score_min": 50, "position_pct_suggest": 3, "emoji": "⭐"},  # + 高成长 + ROE 加速 才挂此标
    "中性":   {"score_min": 50, "position_pct_suggest": 2, "emoji": "✨"},  # <70 但不算丑小鸭
    "真丑":   {"score_min":  0, "position_pct_suggest": 1, "emoji": "❌"},
}

# 丑小鸭判定（v1.2 核心创新：识别"在变美的路上"）
# growth_score_min 设 22 而非 25：缺季度环比/同比加速数据时，年度高增长 (rev+net 各满分) 已达 22-24
V12_UGLY_DUCK_RULES = {
    "score_max":          70,    # 颜值 <70（不是顶美）
    "growth_score_min":   22,    # 成长性 ≥22/35（年度营收+净利双高速即够；季度数据缺也不卡）
    "roe_acceleration":   True,  # ROE TTM > ROE 3 年均值（在加速）
}


def hard_filter_extreme(f: dict) -> dict:
    """v1.2 极端硬过滤：5 条"持续性 + 极端值"双确认红线

    返回：{"passed": bool, "reasons": [str]}
    """
    reasons: list[str] = []

    # 1. 资产负债率 >90%
    debt = _safe_float(f.get("debt_ratio"))
    if debt > V12_EXTREME_REDLINES["debt_ratio_max"]:
        reasons.append(f"资产负债率 {debt:.1f}% > {V12_EXTREME_REDLINES['debt_ratio_max']}%（极端高杠杆）")

    # 2. ROE 3 年均值 <5%
    roe_3y = _safe_float(f.get("roe_3y_avg") or f.get("roe_ttm"))
    if roe_3y < V12_EXTREME_REDLINES["roe_3y_avg_min"]:
        reasons.append(f"ROE 3 年均值 {roe_3y:.1f}% < {V12_EXTREME_REDLINES['roe_3y_avg_min']}%（连续 3 年不赚钱）")

    # 3. 营收 YoY 连续 2 年 <0%
    rev_yoy_history = f.get("rev_yoy_history", [])  # [近 1 年, 近 2 年, ...]
    if isinstance(rev_yoy_history, list) and len(rev_yoy_history) >= 2:
        if all(_safe_float(v) < 0 for v in rev_yoy_history[:2]):
            reasons.append(f"营收 YoY 连续 2 年 <0%（业务衰退）")
    else:
        # 缺历史 → 看最新一年；若最新一年 ≤-15% 视为衰退确认
        rev_latest = _safe_float(f.get("rev_yoy_latest"))
        if rev_latest <= -15:
            reasons.append(f"营收 YoY {rev_latest:.1f}% 严重衰退（缺历史，单年 ≤-15% 视同 2 年）")

    # 4. CFO/NP 连续 2 年都 <0.2
    cfo_np_history = f.get("cfo_to_np_history", [])
    if isinstance(cfo_np_history, list) and len(cfo_np_history) >= 2:
        if all(_safe_float(v) < V12_EXTREME_REDLINES["cfo_to_np_extreme"] for v in cfo_np_history[:2]):
            reasons.append(f"CFO/NP 连续 2 年 <{V12_EXTREME_REDLINES['cfo_to_np_extreme']}（现金流严重失实）")
    # 单年缺历史时不触发；保守

    # 5. 净利润连续 2 年亏损
    net_history = f.get("net_profit_history", [])
    if isinstance(net_history, list) and len(net_history) >= 2:
        if all(_safe_float(v) < 0 for v in net_history[:2]):
            reasons.append(f"净利润连续 2 年亏损")
    else:
        # 缺历史 → 看 ROE 是否为负（粗略）
        roe_ttm = _safe_float(f.get("roe_ttm"))
        if roe_ttm < 0 and roe_3y < 0:
            reasons.append(f"ROE TTM={roe_ttm:.1f}% & 3 年均值={roe_3y:.1f}% 均为负（疑似连续亏损）")

    return {"passed": len(reasons) == 0, "reasons": reasons}


def compute_quadrant_tag(f: dict, score: float, score_growth: float) -> dict:
    """v1.2 颜值 vs 成长 四象限标签

    返回：{"tag": "顶美"|"一线"|"丑小鸭"|"中性"|"真丑", "emoji": str, "narrative": str}
    """
    roe_ttm = _safe_float(f.get("roe_ttm"))
    roe_3y = _safe_float(f.get("roe_3y_avg") or roe_ttm)
    roe_accelerating = roe_ttm > roe_3y

    # 优先识别"丑小鸭"（v1.2 核心创新）
    is_ugly_duck = (
        score < V12_UGLY_DUCK_RULES["score_max"]
        and score_growth >= V12_UGLY_DUCK_RULES["growth_score_min"]
        and roe_accelerating
    )
    if is_ugly_duck:
        return {
            "tag": "丑小鸭",
            "emoji": V12_TIER_THRESHOLDS["丑小鸭"]["emoji"],
            "narrative": (
                f"颜值 {score:.0f} 偏低但成长 {score_growth:.0f}/35 + "
                f"ROE 加速 (TTM {roe_ttm:.1f}% > 3y {roe_3y:.1f}%) "
                f"→ 在变美的路上"
            ),
            "position_pct_suggest": V12_TIER_THRESHOLDS["丑小鸭"]["position_pct_suggest"],
        }

    # 其它分级（按总分）
    if score >= V12_TIER_THRESHOLDS["顶美"]["score_min"]:
        tag, narrative = "顶美", "全维度优秀，茅台/宁王型已成熟"
    elif score >= V12_TIER_THRESHOLDS["一线"]["score_min"]:
        tag, narrative = "一线", "标准成长，无明显短板"
    elif score >= V12_TIER_THRESHOLDS["中性"]["score_min"]:
        tag, narrative = "中性", f"颜值 {score:.0f} 中等，无加速 → 谨慎参与"
    else:
        tag, narrative = "真丑", f"颜值 {score:.0f} 全维度偏弱 → 严格审视/远离"

    return {
        "tag": tag,
        "emoji": V12_TIER_THRESHOLDS[tag]["emoji"],
        "narrative": narrative,
        "position_pct_suggest": V12_TIER_THRESHOLDS[tag]["position_pct_suggest"],
    }


def evaluate_v12(target: str, target_finance: dict, all_finance: dict) -> dict:
    """v1.2 评估单只标的（风险披露版）

    与 v1.0/v1.1 schema 兼容，新增 v12_meta 字段。

    核心差异：
    1. 极端硬过滤未过 → REJECT（保留 grade=C）
    2. 极端硬过滤过 → 任何 score 都进 watchlist；不再因 score<70 强制 C
    3. 输出 quadrant_tag（顶美/一线/丑小鸭/中性/真丑）+ 仓位建议（仅建议）
    4. 输出 risk_disclosure：列出主要风险维度，给老板决策参考
    """
    f = target_finance
    industry = f.get("industry", "")

    # 1. 极端硬过滤
    extreme = hard_filter_extreme(f)
    if not extreme["passed"]:
        return {
            "ticker": target,
            "industry": industry,
            "score": 0,
            "grade": "C",
            "title": "极端淘汰 (v1.2 极端硬过滤)",
            "hard_filter_pass": False,
            "hard_filter_reasons": extreme["reasons"],
            "position_cap_pct": 0,
            "weakness": "极端硬过滤未通过 (v1.2)",
            "v12_meta": {
                "protocol": "v1.2",
                "decision_mode": "REJECT",
                "extreme_reasons": extreme["reasons"],
            },
        }

    # 2. 100 分加权评分（与 v1.0/v1.1 共用维度计算）
    p, p_b = score_profitability(f)
    g, g_b = score_growth(f)
    s, s_b = score_safety(f)
    v, v_b = score_valuation(f)
    total = round(p + g + s + v, 1)

    # 3. v1.2 四象限标签（替代旧 grade S/A/B/C）
    quadrant = compute_quadrant_tag(f, total, g)

    # 4. v1.1 z-score（如同行业池可用，附在风险披露里）
    pool, group = _industry_pool_for(target, all_finance)
    pool_excl_self = [p_ for p_ in pool if p_.get("_ticker") != str(target)]
    z_data = compute_zscores(f, pool_excl_self)
    has_zscore = not z_data.get("_pool_too_small")

    # 5. 风险披露报告（v1.2 核心：替代旧的"硬过滤 reasons"）
    risk_disclosure: list[str] = []
    opportunity_signals: list[str] = []

    debt = _safe_float(f.get("debt_ratio"))
    if debt > 75:
        risk_disclosure.append(f"⚠️ 资产负债率 {debt:.1f}%（行业偏高，但未达极端）")
    cfo_np = _safe_float(f.get("cfo_to_np"))
    if cfo_np < 0.6:
        risk_disclosure.append(f"⚠️ CFO/净利润 {cfo_np:.2f}（现金流弱于稳健阈值 0.8）")
    nm = _safe_float(f.get("net_margin"))
    if nm < 5:
        risk_disclosure.append(f"⚠️ 净利率 {nm:.1f}%（薄利模式，对营收增长敏感）")

    rev_yoy = _safe_float(f.get("rev_yoy_latest"))
    if rev_yoy >= 30:
        opportunity_signals.append(f"✓ 营收 YoY {rev_yoy:.1f}%（高速增长）")
    roe_ttm = _safe_float(f.get("roe_ttm"))
    roe_3y = _safe_float(f.get("roe_3y_avg") or roe_ttm)
    if roe_ttm > roe_3y * 1.05:
        opportunity_signals.append(f"✓ ROE 加速 (TTM {roe_ttm:.1f}% > 3y {roe_3y:.1f}%)")
    if roe_3y >= 20:
        opportunity_signals.append(f"✓ ROE 3y {roe_3y:.1f}%（高 ROE 持续）")

    # 6. 弱点维度
    dim_scores = {"profitability": p / 30, "growth": g / 35, "safety": s / 25, "valuation": v / 10}
    weakest_dim = min(dim_scores, key=dim_scores.get)
    weakest_label = {
        "profitability": "盈利能力", "growth": "成长性",
        "safety": "财务安全", "valuation": "估值",
    }[weakest_dim]

    # 7. 兼容字段：grade（保留 S/A/B/C 给老协议消费者）
    if total >= 90:    legacy_grade = "S"
    elif total >= 80:  legacy_grade = "A"
    elif total >= 70:  legacy_grade = "B"
    else:              legacy_grade = "C"

    return {
        "ticker": target,
        "industry": industry,
        "score": total,
        "grade": legacy_grade,           # 兼容字段
        "tag": quadrant["tag"],          # v1.2 风险标签
        "tag_emoji": quadrant["emoji"],
        "tag_narrative": quadrant["narrative"],
        "title": f"{quadrant['tag']} {legacy_grade}",
        "hard_filter_pass": True,
        "hard_filter_reasons": [],
        "position_cap_pct_suggest": quadrant["position_pct_suggest"],  # v1.2 仅建议
        "position_cap_pct": quadrant["position_pct_suggest"],          # 兼容字段（不再强制）
        "score_breakdown": {
            "profitability": round(p, 1), "growth": round(g, 1),
            "safety": round(s, 1), "valuation": round(v, 1),
        },
        "score_detail": {
            "profitability": p_b, "growth": g_b,
            "safety": s_b, "valuation": v_b,
        },
        "weakness": f"{weakest_label}（{round(dim_scores[weakest_dim] * 100, 1)}%）",
        "v12_meta": {
            "protocol": "v1.2",
            "decision_mode": "DISCLOSE",   # v1.2 不强制；老板决策
            "quadrant_tag": quadrant["tag"],
            "is_ugly_duck": quadrant["tag"] == "丑小鸭",
            "risk_disclosure": risk_disclosure,
            "opportunity_signals": opportunity_signals,
            "industry_group": group,
            "industry_pool_size": len(pool_excl_self),
            "z_scores": z_data if has_zscore else None,
            "position_cap_is_advice_only": True,
        },
    }


# ========================== 评分细则 ==========================

def score_profitability(f: dict) -> tuple[float, dict]:
    """盈利能力 30 分"""
    breakdown = {}

    roe = f.get("roe_ttm", 0)
    if roe >= 25:    breakdown["roe"] = 15
    elif roe >= 20:  breakdown["roe"] = 13
    elif roe >= 15:  breakdown["roe"] = 10
    elif roe >= 12:  breakdown["roe"] = 7
    else:            breakdown["roe"] = 0

    roic = f.get("roic", 0) or roe * 0.7  # 缺值用 ROE * 0.7 估算
    if roic >= 15:   breakdown["roic"] = 8
    elif roic >= 10: breakdown["roic"] = 5
    elif roic >= 7:  breakdown["roic"] = 3
    else:            breakdown["roic"] = 0

    nm = f.get("net_margin", 0)
    if nm >= 30:   breakdown["net_margin"] = 4
    elif nm >= 20: breakdown["net_margin"] = 3
    elif nm >= 10: breakdown["net_margin"] = 2
    else:          breakdown["net_margin"] = 1

    gm = f.get("gross_margin", 0)
    if gm >= 60:   breakdown["gross_margin"] = 3
    elif gm >= 40: breakdown["gross_margin"] = 2
    elif gm >= 25: breakdown["gross_margin"] = 1
    else:          breakdown["gross_margin"] = 0

    return sum(breakdown.values()), breakdown


def score_growth(f: dict) -> tuple[float, dict]:
    """成长性 35 分"""
    breakdown = {}

    rev = f.get("rev_yoy_latest", 0)
    if rev >= 30:   breakdown["rev_yoy"] = 12
    elif rev >= 20: breakdown["rev_yoy"] = 10
    elif rev >= 15: breakdown["rev_yoy"] = 8
    elif rev >= 10: breakdown["rev_yoy"] = 6
    elif rev >= 5:  breakdown["rev_yoy"] = 4
    else:           breakdown["rev_yoy"] = 1

    # 兼容 np_yoy_latest 和 net_yoy_latest 两种字段名（v1.2 兜底）
    np_v = f.get("np_yoy_latest")
    if np_v is None:
        np_v = f.get("net_yoy_latest", 0)
    np_v = np_v or 0
    if np_v >= 40:    breakdown["np_yoy"] = 12
    elif np_v >= 25:  breakdown["np_yoy"] = 10
    elif np_v >= 15:  breakdown["np_yoy"] = 7
    elif np_v >= 5:   breakdown["np_yoy"] = 4
    else:             breakdown["np_yoy"] = 1

    qoq = f.get("rev_qoq_latest", 0)
    if qoq > 0 and rev > 0:
        breakdown["qoq_accel"] = 6
    elif qoq > 0:
        breakdown["qoq_accel"] = 4
    elif qoq == 0:
        breakdown["qoq_accel"] = 2
    else:
        breakdown["qoq_accel"] = 0

    # 单季同比加速：暂用 np_yoy_latest 是否 > 历史均值的简化代理
    breakdown["yoy_accel"] = 3  # 默认中等

    return sum(breakdown.values()), breakdown


def score_safety(f: dict) -> tuple[float, dict]:
    """财务安全 25 分"""
    breakdown = {}

    debt = f.get("debt_ratio", 0)
    if debt <= 30:   breakdown["debt_ratio"] = 8
    elif debt <= 50: breakdown["debt_ratio"] = 6
    elif debt <= 60: breakdown["debt_ratio"] = 4
    elif debt <= 70: breakdown["debt_ratio"] = 2
    else:            breakdown["debt_ratio"] = 0

    cfo = f.get("cfo_to_np", 0)
    if cfo >= 1.2:   breakdown["cfo_np"] = 10
    elif cfo >= 1.0: breakdown["cfo_np"] = 8
    elif cfo >= 0.9: breakdown["cfo_np"] = 6
    elif cfo >= 0.8: breakdown["cfo_np"] = 4
    else:            breakdown["cfo_np"] = 0

    ibd_ratio = f.get("interest_bearing_debt_ratio", 0)
    if ibd_ratio == 0:    breakdown["ibd"] = 7  # 净现金/无有息债务
    elif ibd_ratio <= 10: breakdown["ibd"] = 5
    elif ibd_ratio <= 25: breakdown["ibd"] = 3
    elif ibd_ratio <= 40: breakdown["ibd"] = 1
    else:                 breakdown["ibd"] = 0

    return sum(breakdown.values()), breakdown


def score_valuation(f: dict) -> tuple[float, dict]:
    """估值 10 分（弱权重）"""
    breakdown = {}

    pe = f.get("pe_ttm", 0)
    if 0 < pe <= 15:   breakdown["pe"] = 5
    elif 15 < pe <= 25: breakdown["pe"] = 4
    elif 25 < pe <= 35: breakdown["pe"] = 3
    elif 35 < pe <= 50: breakdown["pe"] = 2
    elif pe > 50:       breakdown["pe"] = 1
    else:               breakdown["pe"] = 2  # 缺值给中等

    peg = f.get("peg", 0)
    if 0 < peg < 0.5:   breakdown["peg"] = 3
    elif peg < 0.8:     breakdown["peg"] = 2
    elif peg < 1.0:     breakdown["peg"] = 1
    else:               breakdown["peg"] = 0

    div = f.get("dividend_yield", 0)
    if div >= 4:   breakdown["dividend"] = 2
    elif div >= 2: breakdown["dividend"] = 1
    else:          breakdown["dividend"] = 0

    return sum(breakdown.values()), breakdown


def grade_score(score: float) -> tuple[str, str, int]:
    """返回 (字母分级, 称号, 仓位上限百分比)"""
    if score >= 90: return "S", "顶级美女", 7
    if score >= 80: return "A", "一线美女", 5
    if score >= 70: return "B", "准入线",   3
    return "C", "淘汰", 0


def find_weakness(breakdown: dict, dim_max: dict) -> str:
    """找出最弱维度（百分比最低）"""
    ratios = {k: breakdown[k] / dim_max[k] for k in breakdown}
    weakest = min(ratios, key=ratios.get)
    return f"{weakest}（{breakdown[weakest]:.1f}/{dim_max[weakest]}）"


# ========================== 主入口 ==========================

def evaluate(ticker: str, finance_data: dict) -> dict:
    """评估一只标的"""
    f = finance_data.get(ticker) or finance_data.get(ticker.lower(), {})
    if not f:
        return {
            "ticker": ticker,
            "score": 0,
            "grade": "C",
            "title": "数据缺失",
            "hard_filter_pass": False,
            "hard_filter_reasons": ["finance_<date>.json 中无此 ticker"],
            "position_cap_pct": 0,
        }

    industry = f.get("industry", "")

    # 硬过滤
    passed, reasons = hard_filter(f, industry)
    if not passed:
        return {
            "ticker": ticker,
            "industry": industry,
            "score": 0,
            "grade": "C",
            "title": "淘汰",
            "hard_filter_pass": False,
            "hard_filter_reasons": reasons,
            "position_cap_pct": 0,
            "weakness": "硬过滤未通过",
        }

    # 100 分评分
    p, p_b = score_profitability(f)
    g, g_b = score_growth(f)
    s, s_b = score_safety(f)
    v, v_b = score_valuation(f)
    total = round(p + g + s + v, 1)

    grade, title, cap = grade_score(total)

    # 综合最弱维度
    dim_scores = {"profitability": p / 30, "growth": g / 35, "safety": s / 25, "valuation": v / 10}
    weakest_dim = min(dim_scores, key=dim_scores.get)
    weakest_label = {
        "profitability": "盈利能力",
        "growth": "成长性",
        "safety": "财务安全",
        "valuation": "估值",
    }[weakest_dim]

    return {
        "ticker": ticker,
        "industry": industry,
        "score": total,
        "grade": grade,
        "title": title,
        "hard_filter_pass": True,
        "hard_filter_reasons": [],
        "score_breakdown": {
            "profitability": round(p, 1),
            "growth": round(g, 1),
            "safety": round(s, 1),
            "valuation": round(v, 1),
        },
        "score_detail": {
            "profitability": p_b,
            "growth": g_b,
            "safety": s_b,
            "valuation": v_b,
        },
        "weakness": f"{weakest_label}（{round(dim_scores[weakest_dim] * 100, 1)}%）",
        "position_cap_pct": cap,
    }


def evaluate_v11(target: str, target_finance: dict, all_finance: dict) -> dict:
    """v1.1 评估单只标的（z-score 主导）

    与 v1.0 evaluate() 同 schema，新增 v11_meta 字段
    Args:
        target: 目标 ticker
        target_finance: target 的财务字典
        all_finance: finance_<date>.json 中的 tickers dict（含同行业 peers）
    """
    pool, group = _industry_pool_for(target, all_finance)
    pool_excl_self = [p for p in pool if p.get("_ticker") != str(target)]

    f = target_finance
    industry = f.get("industry", "")

    v11 = hard_filter_v11(f, pool_excl_self)

    # 退化：行业池不足 → 走 v1.0 流程
    if v11.get("fallback_to_v10"):
        v10_result = evaluate(target, all_finance)
        v10_result["v11_meta"] = {
            "industry_group": group,
            "industry_pool_size": v11.get("industry_pool_size", 0),
            "fallback_to_v10": True,
            "fallback_reason": f"行业池仅 {v11.get('industry_pool_size', 0)} 家 < {V11_MIN_POOL_SIZE}",
            "z_scores": {},
        }
        return v10_result

    # 硬过滤未过 → 直接 C
    if not v11["passed"]:
        return {
            "ticker": target,
            "industry": industry,
            "score": 0,
            "grade": "C",
            "title": "淘汰 (v1.1 z-score)",
            "hard_filter_pass": False,
            "hard_filter_reasons": v11["reasons"],
            "position_cap_pct": 0,
            "weakness": "硬过滤未通过 (v1.1)",
            "v11_meta": {
                "industry_group": group,
                "industry_pool_size": v11["industry_pool_size"],
                "fallback_to_v10": False,
                "z_scores": v11["z_scores"],
                "warnings": v11["warnings"],
                "absolute_violations": v11["absolute_violations"],
            },
        }

    # 硬过滤过 → 100 分加权评分（与 v1.0 共用）
    p, p_b = score_profitability(f)
    g, g_b = score_growth(f)
    s, s_b = score_safety(f)
    v, v_b = score_valuation(f)
    total = round(p + g + s + v, 1)

    grade, title, cap = grade_score(total)

    dim_scores = {"profitability": p / 30, "growth": g / 35, "safety": s / 25, "valuation": v / 10}
    weakest_dim = min(dim_scores, key=dim_scores.get)
    weakest_label = {
        "profitability": "盈利能力", "growth": "成长性",
        "safety": "财务安全", "valuation": "估值",
    }[weakest_dim]

    return {
        "ticker": target,
        "industry": industry,
        "score": total,
        "grade": grade,
        "title": title,
        "hard_filter_pass": True,
        "hard_filter_reasons": [],
        "score_breakdown": {
            "profitability": round(p, 1), "growth": round(g, 1),
            "safety": round(s, 1), "valuation": round(v, 1),
        },
        "score_detail": {
            "profitability": p_b, "growth": g_b,
            "safety": s_b, "valuation": v_b,
        },
        "weakness": f"{weakest_label}（{round(dim_scores[weakest_dim] * 100, 1)}%）",
        "position_cap_pct": cap,
        "v11_meta": {
            "industry_group": group,
            "industry_pool_size": v11["industry_pool_size"],
            "fallback_to_v10": False,
            "z_scores": v11["z_scores"],
            "warnings": v11["warnings"],
        },
    }


def write_audit_log(today: str, results: dict):
    """写入 audit_log 表（5 号 audit 链可查询）"""
    if not DB_PATH.exists():
        print(f"⚠️  DB 不存在 {DB_PATH}，跳过 audit_log", file=sys.stderr)
        return
    conn = sqlite3.connect(DB_PATH)
    for ticker, r in results.items():
        verdict = "PASS" if r["score"] >= 70 else "FAIL"
        detail = json.dumps({
            "score": r["score"],
            "grade": r["grade"],
            "hard_filter": r["hard_filter_pass"],
            "weakness": r.get("weakness"),
        }, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO audit_log (review_id, script_name, target_role, target_artifact, verdict, detail_json, audit_date)
            VALUES (NULL, 'beauty_score', '2', ?, ?, ?, ?)
            """,
            (ticker, verdict, detail, today),
        )
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="v6.0 选美评分")
    parser.add_argument("--tickers", nargs="*", default=[])
    parser.add_argument("--finance-file", help="指定 finance_<date>.json")
    parser.add_argument("--watchlist", action="store_true")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--no-db", action="store_true", help="不写 audit_log")
    parser.add_argument("--protocol", default="auto",
                        choices=["1.0", "1.1", "1.2", "auto"],
                        help="评分协议版本：1.0=绝对阈值；1.1=z-score；1.2=风险披露版（推荐）；auto=v1.2（默认）")
    args = parser.parse_args()

    today = args.date
    protocol = args.protocol

    # 1. 加载财务数据
    if args.finance_file:
        finance_path = Path(args.finance_file)
    else:
        finance_path = FINANCE_DIR / f"finance_{today}.json"
    if not finance_path.exists():
        print(f"❌ {finance_path} 不存在。先跑 finance_collector.py")
        sys.exit(1)
    finance = json.loads(finance_path.read_text(encoding="utf-8"))
    tickers_data = finance.get("tickers", {})

    # 2. 确定要评估的 ticker 列表
    targets = list(args.tickers) if args.tickers else list(tickers_data.keys())

    if args.watchlist:
        wl_path = SKILL_HOME / "outputs" / "02_industry" / "02_Watchlist.md"
        if wl_path.exists():
            import re
            content = wl_path.read_text(encoding="utf-8")
            for m in re.finditer(r"\b(\d{6})\b", content):
                targets.append(m.group(1))
            targets = list(dict.fromkeys(targets))

    print(f"💄 v6.1 beauty_score | date={today} | protocol={protocol} | tickers={len(targets)}")

    # 3. 逐个评分（v1.0 / v1.1 / v1.2 / auto）
    # auto 模式默认走 v1.2（风险披露），并附带 v1.0 / v1.1 结果用于 5 号 audit 协议级冲突检测
    results = {}
    conflict_count = 0
    for t in targets:
        target_finance_dict = tickers_data.get(t, {})
        v10_r = evaluate(t, tickers_data) if protocol in ("1.0", "auto") and t in tickers_data else None
        v11_r = evaluate_v11(t, target_finance_dict, tickers_data) if protocol in ("1.1", "auto") and t in tickers_data else None
        v12_r = evaluate_v12(t, target_finance_dict, tickers_data) if protocol in ("1.2", "auto") and t in tickers_data else None

        if protocol == "auto" and v12_r:
            # auto 默认 v1.2 决策；v1.0/v1.1 作为对照参考
            r = dict(v12_r)
            if v10_r and v11_r:
                cmp = compare_v10_v11(v10_r, v11_r)
                r["v10_result"] = {"grade": v10_r["grade"], "score": v10_r["score"], "title": v10_r["title"],
                                  "hard_filter_reasons": v10_r.get("hard_filter_reasons", [])}
                r["v11_result"] = {"grade": v11_r["grade"], "score": v11_r["score"], "title": v11_r["title"]}
                r["consensus_v10_v11"] = cmp["consensus"]
                if cmp["consensus"] == "CONFLICT":
                    conflict_count += 1
                r["audit_flag"] = cmp["audit_flag"]
            r["decision_protocol"] = "v1.2"
        elif protocol == "1.2" and v12_r:
            r = v12_r
            r["decision_protocol"] = "v1.2"
        elif protocol == "1.1" and v11_r:
            r = v11_r
            r["decision_protocol"] = "v1.1"
        elif v10_r:
            r = v10_r
            r["decision_protocol"] = "v1.0"
        else:
            r = {"ticker": t, "grade": "C", "score": 0, "title": "数据缺失", "hard_filter_pass": False,
                 "hard_filter_reasons": ["finance_<date>.json 中无此 ticker"], "position_cap_pct": 0}

        results[t] = r
        # 显示行（v1.2 用 emoji + tag；老协议用 grade）
        if r.get("v12_meta"):
            emoji = r.get("tag_emoji", "❓")
            tag = r.get("tag", "?")
            line = f"  {emoji} {t} {tag:6s} score={r['score']:5.1f} 建议仓位 ≤{r.get('position_cap_pct_suggest', 0)}%"
            opp = r.get("v12_meta", {}).get("opportunity_signals", [])
            risk = r.get("v12_meta", {}).get("risk_disclosure", [])
            if opp:
                line += f"  | {len(opp)} 机会"
            if risk:
                line += f" / {len(risk)} 风险"
        else:
            emoji = {"S": "🌟", "A": "💎", "B": "✨", "C": "❌"}.get(r.get("grade"), "❓")
            line = f"  {emoji} {t} {r.get('title','?'):18s} score={r.get('score',0):5.1f} cap={r.get('position_cap_pct', 0)}%"
        if r.get("audit_flag"):
            line += f"  {r['audit_flag']}"
        print(line)
        if r.get("hard_filter_reasons"):
            for reason in r["hard_filter_reasons"][:3]:
                print(f"     ⛔ {reason}")
        # v1.2 风险/机会简报（仅 1 行总结）
        if r.get("v12_meta"):
            for sig in r["v12_meta"].get("opportunity_signals", [])[:2]:
                print(f"     {sig}")
            for risk in r["v12_meta"].get("risk_disclosure", [])[:2]:
                print(f"     {risk}")

    # 4. 输出 JSON
    output = {
        "date": today,
        "generated_by": f"beauty_score.py [v6.1, protocol={protocol}]",
        "protocol_version": "1.2" if protocol in ("1.2", "auto") else protocol,
        "tickers": results,
        "summary": {
            "total": len(results),
            # v1.2 风险标签统计
            "v12_顶美":   sum(1 for r in results.values() if r.get("tag") == "顶美"),
            "v12_一线":   sum(1 for r in results.values() if r.get("tag") == "一线"),
            "v12_丑小鸭": sum(1 for r in results.values() if r.get("tag") == "丑小鸭"),
            "v12_中性":   sum(1 for r in results.values() if r.get("tag") == "中性"),
            "v12_真丑":   sum(1 for r in results.values() if r.get("tag") == "真丑"),
            "v12_极端淘汰": sum(1 for r in results.values() if r.get("v12_meta", {}).get("decision_mode") == "REJECT"),
            # v1.0/v1.1 协议级冲突计数（5 号 audit 关注）
            "v10_v11_conflicts": conflict_count,
        },
    }
    out_path = FINANCE_DIR / f"beauty_{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 已写入 {out_path}")
    s = output["summary"]
    print(f"📊 v1.2 风险标签: 顶美={s['v12_顶美']} 一线={s['v12_一线']} 丑小鸭={s['v12_丑小鸭']} 中性={s['v12_中性']} 真丑={s['v12_真丑']} 极端淘汰={s['v12_极端淘汰']}")
    if protocol == "auto" and conflict_count > 0:
        print(f"⚠️  v1.0 / v1.1 协议级冲突 {conflict_count} 起，5 号 audit 应特别关注")

    # 5. 写 audit_log
    if not args.no_db:
        write_audit_log(today, results)
        print(f"📝 audit_log 已写入 {DB_PATH}")

    # 退出码：所有都被极端淘汰（v1.2）或都是 C 级（v1.0）则 1
    extreme_count = output["summary"].get("v12_极端淘汰", 0)
    legacy_c = output["summary"].get("C", 0)
    if (extreme_count or legacy_c) >= output["summary"]["total"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
