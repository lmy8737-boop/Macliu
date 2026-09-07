"""
3号数据员调用：拉取多级别K线 → 缠论计算 → 输出结构化JSON
4号交易员只需读取这个JSON做逻辑推演

v4.4 升级：
  - 引擎自动选择 czsc（主）或 legacy（fallback）
  - 新增 --multi-level 参数支持多级别联立分析（需要 czsc）
  - 新增 --finrl 参数在输出中附加 RL 评估（需要 finrl）

输出目录：环境变量 INVESTMENT_TEAM_DATA_DIR（默认 ./engine/data/structures/）
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from chanlun import analyze

DATA_ROOT = Path(os.environ.get(
    "INVESTMENT_TEAM_DATA_DIR",
    Path.cwd() / "engine" / "data"
))
OUT_DIR = DATA_ROOT / "structures"


def fetch_kline(ticker, period="day", limit=120):
    """用 westock-data 拉K线，转成 chanlun.py 需要的格式"""
    result = subprocess.run(
        ["npx", "-y", "westock-data-clawhub@1.0.4",
         "kline", ticker, "--period", period, "--limit", str(limit)],
        capture_output=True, text=True, timeout=90
    )
    
    bars = []
    lines = result.stdout.strip().split("\n")
    for line in lines[2:]:  # 跳过表头
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if len(cols) >= 6:
            try:
                bars.append({
                    "dt": cols[0],
                    "open": float(cols[1]),
                    "close": float(cols[2]),
                    "high": float(cols[3]),
                    "low": float(cols[4]),
                    "volume": float(cols[5]),
                })
            except ValueError:
                continue
    
    # 反转：westock 默认新→老，缠论需要老→新
    bars.reverse()
    return bars


def analyze_ticker(ticker, levels=None):
    """对单只标的多级别分析"""
    levels = levels or [("day", 120, "daily"), ("30", 200, "30min")]
    
    results = {
        "ticker": ticker,
        "analysis_at": datetime.now().isoformat(),
        "levels": {}
    }
    
    for period, limit, label in levels:
        print(f"  📊 拉取 {ticker} {label} K线...")
        bars = fetch_kline(ticker, period, limit)
        if len(bars) < 30:
            results["levels"][label] = {"error": f"数据不足({len(bars)}日)"}
            continue
        results["levels"][label] = analyze(bars, level=label)
    
    return results


def batch_analyze(tickers, levels=None):
    """批量分析"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    out_file = OUT_DIR / f"structures_{today}.json"
    
    all_results = {"date": today, "tickers": {}}
    
    for t in tickers:
        print(f"\n🔍 分析 {t}")
        try:
            all_results["tickers"][t] = analyze_ticker(t, levels)
        except Exception as e:
            all_results["tickers"][t] = {"error": str(e)}
            print(f"   ❌ 失败: {e}")
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 结构化输出: {out_file}")
    return all_results


if __name__ == "__main__":
    # 解析参数
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    multi_level = "--multi-level" in flags
    use_finrl = "--finrl" in flags

    if not args:
        tickers = ["usVOO", "usQQQ", "usSPY"]
        print("⚠️ 未指定 ticker，使用默认示例标的；实际使用请传参，如：")
        print("   python3 structure_pipeline.py sh510300 hk03033 usNVDA.OQ")
        print("   python3 structure_pipeline.py sh510300 --multi-level")
        print("   python3 structure_pipeline.py sh510300 --finrl")
    else:
        tickers = args

    # 选择级别
    if multi_level:
        levels = [("day", 120, "daily"), ("30", 200, "30min"), ("5", 500, "5min")]
        print("📊 多级别联立模式：daily + 30min + 5min")
    else:
        levels = [("day", 120, "daily")]

    results = batch_analyze(tickers, levels=levels)

    # 可选：FinRL 增强评估
    if use_finrl:
        try:
            from finrl_augment import augment_signal
            print("\n\n" + "=" * 60)
            print("🤖 FinRL 信号增强评估")
            print("=" * 60)
            for t, r in results["tickers"].items():
                if "error" in r:
                    continue
                daily = r.get("levels", {}).get("daily", {})
                if "error" in daily:
                    continue
                rl_result = augment_signal(
                    ticker=t, signal_strength=3, direction="LONG", features=daily
                )
                print(f"\n{t}: {rl_result['action']} — {rl_result['reason']}")
        except ImportError:
            print("\n⚠️ FinRL 未安装，跳过信号增强。安装: pip install finrl stable-baselines3 gymnasium")

    # 简要打印
    print("\n" + "=" * 60)
    print("📋 结构化分析摘要（4号读这份JSON即可）")
    print("=" * 60)
    for t, r in results["tickers"].items():
        if "error" in r:
            print(f"❌ {t}: {r['error']}")
            continue
        d = r["levels"].get("daily", {})
        engine = d.get("engine", "legacy")
        print(f"\n{t} [engine={engine}]")
        print(f"  结构: {d.get('current_structure')}")
        print(f"  笔数: {d.get('bi_count')} / 中枢数: {d.get('center_count')}")
        print(f"  支撑: {d.get('support')} / 阻力: {d.get('resistance')}")
        div = d.get("divergence", {})
        if div.get("has_divergence"):
            print(f"  ⚠️ 背驰: {div.get('direction')} 方向，能量比 {div.get('energy_ratio')}")
