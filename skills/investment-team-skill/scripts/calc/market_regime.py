"""
市场环境仪表盘 — 5号监工的三层交通灯系统
==================================================
v4.6 新增：在 7 条静态红线之上叠加动态市场环境监控

三层交通灯：
  Layer 1: 市场环境（VIX/宽度/趋势/波动率/情绪）← 最高优先级
  Layer 2: 流动性（SHIBOR/信用利差/北向资金/TED）
  Layer 3: 地缘政治（中美/台海/中东/制裁）

输出：
  - 每层独立的 🟢绿/🟡黄/🔴红 灯色
  - 综合操作指令（正常/审慎/防御/全面防御）

使用：
  python3 market_regime.py            # 输出当日三层灯色
  python3 market_regime.py --json     # JSON 格式输出
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
#  Layer 1: 市场环境（最高优先级）
# ═══════════════════════════════════════════════════════════════════════

def check_vix() -> dict:
    """
    VIX 恐慌指数
    🟢 <18: 市场平静，正常运作
    🟡 18-28: 波动加大，审慎
    🔴 >28: 恐慌模式，防御
    """
    # 实际运行时通过 westock-data 获取 VIX
    # 此处为框架，Agent 运行时填充
    return {
        "indicator": "VIX",
        "value": None,
        "thresholds": {"green": "<18", "yellow": "18-28", "red": ">28"},
        "color": "UNKNOWN",
        "action_if_red": "总仓位上限降到60%",
        "data_source": "westock-data usVIX 或 WebSearch 'CBOE VIX index'",
    }


def check_market_breadth() -> dict:
    """
    市场宽度（涨跌家数比）
    🟢 >60% 上涨: 普涨行情
    🟡 40-60%: 分化
    🔴 <40%: 普跌，系统性风险
    """
    return {
        "indicator": "市场宽度（A股涨跌比）",
        "value": None,
        "thresholds": {"green": ">60%上涨", "yellow": "40-60%", "red": "<40%"},
        "color": "UNKNOWN",
        "action_if_red": "禁止新建仓",
        "data_source": "neodata-financial-search '今日A股涨跌统计'",
    }


def check_trend_vs_ma() -> dict:
    """
    主要指数 vs 均线位置
    🟢 沪深300 > 20日MA: 趋势向上
    🟡 在20日MA ±3% 内: 震荡
    🔴 < 20日MA 且 < 60日MA: 趋势向下
    """
    return {
        "indicator": "指数趋势（沪深300 vs MA）",
        "value": None,
        "thresholds": {"green": ">20MA", "yellow": "±3%内", "red": "<20MA且<60MA"},
        "color": "UNKNOWN",
        "action_if_red": "只减不加",
        "data_source": "westock-data sh510300 --period day --limit 60",
    }


def check_volatility_regime() -> dict:
    """
    波动率Regime（历史波动率）
    🟢 低波 HV < 15%: 稳定期
    🟡 中波 15-30%: 正常
    🔴 高波 > 30%: 动荡期
    """
    return {
        "indicator": "波动率Regime（20日HV年化）",
        "value": None,
        "thresholds": {"green": "HV<15%", "yellow": "15-30%", "red": "HV>30%"},
        "color": "UNKNOWN",
        "action_if_red": "所有持仓仓位减半",
        "data_source": "基于 westock-data K线计算",
    }


def check_sentiment() -> dict:
    """
    A股市场情绪（换手率+融资变动）
    🟢 正常: 日均换手1-3%
    🟡 偏热/偏冷
    🔴 极端: 换手率 >5%（过热）或 融资连续5日大幅流出
    """
    return {
        "indicator": "市场情绪（换手率/融资变动）",
        "value": None,
        "thresholds": {"green": "正常换手", "yellow": "偏热/偏冷", "red": "极端（>5%换手或融资暴降）"},
        "color": "UNKNOWN",
        "action_if_red": "极端过热→分批减仓；极端过冷→逆向信号（可能是底）",
        "data_source": "neodata-financial-search '全市场换手率' + '融资余额变动'",
    }


# ═══════════════════════════════════════════════════════════════════════
#  Layer 2: 流动性
# ═══════════════════════════════════════════════════════════════════════

def check_interbank_rate() -> dict:
    """
    银行间利率（SHIBOR/DR007）
    🟢 平稳: DR007 在 ±20bp 政策利率附近
    🟡 季末跳升: 超出 30-50bp
    🔴 异常飙升: 超出 50bp+
    """
    return {
        "indicator": "银行间利率（DR007）",
        "value": None,
        "thresholds": {"green": "±20bp", "yellow": "30-50bp偏离", "red": ">50bp飙升"},
        "color": "UNKNOWN",
        "action_if_red": "警惕赎回潮，减持小盘/低流动性标的",
        "data_source": "neodata-financial-search 'DR007最新' 或 WebSearch 'SHIBOR'",
    }


def check_credit_spread() -> dict:
    """
    信用利差
    🟢 收窄/平稳
    🟡 走扩 < 50bp
    🔴 急速走扩 > 50bp
    """
    return {
        "indicator": "信用利差（AA-国债）",
        "value": None,
        "thresholds": {"green": "收窄/平稳", "yellow": "走扩<50bp", "red": "急速走扩>50bp"},
        "color": "UNKNOWN",
        "action_if_red": "减持高杠杆标的（如万国数据、高负债民企）",
        "data_source": "neodata-financial-search '信用利差' 或 WebSearch",
    }


def check_northbound_flow() -> dict:
    """
    北向资金
    🟢 净流入
    🟡 小幅流出 < 50亿/日
    🔴 单日大幅流出 > 100亿
    """
    return {
        "indicator": "北向资金",
        "value": None,
        "thresholds": {"green": "净流入", "yellow": "流出<50亿", "red": "单日流出>100亿"},
        "color": "UNKNOWN",
        "action_if_red": "港股/A股蓝筹持仓减半；外资重仓股优先止损",
        "data_source": "neodata-financial-search '北向资金今日'",
    }


def check_usd_liquidity() -> dict:
    """
    美元流动性（TED Spread = LIBOR - T-Bill）
    🟢 < 0.3%: 正常
    🟡 0.3-0.5%: 紧张
    🔴 > 0.5%: 流动性危机（类似2020.3/2008.9）
    """
    return {
        "indicator": "美元流动性（TED Spread）",
        "value": None,
        "thresholds": {"green": "<0.3%", "yellow": "0.3-0.5%", "red": ">0.5%"},
        "color": "UNKNOWN",
        "action_if_red": "全面避险：增加现金+黄金；减持美元计价资产",
        "data_source": "WebSearch 'TED spread current' 或 'LIBOR OIS spread'",
    }


# ═══════════════════════════════════════════════════════════════════════
#  Layer 3: 地缘政治
# ═══════════════════════════════════════════════════════════════════════

def check_us_china() -> dict:
    """
    中美关系
    🟢 对话/缓和: 高层会晤、贸易协议进展
    🟡 言辞升级: 制裁威胁、实体清单扩大传闻
    🔴 实质行动: 新制裁落地、军事对峙
    """
    return {
        "indicator": "中美关系",
        "value": None,
        "thresholds": {"green": "对话/缓和", "yellow": "言辞升级/传闻", "red": "实质制裁/军事对峙"},
        "color": "UNKNOWN",
        "action_if_red": "中概/港股止损线收紧10%；半导体/AI供应链标的评估影响",
        "data_source": "WebSearch '中美关系最新 2026' 近24小时",
    }


def check_taiwan_strait() -> dict:
    """
    台海局势
    🟢 平静
    🟡 军演/绕台/言辞升温
    🔴 实质性封锁/冲突信号
    """
    return {
        "indicator": "台海局势",
        "value": None,
        "thresholds": {"green": "平静", "yellow": "军演/绕台", "red": "封锁/冲突"},
        "color": "UNKNOWN",
        "action_if_red": "台湾半导体供应链标的（TSMC相关）立即止损；增加黄金",
        "data_source": "WebSearch '台海 军事 2026' 近7日",
    }


def check_middle_east() -> dict:
    """
    中东/俄乌局势
    🟢 缓和/停火进展
    🟡 局部升级
    🔴 大规模冲突/石油供应中断
    """
    return {
        "indicator": "中东/俄乌",
        "value": None,
        "thresholds": {"green": "缓和", "yellow": "局部升级", "red": "大规模冲突"},
        "color": "UNKNOWN",
        "action_if_red": "加仓黄金ETF/能源ETF对冲；检查运输/航运相关标的",
        "data_source": "WebSearch '中东局势 OR 俄乌冲突 最新'",
    }


def check_sanctions() -> dict:
    """
    制裁/出口管制升级
    🟢 无新动作
    🟡 传闻/草案阶段
    🔴 正式发布新制裁
    """
    return {
        "indicator": "制裁/出口管制",
        "value": None,
        "thresholds": {"green": "无新动作", "yellow": "传闻/草案", "red": "正式发布"},
        "color": "UNKNOWN",
        "action_if_red": "受限标的（半导体/AI芯片相关）止损线收紧；评估替代受益标的",
        "data_source": "WebSearch 'US sanctions China 2026' OR '出口管制升级'",
    }


# ═══════════════════════════════════════════════════════════════════════
#  综合仪表盘
# ═══════════════════════════════════════════════════════════════════════

def get_market_environment() -> dict:
    """
    三层交通灯综合输出

    决策逻辑：
    - 全绿 → 正常运作，最大仓位80%
    - 任一黄 → 审慎运作，新建仓需额外确认
    - 任一红 → 防御模式（根据哪层红采取不同措施）
    - 两红以上 → 全面防御：总仓位降到40%，只留核心底仓
    """

    layer1 = {
        "name": "市场环境",
        "priority": "最高",
        "indicators": [
            check_vix(),
            check_market_breadth(),
            check_trend_vs_ma(),
            check_volatility_regime(),
            check_sentiment(),
        ],
    }

    layer2 = {
        "name": "流动性",
        "priority": "高",
        "indicators": [
            check_interbank_rate(),
            check_credit_spread(),
            check_northbound_flow(),
            check_usd_liquidity(),
        ],
    }

    layer3 = {
        "name": "地缘政治",
        "priority": "中高",
        "indicators": [
            check_us_china(),
            check_taiwan_strait(),
            check_middle_east(),
            check_sanctions(),
        ],
    }

    # 每层取最差灯色
    def worst_color(layer):
        colors = [ind["color"] for ind in layer["indicators"]]
        if "RED" in colors:
            return "RED"
        elif "YELLOW" in colors:
            return "YELLOW"
        elif "GREEN" in colors:
            return "GREEN"
        return "UNKNOWN"

    l1_color = worst_color(layer1)
    l2_color = worst_color(layer2)
    l3_color = worst_color(layer3)

    # 综合判断
    red_count = sum(1 for c in [l1_color, l2_color, l3_color] if c == "RED")

    if red_count >= 2:
        overall = "FULL_DEFENSE"
        max_position = 40
        instruction = "全面防御：总仓位降到40%，只留核心底仓"
    elif red_count == 1:
        overall = "DEFENSE"
        max_position = 60
        instruction = "防御模式：总仓位上限60%，禁止新建仓"
    elif "YELLOW" in [l1_color, l2_color, l3_color]:
        overall = "CAUTIOUS"
        max_position = 70
        instruction = "审慎运作：新建仓需4号+5号双确认"
    else:
        overall = "NORMAL"
        max_position = 80
        instruction = "正常运作：按常规流程执行"

    return {
        "timestamp": datetime.now().isoformat(),
        "layers": {
            "market_environment": {"color": l1_color, "detail": layer1},
            "liquidity": {"color": l2_color, "detail": layer2},
            "geopolitics": {"color": l3_color, "detail": layer3},
        },
        "overall": {
            "mode": overall,
            "max_position_pct": max_position,
            "instruction": instruction,
            "red_count": red_count,
        },
    }


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    env = get_market_environment()

    if "--json" in sys.argv:
        print(json.dumps(env, ensure_ascii=False, indent=2, default=str))
    else:
        print("\n" + "=" * 60)
        print("🚦 市场环境仪表盘 — 5号监工每日首检")
        print("=" * 60)
        print(f"  时间: {env['timestamp'][:19]}")
        print()

        emoji_map = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴", "UNKNOWN": "⚪"}

        for layer_name, layer_data in env["layers"].items():
            color = layer_data["color"]
            detail = layer_data["detail"]
            print(f"  {emoji_map[color]} Layer: {detail['name']}（优先级: {detail['priority']}）")
            for ind in detail["indicators"]:
                ind_color = ind["color"]
                print(f"     {emoji_map[ind_color]} {ind['indicator']}: {ind.get('value', '待查询')}")
            print()

        overall = env["overall"]
        mode_emoji = {"NORMAL": "🟢", "CAUTIOUS": "🟡", "DEFENSE": "🔴", "FULL_DEFENSE": "🔴🔴"}
        print(f"  {'='*50}")
        print(f"  {mode_emoji.get(overall['mode'], '⚪')} 综合模式: {overall['mode']}")
        print(f"  📊 最大仓位: {overall['max_position_pct']}%")
        print(f"  📋 操作指令: {overall['instruction']}")
        print(f"  {'='*50}")
        print()
        print("  ⚠️ 注意：灯色标记为 UNKNOWN 的指标需要 Agent 在运行时通过")
        print("     neodata/WebSearch 查询实时数据后填充。")
