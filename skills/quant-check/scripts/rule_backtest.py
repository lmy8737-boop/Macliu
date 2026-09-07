#!/usr/bin/env python3
"""
简单情景回测：某条打分触发规则（如"分数升破阈值就买入/降到阈值以下就卖出"）
历史上跑出什么结果。用 vectorbt 做单资产、单规则的快速情景验证，
不做参数寻优、不做多资产组合优化——只回答"这条规则历史上灵不灵"。

用法：
  python3 rule_backtest.py --price price.csv --signal signal.csv \
      --asset 600519.SH --out result.json

price.csv：date,asset,close（日频）
signal.csv：date,asset,score（分数变化点，不需要每天都有，会做前向填充对齐到价格序列）

规则固定为：score 上穿 entry_threshold 买入，下穿 exit_threshold 卖出（可通过参数调整阈值）。
"""
import argparse
import json
import sys

import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser(description="vectorbt 简单情景回测：打分触发规则历史表现")
    ap.add_argument("--price", required=True, help="价格 CSV：date,asset,close")
    ap.add_argument("--signal", required=True, help="打分 CSV：date,asset,score")
    ap.add_argument("--asset", required=True, help="要回测的标的代码，需同时出现在 price 和 signal 中")
    ap.add_argument("--entry-threshold", type=float, default=None,
                     help="分数上穿此值买入；默认取 signal 序列的 60 分位")
    ap.add_argument("--exit-threshold", type=float, default=None,
                     help="分数下穿此值卖出；默认取 signal 序列的 40 分位")
    ap.add_argument("--fees", type=float, default=0.001, help="单边手续费，默认 0.1%")
    ap.add_argument("--out", default=None, help="结果输出为 JSON")
    args = ap.parse_args()

    try:
        import vectorbt as vbt
    except ImportError:
        print("ERROR: vectorbt 未安装。请先激活环境：source ~/.venvs/quant-check/bin/activate", file=sys.stderr)
        sys.exit(1)

    price_df = pd.read_csv(args.price, parse_dates=["date"])
    signal_df = pd.read_csv(args.signal, parse_dates=["date"])

    price = price_df[price_df["asset"] == args.asset].set_index("date")["close"].sort_index()
    signal = signal_df[signal_df["asset"] == args.asset].set_index("date")["score"].sort_index()

    if price.empty:
        print(f"ERROR: 价格数据中找不到标的 {args.asset}", file=sys.stderr)
        sys.exit(1)
    if signal.empty:
        print(f"ERROR: 打分数据中找不到标的 {args.asset}", file=sys.stderr)
        sys.exit(1)

    # 把稀疏的打分变化点前向填充对齐到价格序列的每个交易日
    score_aligned = signal.reindex(price.index, method="ffill")
    if score_aligned.isna().all():
        print("ERROR: 打分序列对齐后全为空值，检查日期范围是否与价格序列重叠", file=sys.stderr)
        sys.exit(1)

    entry_th = args.entry_threshold if args.entry_threshold is not None else score_aligned.quantile(0.6)
    exit_th = args.exit_threshold if args.exit_threshold is not None else score_aligned.quantile(0.4)

    entries = (score_aligned > entry_th) & (score_aligned.shift(1) <= entry_th)
    exits = (score_aligned < exit_th) & (score_aligned.shift(1) >= exit_th)

    pf = vbt.Portfolio.from_signals(
        price, entries.fillna(False), exits.fillna(False),
        fees=args.fees, freq="1D",
    )

    stats = pf.stats()

    # 基准：买入持有
    bh_pf = vbt.Portfolio.from_holding(price, freq="1D")
    bh_return = float(bh_pf.total_return())

    result = {
        "asset": args.asset,
        "entry_threshold": round(float(entry_th), 4),
        "exit_threshold": round(float(exit_th), 4),
        "n_trades": int(pf.trades.count()) if pf.trades.count() > 0 else 0,
        "total_return": round(float(pf.total_return()), 4),
        "buy_hold_return": round(bh_return, 4),
        "excess_vs_buy_hold": round(float(pf.total_return()) - bh_return, 4),
        "max_drawdown": round(float(pf.max_drawdown()), 4),
        "win_rate": round(float(pf.trades.win_rate()), 4) if pf.trades.count() > 0 else None,
        "sharpe_ratio": round(float(pf.sharpe_ratio()), 4) if not np.isnan(pf.sharpe_ratio()) else None,
    }

    if result["n_trades"] < 5:
        result["sample_warning"] = f"仅 {result['n_trades']} 笔交易，样本太少，结论不构成统计证据，只作方向参考"

    out_str = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out_str)
        print(f"结果已写入 {args.out}")
    print(out_str)


if __name__ == "__main__":
    main()
