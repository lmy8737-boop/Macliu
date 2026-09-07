"""
Alpha 引擎 — 4号交易员的多维 Alpha 信号生成器
==================================================
v4.6 新增：在缠论 Beta 基础上叠加 4 个独立 Alpha 维度

四大模块：
  A. 多因子量化模型（动量/价值/质量/波动率/盈利修正）
  B. 资金流/筹码博弈（北向/融资融券/大宗/龙虎榜/ETF份额）
  C. 事件驱动引擎（财报/政策/并购回购/行业突发）
  D. 跨资产联动（美债利率/美元/铜油/VIX → regime判断）

使用：
  from alpha_engine import get_alpha_signals, fuse_signals

  alpha = get_alpha_signals("sh510300")
  final = fuse_signals(chanlun_strength=3, direction="LONG", alpha=alpha)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
#  模块 A：多因子量化模型
# ═══════════════════════════════════════════════════════════════════════

def calc_factor_score(ticker: str) -> dict:
    """
    计算多因子综合得分（-100 到 +100）

    因子权重：
    - 动量 (30%): 20日/60日/120日涨跌幅排名
    - 价值 (20%): PE/PB 在历史5年的分位数（越低越好）
    - 质量 (25%): ROE 趋势 + 经营现金流/净利润
    - 波动率 (10%): 低波异象（低波动反而跑赢）
    - 盈利修正 (15%): EPS 一致预期变动方向
    """
    factors = {
        "momentum_score": _calc_momentum(ticker),
        "value_score": _calc_value(ticker),
        "quality_score": _calc_quality(ticker),
        "volatility_score": _calc_volatility(ticker),
        "earnings_revision_score": _calc_earnings_revision(ticker),
    }

    # 加权综合
    weights = {
        "momentum_score": 0.30,
        "value_score": 0.20,
        "quality_score": 0.25,
        "volatility_score": 0.10,
        "earnings_revision_score": 0.15,
    }

    composite = sum(factors[k] * weights[k] for k in weights)
    composite = max(-100, min(100, composite))  # 限制范围

    return {
        "ticker": ticker,
        "composite_score": round(composite, 1),
        "factors": factors,
        "signal": "BULLISH" if composite > 30 else ("BEARISH" if composite < -30 else "NEUTRAL"),
        "bonus": 1 if composite > 50 else (-1 if composite < -50 else 0),
    }


def _calc_momentum(ticker: str) -> float:
    """动量因子：基于价格趋势"""
    try:
        result = subprocess.run(
            ["npx", "-y", "westock-data-clawhub@1.0.4", "kline", ticker, "--period", "day", "--limit", "120"],
            capture_output=True, text=True, timeout=30
        )
        lines = result.stdout.strip().split("\n")
        closes = []
        for line in lines[2:]:
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if len(cols) >= 6:
                try:
                    closes.append(float(cols[2]))  # close price
                except ValueError:
                    continue

        if len(closes) < 60:
            return 0

        # 计算各期动量
        ret_20 = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 else 0
        ret_60 = (closes[-1] / closes[-60] - 1) * 100 if len(closes) >= 60 else 0
        ret_120 = (closes[-1] / closes[-120] - 1) * 100 if len(closes) >= 120 else 0

        # 综合动量得分 (-100 to 100)
        raw = ret_20 * 0.5 + ret_60 * 0.3 + ret_120 * 0.2
        return max(-100, min(100, raw * 2))  # 缩放

    except Exception:
        return 0


def _calc_value(ticker: str) -> float:
    """价值因子：PE/PB 历史分位（越低=越便宜=得分越高）"""
    # 占位实现：需要接 neodata-financial-search 获取 PE/PB 历史数据
    # 返回 -100(极贵) 到 +100(极便宜)
    return 0  # 默认中性，实际运行时由 LLM Agent 通过 neodata 查询填充


def _calc_quality(ticker: str) -> float:
    """质量因子：ROE 趋势 + 现金流质量"""
    return 0  # 默认中性，由 Agent 查询填充


def _calc_volatility(ticker: str) -> float:
    """波动率因子：低波异象（低波=正分）"""
    try:
        result = subprocess.run(
            ["npx", "-y", "westock-data-clawhub@1.0.4", "kline", ticker, "--period", "day", "--limit", "60"],
            capture_output=True, text=True, timeout=30
        )
        lines = result.stdout.strip().split("\n")
        closes = []
        for line in lines[2:]:
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if len(cols) >= 6:
                try:
                    closes.append(float(cols[2]))
                except ValueError:
                    continue

        if len(closes) < 20:
            return 0

        # 计算日收益率标准差
        returns = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        daily_vol = variance ** 0.5
        annual_vol = daily_vol * (252 ** 0.5) * 100

        # 低波=正分（低波异象）
        if annual_vol < 15:
            return 50
        elif annual_vol < 25:
            return 20
        elif annual_vol < 40:
            return 0
        elif annual_vol < 60:
            return -30
        else:
            return -60

    except Exception:
        return 0


def _calc_earnings_revision(ticker: str) -> float:
    """盈利修正因子：EPS 一致预期变动"""
    return 0  # 由 Agent 通过 neodata 查询填充


# ═══════════════════════════════════════════════════════════════════════
#  模块 B：资金流/筹码博弈
# ═══════════════════════════════════════════════════════════════════════

def get_capital_flow(ticker: str) -> dict:
    """
    资金流信号

    综合信号来源：
    - 北向资金（沪/深股通）连续 N 日净流入/出
    - 融资融券余额变动方向
    - 大宗交易折溢价
    - 龙虎榜机构席位净买入
    - ETF份额变动（相关ETF）

    输出：BULLISH / BEARISH / NEUTRAL + 强度 (0-1)
    """
    # 这些数据需要通过 neodata-financial-search 实时查询
    # 此处定义框架，实际由 4号 Agent 在运行时通过 MCP 工具获取

    return {
        "ticker": ticker,
        "northbound_flow": None,       # 北向资金近5日累计（亿）
        "margin_change": None,          # 融资余额5日变动
        "block_trade_premium": None,    # 大宗交易平均折溢价
        "institution_net_buy": None,    # 龙虎榜机构净买入
        "etf_shares_change": None,      # 相关ETF份额变动

        "signal": "NEUTRAL",            # BULLISH / BEARISH / NEUTRAL
        "strength": 0,                  # 0-1
        "bonus": 0,                     # +0.5 / -0.5 / 0

        "note": "需要通过 neodata-financial-search 查询实时数据填充",
    }


# ═══════════════════════════════════════════════════════════════════════
#  模块 C：事件驱动引擎
# ═══════════════════════════════════════════════════════════════════════

def scan_events(ticker: str) -> dict:
    """
    事件扫描器

    事件类型 & 计分规则：
    | 事件 | 方向 | 冲击强度 | 持续性 |
    |------|------|---------|--------|
    | 财报超预期 >20% | +1 | 高 | 1-2季度 |
    | 财报不及预期 >10% | -1 | 高 | 1-2季度 |
    | 政策利好（补贴/放开）| +1 | 中高 | 持续性强 |
    | 政策利空（限制/处罚）| -1 | 中高 | 需评估 |
    | 回购/大股东增持 | +0.5 | 中 | 3-6月 |
    | 大股东减持/质押 | -0.5 | 中 | 持续 |
    | 行业涨价/限产 | +0.5 | 中 | 看供需 |
    | 利空出尽（利空落地+不跌）| +1 | 高 | 反转信号 |

    特殊模式：
    - "利空出尽" = 利空事件已公布 + 股价不再创新低 + 成交量萎缩
      → 这是最强买入信号之一（参考 FUTU 案例）
    """

    return {
        "ticker": ticker,
        "events": [],  # 由 Agent 实时扫描公告/新闻填充
        "signal": "NONE",  # CATALYST / RISK / NONE
        "bonus": 0,  # +1 / -1 / 0
        "mode": None,  # "利空出尽" / "催化剂临近" / None
        "note": "需要 Agent 通过 neodata + WebSearch 扫描最近 30 日公告/新闻",
    }


# ═══════════════════════════════════════════════════════════════════════
#  模块 D：跨资产联动
# ═══════════════════════════════════════════════════════════════════════

def get_macro_regime() -> dict:
    """
    跨资产联动判断 → 输出 RISK_ON / RISK_OFF / NEUTRAL

    传导逻辑：
    - 美债10Y利率↑ → 成长股/高估值↓ → RISK_OFF for growth
    - 美元DXY↑ → 新兴市场/大宗商品↓ → RISK_OFF for EM/commodities
    - 铜/油价↑ → 通胀预期 → 资源股受益但科技股承压
    - VIX > 25 → 系统性避险 → RISK_OFF
    - 人民币贬值 → 出口受益 / 港股承压

    实际数据获取：
    - VIX: westock-data usVIX
    - 美元: westock-data usDXY 或 WebSearch "dollar index"
    - 美债: WebSearch "US 10-year treasury yield"
    - 铜: westock-data 或 WebSearch "copper price LME"
    """

    return {
        "vix": None,
        "us_10y_yield": None,
        "dxy": None,
        "copper_price": None,
        "cny_trend": None,

        "regime": "NEUTRAL",  # RISK_ON / RISK_OFF / NEUTRAL
        "adj": 0,  # 0 (neutral/risk_on) or -1 (risk_off)

        "transmission_notes": [],
        "note": "需要 Agent 查询 VIX/美债/美元/铜等实时数据",
    }


# ═══════════════════════════════════════════════════════════════════════
#  信号融合
# ═══════════════════════════════════════════════════════════════════════

def fuse_signals(
    chanlun_strength: int,
    direction: str,
    alpha: dict = None,
) -> dict:
    """
    信号融合公式：
    final_strength = 缠论基础强度
        + factor_score_bonus (±1)
        + capital_flow_bonus (±0.5)
        + event_bonus (±1)
        + macro_regime_adj (0 or -1)
        + finrl_bonus (±1, 如有)

    最终只有 final_strength ≥ 3 才输出信号
    """
    if alpha is None:
        alpha = {}

    factor_bonus = alpha.get("factor", {}).get("bonus", 0)
    flow_bonus = alpha.get("capital_flow", {}).get("bonus", 0)
    event_bonus = alpha.get("event", {}).get("bonus", 0)
    regime_adj = alpha.get("macro_regime", {}).get("adj", 0)
    finrl_bonus = alpha.get("finrl", {}).get("final_strength_delta", 0)

    final = chanlun_strength + factor_bonus + flow_bonus + event_bonus + regime_adj + finrl_bonus
    final = max(0, min(6, final))  # 限制 0-6

    breakdown = {
        "chanlun_base": chanlun_strength,
        "factor_bonus": factor_bonus,
        "capital_flow_bonus": flow_bonus,
        "event_bonus": event_bonus,
        "macro_regime_adj": regime_adj,
        "finrl_bonus": finrl_bonus,
        "final_strength": round(final, 1),
    }

    # 判断是否输出
    if final >= 3:
        action = "SIGNAL"
    elif final >= 2:
        action = "WATCH"
    else:
        action = "PASS"

    return {
        "direction": direction,
        "final_strength": round(final, 1),
        "action": action,
        "breakdown": breakdown,
        "recommendation": _strength_to_position(final),
    }


def _strength_to_position(strength: float) -> str:
    """信号强度 → 建议仓位"""
    if strength >= 5:
        return "5-7%（S级信号）"
    elif strength >= 4:
        return "3-5%（A级信号）"
    elif strength >= 3:
        return "1-3%（B级信号）"
    else:
        return "不建仓"


# ═══════════════════════════════════════════════════════════════════════
#  综合入口
# ═══════════════════════════════════════════════════════════════════════

def get_alpha_signals(ticker: str) -> dict:
    """
    获取完整 Alpha 信号集合

    4号交易员在每只标的上调用此函数，获取缠论之外的所有 Alpha 维度
    """
    return {
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "factor": calc_factor_score(ticker),
        "capital_flow": get_capital_flow(ticker),
        "event": scan_events(ticker),
        "macro_regime": get_macro_regime(),
    }


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Alpha 引擎 — 4号交易员多维信号生成器")
        print("用法: python3 alpha_engine.py --test <ticker>")
        print("      python3 alpha_engine.py --fuse <ticker> <chanlun_strength> <direction>")
        sys.exit(0)

    if sys.argv[1] == "--test":
        ticker = sys.argv[2] if len(sys.argv) > 2 else "sh510300"
        print(f"\n📊 Alpha 引擎测试: {ticker}")
        print("=" * 60)
        alpha = get_alpha_signals(ticker)
        print(json.dumps(alpha, ensure_ascii=False, indent=2, default=str))

    elif sys.argv[1] == "--fuse":
        ticker = sys.argv[2] if len(sys.argv) > 2 else "sh510300"
        strength = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        direction = sys.argv[4] if len(sys.argv) > 4 else "LONG"

        print(f"\n🔀 信号融合: {ticker} | 缠论强度={strength} | 方向={direction}")
        print("=" * 60)
        alpha = get_alpha_signals(ticker)
        fused = fuse_signals(strength, direction, alpha)
        print(json.dumps(fused, ensure_ascii=False, indent=2, default=str))
