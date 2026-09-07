#!/usr/bin/env python3
"""dk_check.py — v6.4.7 DK 波段信号 CLI（民间近似版 v1）

⚠️ 重要：此为民间近似实现，非东方财富证券客户端官方 DK 信号。
   官方 DK 是付费增值功能，公开 API 无法获取（已实测 push2/datacenter/emrnweb 三域名均反爬）。
   本工具基于 EMA + 主力资金 + KDJ 三因子投票合成，方向通常一致但震荡市可能分歧。

用法（在 SKILL_HOME 目录下）：
    .venv-czsc/bin/python scripts/cli/dk_check.py SH601208
    .venv-czsc/bin/python scripts/cli/dk_check.py 601208 --lookback 120
    .venv-czsc/bin/python scripts/cli/dk_check.py 300059 -m   # 同时跑 czsc 共振
"""
from __future__ import annotations

import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

SKILL_HOME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_HOME / "scripts"))

from data.kline_fetcher import _xueqiu_session   # noqa: E402
from calc.dk_signal import (                      # noqa: E402
    fetch_fund_flow,
    compute_dk_signal,
    summarize,
    DKConfig,
)


def fetch_xueqiu_kline(symbol: str, count: int = 300):
    """雪球拉日 K 线 → DataFrame[date,open,high,low,close,volume]"""
    import pandas as pd
    s = _xueqiu_session()
    end_ms = int(time.time() * 1000)
    url = (
        f"https://stock.xueqiu.com/v5/stock/chart/kline.json"
        f"?symbol={symbol}&begin={end_ms}&period=day&type=before&count=-{count}"
    )
    j = s.get(url, timeout=10).json()
    items = (j.get("data") or {}).get("item") or []
    rows = []
    for it in items:
        if it[5] is None:
            continue
        rows.append({
            "date":   datetime.utcfromtimestamp(it[0] / 1000),
            "open":   float(it[2]),
            "high":   float(it[3]),
            "low":    float(it[4]),
            "close":  float(it[5]),
            "volume": float(it[1]) if it[1] else 0,
        })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(
        description="v6.4.7 DK 波段信号（民间近似版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("symbol", help="雪球 symbol（SH601208 / SZ301305 / 01133）— 美股暂不支持资金流")
    parser.add_argument("--lookback", type=int, default=120,
                        help="拉多少根日 K（默认 120）")
    parser.add_argument("-m", "--multi-level", action="store_true",
                        help="同时跑 czsc 多周期共振对照")
    parser.add_argument("--no-fund", action="store_true",
                        help="跳过资金流向（仅用 EMA+KDJ 2 票，海外标的可用）")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    if symbol.isdigit() and len(symbol) in (4, 5):
        symbol = symbol.zfill(5)

    print(f"📡 拉取日 K 线 {symbol} ({args.lookback} 根)...")
    df = fetch_xueqiu_kline(symbol, args.lookback)
    if df.empty:
        print(f"❌ 雪球返回空"); sys.exit(1)
    print(f"   ✓ {len(df)} 根（{df['date'].min().strftime('%Y-%m-%d')} → {df['date'].max().strftime('%Y-%m-%d')}）")

    fund_df = None
    if not args.no_fund:
        print(f"📡 拉取主力资金流向 {symbol}（东财 push2 公开接口）...")
        try:
            fund_df = fetch_fund_flow(symbol, lookback_days=args.lookback)
            if fund_df.empty:
                print(f"   ⚠️ 资金流为空（可能美股/不支持），将仅用 EMA+KDJ 2 票")
                fund_df = None
            else:
                print(f"   ✓ {len(fund_df)} 行")
        except Exception as e:
            print(f"   ⚠️ 资金流拉取失败 {e!r:.60}，将仅用 EMA+KDJ 2 票")

    print(f"📐 合成 DK 信号（民间近似 v1：EMA12/26 + 主力5日 + KDJ-J）...")
    t0 = time.time()
    out = compute_dk_signal(df, fund_df)
    print(f"   ✓ {(time.time()-t0)*1000:.0f} ms")
    print()

    s = summarize(out, last_n=5)
    cur = s["current"]

    print("═" * 72)
    print(f" {symbol} — DK 波段信号（民间近似 v1，非东财官方）")
    print("═" * 72)
    print(f"  日期:       {cur['date']}")
    print(f"  收盘价:     {cur['close']}")
    print()

    state_emoji = {"D": "🟢 D（买入信号）", "K": "🔴 K（卖出信号）", "-": "⚪ —（中性）"}
    print(f"  当前状态:   {state_emoji.get(cur['state'], cur['state'])}")
    print(f"  趋势天数:   {cur['trend_days']} 天")
    print(f"  趋势涨幅:   {cur['trend_pct']:+.2f}%")
    print()
    print(f"  ── 三因子投票（{cur['vote_total']:+d} 净票）──")
    vote_str = lambda v: "🟢 +1 (买)" if v == 1 else ("🔴 -1 (卖)" if v == -1 else "⚪ 0 (中)")
    print(f"    EMA12 vs 26:    {vote_str(cur['vote_ema'])}")
    print(f"    主力 5 日累计:  {vote_str(cur['vote_fund'])}  ({cur['main_net_5d']:+.2f} 亿)")
    print(f"    KDJ J ({cur['kdj_J']:.1f}):  {vote_str(cur['vote_kdj'])}")
    print()

    if s["recent_triggers"]:
        print(f"  ── 最近 5 个 D/K 触发点 ──")
        for t in s["recent_triggers"]:
            tag = "🟢" if t["signal"] == "D" else "🔴"
            print(f"    {tag} {t['date']}  {t['signal']}  @ {t['close']:>8.3f}  "
                  f"持续 {t['trend_days']:>3} 天  累计 {t['trend_pct']:+6.2f}%")
        print()

    print("═" * 72)
    print("  ⚠️ 民间近似版，非东财官方 DK 信号。")
    print("     官方 DK 含板块联动 / 龙虎榜 / 北向资金等更多维度，本版仅 3 因子。")
    print("═" * 72)

    # 多级别 czsc 对照（可选）
    if args.multi_level:
        print()
        print("📐 同时跑 czsc 多周期共振对照（v6.4.5）...")
        import subprocess
        cmd = [str(SKILL_HOME / ".venv-czsc/bin/python"),
               str(SKILL_HOME / "scripts/cli/czsc_check.py"),
               symbol, str(args.lookback), "-m"]
        subprocess.run(cmd, cwd=str(SKILL_HOME))


if __name__ == "__main__":
    main()
