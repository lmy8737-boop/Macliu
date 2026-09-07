"""
etf_chip_analysis.py  — 国家队 ETF & 宽基指数筹码水位分析引擎
=============================================================
职责：
  - 拉取 ETF / 宽基指数 日线 K 线（默认 250 日）
  - 用换手率加权的筹码模型计算价格分布
  - 输出筹码水位分位、主力均价、密集峰区间、支撑阻力
  - 覆盖：A股宽基(50/300/500/1000/2000) + 风格板块 + 港美外围 + 行业托底

用法：
  # 日常快速模式（宽基5只）
  python3 etf_chip_analysis.py sh510050 sh510300 sh510500 sz159845 sz159852

  # 单只
  python3 etf_chip_analysis.py sh510300

  # 完整模式（不带参数，运行全部 DEFAULT_BASKET）
  python3 etf_chip_analysis.py

输出：
  ./engine/data/chips/chip_analysis_YYYY-MM-DD.json
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# ─── ETF 完整清单（4层，v4.2）─────────────────────────────────────────
# 格式：code → 中文名

# 第一层：宽基核心（必算，日常默认组合）
LAYER1_BROAD = {
    "sh510050": "上证50ETF（汇金核心）",
    "sh510300": "沪深300ETF（汇金重仓）",
    "sh510500": "中证500ETF（中盘）",
    "sz159845": "中证1000ETF（小盘）",
    "sz159852": "中证2000ETF（微盘）",
}

# 第二层：A股风格/板块
LAYER2_STYLE = {
    "sz159915": "创业板ETF（成长/科技）",
    "sh588050": "科创50ETF（科创板）",
    "sh588080": "科创100ETF（科创中小）",
    "sh512100": "中证500ETF-A（备用300交叉校验）",
    "sz159920": "中证A股ETF（全A）",
}

# 第三层：港股/美股（外围锚点）
LAYER3_OVERSEAS = {
    "sz159633": "恒生科技ETF（港科技）",
    "sz159922": "恒生ETF（港大盘）",
    "sh513100": "纳指100ETF（美科技）",
    "sh513500": "标普500ETF（美大盘）",
    "sh513050": "中概互联ETF（中美科技）",
}

# 第四层：行业托底 / 避险
LAYER4_SECTOR = {
    "sh518880": "黄金ETF（避险）",
    "sh512880": "券商ETF（金融救市）",
    "sz159605": "银行ETF（稳定器）",
}

# 合并全量清单（用于完整模式）
ALL_ETFS = {**LAYER1_BROAD, **LAYER2_STYLE, **LAYER3_OVERSEAS, **LAYER4_SECTOR}

# 默认快速篮子（日常运行，只算第一层）
DEFAULT_BASKET = list(LAYER1_BROAD.keys())

# ─── 向后兼容：旧版 STATE_FUND_ETFS 别名 ────────────────────────────
STATE_FUND_ETFS = ALL_ETFS

# ─── 国家队份额留存率基准线（2024Q3峰值 + 2025年末年报）───────────────
# 单位：亿份，来源：同花顺基金F10季报/年报 + stcn/中证网报道
PEAK_SHARES_2024Q3 = {
    "sh510300": 909.44,    # 华泰柏瑞沪深300ETF 2024-09-24 峰值
    "sh510050": 575.72,    # 华夏上证50ETF 2024-09-30
    "sh510500": 212.15,    # 南方中证500ETF 2024-09-30
    "sz159915": 180.0,     # 创业板ETF（估计）
    "sh588050": 100.0,     # 科创50ETF（估计）
    "sz159845": 50.0,      # 中证1000ETF（估计）
    "sz159852": 30.0,      # 中证2000ETF（估计）
}

YEAR_END_SHARES_2025 = {
    "sh510300": 888.30,    # 华泰柏瑞沪深300ETF 年报
    "sh510050": 566.65,    # 华夏上证50ETF 年报
    "sh510500": 190.65,    # 南方中证500ETF 年报
    "sz159915": 170.0,     # 创业板ETF（估计）
    "sh588050": 90.0,      # 科创50ETF（估计）
    "sz159845": 45.0,      # 中证1000ETF（估计）
    "sz159852": 25.0,      # 中证2000ETF（估计）
}

# 汇金系占比（2025年末年报）
HUIJIN_RATIO_2025 = {
    "sh510300": 0.8276,    # 82.76%
    "sh510050": 0.8605,    # 86.05%
    "sh510500": 0.70,      # ~70%（估计）
    "sz159915": 0.50,      # ~50%（估计）
    "sh588050": 0.60,      # ~60%（估计）
}

# 输出目录（优先读环境变量，fallback 到相对路径）
DATA_ROOT = Path(os.environ.get(
    "INVESTMENT_TEAM_DATA_DIR",
    Path(__file__).parent.parent.parent / "engine" / "data"
))
OUT_DIR = DATA_ROOT / "chips"


# ─── K 线拉取 ────────────────────────────────────────────────────────
def fetch_kline(ticker: str, limit: int = 250) -> list[dict]:
    """
    调用 westock-data CLI 拉取日线 K 线
    返回按时间正序排列的 list[{date, open, close, high, low, volume, turnover}]
    """
    try:
        result = subprocess.run(
            ["npx", "-y", "westock-data-clawhub@1.0.4", "kline",
             ticker, "--period", "day", "--limit", str(limit)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"  ⚠️ {ticker}: westock-data 调用失败 — {result.stderr[:200]}")
            return []

        # 解析 westock-data 输出（JSON 数组格式）
        lines = result.stdout.strip().split("\n")
        klines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # westock-data 字段映射
                klines.append({
                    "date":     obj.get("t", obj.get("date", "")),
                    "open":     float(obj.get("o", obj.get("open",  0))),
                    "high":     float(obj.get("h", obj.get("high",  0))),
                    "low":      float(obj.get("l", obj.get("low",   0))),
                    "close":    float(obj.get("c", obj.get("close", 0))),
                    "volume":   float(obj.get("v", obj.get("volume", 0))),
                    "turnover": float(obj.get("a", obj.get("turnover", 0))),
                })
            except (json.JSONDecodeError, ValueError):
                continue

        # 按日期正序
        klines.sort(key=lambda x: x["date"])
        return klines

    except subprocess.TimeoutExpired:
        print(f"  ⚠️ {ticker}: 超时（60s）")
        return []
    except Exception as e:
        print(f"  ⚠️ {ticker}: 异常 {e}")
        return []


# ─── 筹码分布模型 ────────────────────────────────────────────────────
def calc_chip_distribution(klines: list[dict],
                            price_bins: int = 200,
                            decay_factor: float = 0.92) -> tuple[list, list]:
    """
    基于换手率的筹码分布模型（等价于 TDX 筹码分布图的简化版本）

    思路：
    - 每根 K 线的成交量被视为在 [low, high] 均匀分布的新建仓筹码
    - 历史筹码每日按 decay_factor 衰减（模拟换手消耗）
    - 累计得到每个价格区间的筹码浓度

    Args:
        klines:       时间正序的 K 线列表
        price_bins:   价格分箱数（精度）
        decay_factor: 每日残留系数（0.92 ≈ 每月衰减约50%）

    Returns:
        prices:  各分箱的中心价格列表
        chips:   各分箱的筹码密度列表（已归一化到 sum=1）
    """
    if len(klines) < 5:
        return [], []

    # 确定价格范围
    all_prices = [k["close"] for k in klines if k["close"] > 0]
    if not all_prices:
        return [], []

    p_min = min(k["low"]  for k in klines if k["low"]  > 0) * 0.98
    p_max = max(k["high"] for k in klines if k["high"] > 0) * 1.02
    bin_size = (p_max - p_min) / price_bins

    prices = [p_min + (i + 0.5) * bin_size for i in range(price_bins)]
    chips  = [0.0] * price_bins

    total_volume = sum(k["volume"] for k in klines if k["volume"] > 0)
    if total_volume == 0:
        return prices, chips

    for k in klines:
        if k["volume"] <= 0 or k["high"] <= k["low"]:
            continue

        # 成交量权重（归一化）
        vol_weight = k["volume"] / total_volume

        # 该 bar 的成交均匀分布在 [low, high]
        bar_range = k["high"] - k["low"]
        for i, p in enumerate(prices):
            if k["low"] <= p <= k["high"]:
                chips[i] += vol_weight / (bar_range / bin_size)

        # 历史筹码衰减（模拟换手）
        chips = [c * decay_factor for c in chips]

    # 归一化
    total = sum(chips)
    if total > 0:
        chips = [c / total for c in chips]

    return prices, chips


# ─── 水位分析 ────────────────────────────────────────────────────────
def analyze_waterline(ticker: str, klines: list[dict], name: str = "") -> dict:
    """
    计算完整的筹码水位分析结果
    """
    if not klines:
        return {"ticker": ticker, "error": "无K线数据"}

    current_close = klines[-1]["close"]
    current_date  = klines[-1]["date"]

    print(f"  📊 {ticker} {name}: {len(klines)} 日 K 线，当前价 {current_close}")

    # 1. 筹码分布
    prices, chips = calc_chip_distribution(klines)
    if not prices:
        return {"ticker": ticker, "error": "筹码分布计算失败"}

    # 2. 当前价位于筹码分位
    below = sum(c for p, c in zip(prices, chips) if p < current_close)
    above = sum(c for p, c in zip(prices, chips) if p >= current_close)
    percentile = round(below / (below + above) * 100, 1) if (below + above) > 0 else 50.0

    # 3. 筹码水位状态
    if percentile <= 30:
        status = "底部区域 🟢"
        macro_signal = "当前价处于筹码分布底部30%内，国家队成本支撑强，配置性价比高"
    elif percentile <= 70:
        status = "中位区间 ⚪"
        macro_signal = "当前价处于筹码中位，上下阻力均衡，等待方向性突破"
    else:
        status = "顶部区域 🔴"
        macro_signal = "当前价处于筹码分布顶部，上方套牢盘压力重，谨慎追高"

    # 4. 最密集筹码峰（Top 3 bins）
    sorted_bins = sorted(zip(prices, chips), key=lambda x: -x[1])
    top_bins = sorted_bins[:10]
    if top_bins:
        peak_prices = [p for p, _ in top_bins]
        dense_peak_low  = round(min(peak_prices) * 0.98, 4)
        dense_peak_high = round(max(peak_prices) * 1.02, 4)
    else:
        dense_peak_low = dense_peak_high = current_close

    # 5. 成交量加权均价（VWAP，作为主力平均成本估算）
    total_vol = sum(k["volume"] for k in klines if k["volume"] > 0)
    vwap = (
        sum(k["close"] * k["volume"] for k in klines if k["volume"] > 0)
        / total_vol
        if total_vol > 0 else current_close
    )
    vwap = round(vwap, 4)

    # 6. 支撑/压力（筹码密集峰下沿=支撑，上方最近密集区=压力）
    support_level    = round(dense_peak_low, 4)
    # 找当前价以上第一个筹码密集区
    above_bins = [(p, c) for p, c in zip(prices, chips) if p > current_close]
    if above_bins:
        above_sorted = sorted(above_bins, key=lambda x: -x[1])
        resistance_level = round(above_sorted[0][0] * 1.01, 4)
    else:
        resistance_level = round(current_close * 1.05, 4)

    result = {
        "ticker": ticker,
        "name": name,
        "current_price": current_close,
        "analysis_date": current_date,
        "kline_days": len(klines),
        "chip_waterline": {
            "percentile": percentile,
            "status": status,
            "avg_cost_vwap": vwap,
            "dense_peak_low": dense_peak_low,
            "dense_peak_high": dense_peak_high,
            "support_level": support_level,
            "resistance_level": resistance_level,
            "chip_below_pct": round(below * 100, 1),
            "chip_above_pct": round(above * 100, 1),
        },
        "interpretation": (
            f"{name or ticker} 当前 {current_close}，筹码水位 {percentile}% 分位（{status}）；"
            f"估算主力VWAP成本 {vwap}；"
            f"筹码最密集区 {dense_peak_low}-{dense_peak_high}；"
            f"支撑 {support_level} / 压力 {resistance_level}。"
        ),
        "macro_signal": macro_signal,
    }

    return result


# ─── 主流程 ──────────────────────────────────────────────────────────
def main():
    # 解析命令行参数
    args = sys.argv[1:]

    if not args:
        # 无参数 → 运行默认快速篮子（第一层宽基）
        tickers = DEFAULT_BASKET
        print(f"🔧 未指定标的，运行默认快速篮子（第一层宽基 {len(tickers)} 只）")
        print(f"   如需完整模式：python3 etf_chip_analysis.py --all")
        print(f"   如需指定：python3 etf_chip_analysis.py sh510300 sz159915 sh513100\n")
    elif args == ["--all"]:
        tickers = list(ALL_ETFS.keys())
        print(f"🔧 完整模式：全部 {len(tickers)} 只 ETF")
    elif args == ["--layer1"]:
        tickers = list(LAYER1_BROAD.keys())
    elif args == ["--layer2"]:
        tickers = list(LAYER2_STYLE.keys())
    elif args == ["--overseas"]:
        tickers = list(LAYER3_OVERSEAS.keys())
    elif args == ["--sector"]:
        tickers = list(LAYER4_SECTOR.keys())
    else:
        tickers = args

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = OUT_DIR / f"chip_analysis_{today}.json"

    print(f"\n📊 筹码水位分析 — {today}")
    print(f"   标的: {tickers}")
    print(f"   输出: {out_path}\n")

    results = {}

    for ticker in tickers:
        name = STATE_FUND_ETFS.get(ticker, "")
        print(f"\n▶ {ticker} {name}")
        klines = fetch_kline(ticker, limit=250)
        if not klines:
            results[ticker] = {"ticker": ticker, "error": "无法获取K线数据"}
            continue
        results[ticker] = analyze_waterline(ticker, klines, name)

    # 生成摘要报告
    summary = {
        "analysis_date": today,
        "tickers_analyzed": len(results),
        "results": results,
        "summary_table": [],
    }

    print("\n\n" + "=" * 70)
    print("📊 国家队 ETF 筹码水位汇总")
    print("=" * 70)
    header = f"{'ETF代码':<12} {'名称':<20} {'当前价':>8} {'水位分位':>8} {'状态':>12} {'VWAP':>8} {'支撑':>8} {'压力':>8}"
    print(header)
    print("-" * 70)

    for ticker, r in results.items():
        if "error" in r:
            print(f"{ticker:<12} {'[错误]':<20} {r.get('error', '')}")
            continue
        wl = r["chip_waterline"]
        row = {
            "ticker": ticker,
            "name": r.get("name", ""),
            "current_price": r["current_price"],
            "percentile": wl["percentile"],
            "status": wl["status"],
            "vwap": wl["avg_cost_vwap"],
            "support": wl["support_level"],
            "resistance": wl["resistance_level"],
        }
        summary["summary_table"].append(row)
        print(
            f"{ticker:<12} {r.get('name','')[:18]:<20} "
            f"{r['current_price']:>8.3f} "
            f"{wl['percentile']:>7.1f}% "
            f"{wl['status']:>14} "
            f"{wl['avg_cost_vwap']:>8.3f} "
            f"{wl['support_level']:>8.3f} "
            f"{wl['resistance_level']:>8.3f}"
        )

    print("=" * 70)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n✅ 价格分布分析已写入: {out_path}")

    # ─── 份额留存率分析（国家队筹码水位真正定义）───────────────────────
    print("\n\n" + "=" * 70)
    print("📊 国家队 ETF 份额留存率（份额口径，非价格分位）")
    print("=" * 70)
    print(f"{'ETF':<12} {'名称':<20} {'当前份额':>10} {'2409峰值':>10} {'留存率':>8} "
          f"{'今日变动':>10} {'信号':<12}")
    print("-" * 85)

    # 用 westock-data etf 命令拉实时份额
    etf_codes = ",".join(t for t in tickers if t in PEAK_SHARES_2024Q3)
    if etf_codes:
        try:
            etf_result = subprocess.run(
                ["npx", "-y", "westock-data-clawhub@1.0.4", "etf", etf_codes],
                capture_output=True, text=True, timeout=60
            )
            etf_lines = [l.strip() for l in etf_result.stdout.split("\n")
                         if l.strip().startswith("|")]
            if len(etf_lines) >= 3:
                etf_headers = [h.strip() for h in etf_lines[0].split("|") if h.strip()]
                etf_idx = {h: i for i, h in enumerate(etf_headers)}

                retention_data = []
                for row_line in etf_lines[2:]:
                    vals = [v.strip() for v in row_line.split("|") if v.strip()]
                    if len(vals) <= max(etf_idx.values(), default=0):
                        continue
                    try:
                        code = vals[etf_idx["code"]]
                        name_etf = vals[etf_idx["name"]]
                        shares_cur = float(vals[etf_idx["shares"]]) / 1e8  # 转亿份
                        shares_chg = float(vals[etf_idx["sharesChg"]]) / 1e8
                    except (ValueError, KeyError):
                        continue

                    peak = PEAK_SHARES_2024Q3.get(code)
                    year_end = YEAR_END_SHARES_2025.get(code)
                    if not peak:
                        continue

                    ret_vs_peak = shares_cur / peak * 100
                    ret_vs_year = shares_cur / year_end * 100 if year_end else None

                    if ret_vs_peak > 80:
                        signal = "🟢 满仓护盘"
                    elif ret_vs_peak > 50:
                        signal = "🟡 开始退出"
                    elif ret_vs_peak > 30:
                        signal = "🟠 大幅退出"
                    else:
                        signal = "🔴 几乎清仓"

                    retention_data.append({
                        "code": code,
                        "name": name_etf,
                        "current_shares_yi": round(shares_cur, 2),
                        "peak_2409_yi": peak,
                        "year_end_2512_yi": year_end,
                        "retention_vs_2409_pct": round(ret_vs_peak, 1),
                        "retention_vs_2512_pct": round(ret_vs_year, 1) if ret_vs_year else None,
                        "daily_chg_yi": round(shares_chg, 2),
                        "signal": signal,
                    })

                    print(f"{code:<12} {name_etf[:18]:<20} "
                          f"{shares_cur:>8.1f}亿 {peak:>8.1f}亿 "
                          f"{ret_vs_peak:>6.1f}% "
                          f"{shares_chg:>+8.2f}亿 {signal}")

                # 汇总
                total_cur = sum(d["current_shares_yi"] for d in retention_data)
                total_peak = sum(d["peak_2409_yi"] for d in retention_data)
                overall_ret = total_cur / total_peak * 100 if total_peak else 0

                print("-" * 85)
                print(f"{'合计':<12} {'':<20} {total_cur:>8.1f}亿 {total_peak:>8.1f}亿 "
                      f"{overall_ret:>6.1f}%")
                print(f"\n📋 整体留存率: {overall_ret:.1f}%"
                      f" — 国家队ETF筹码已退出约{100-overall_ret:.0f}%")

                # 写入 summary
                summary["retention_analysis"] = {
                    "overall_retention_pct": round(overall_ret, 1),
                    "etfs": retention_data,
                }

                # 重新写入（覆盖）
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
                print(f"✅ 含份额留存率的完整报告已更新: {out_path}")

        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"⚠️ 份额留存率计算失败: {e}")

    return summary


if __name__ == "__main__":
    main()
