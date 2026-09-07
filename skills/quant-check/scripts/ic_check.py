#!/usr/bin/env python3
"""
IC 检验：某个打分/因子历史上对未来收益有没有预测力。
用于校验总纲第八节"校准回路"和第八点五节"打分变更追溯"里的判断——
"表2/表3 分数升，历史上是否领先云厂股价"这类问题的量化版本。

设计说明：alphalens 的 IC 引擎是为"同一天内给一批资产分层排序、比较头尾组收益"
（截面选股）设计的；你的场景通常是单一标的/指数的时间序列打分（如"表2 risk_score
从 0.24 到 0.30"），不是截面排序问题，套 alphalens 会在分箱阶段丢光样本。
本脚本改用 Spearman 秩相关直接实现 IC 的原始定义（因子值与未来收益的秩相关系数），
对时间序列场景更直接，也不依赖 alphalens。多资产截面选股场景仍可用 alphalens。

用法：
  python3 ic_check.py --factor factor.csv --price price.csv \
      --periods 21 63 126 --out result.json

factor.csv 格式（长表）：
  date,asset,factor
  2023-03-31,600519.SH,0.45
  date = 打分变更生效日；asset = 标的代码（单一指数/ETF代理或多标的均可）；
  factor = 当期分数（如表2/表3的 risk_score 或综合分）

price.csv 格式（长表，日频收盘价）：
  date,asset,close

periods：向前看多少个交易日算收益，默认 21/63/126（约1/3/6个月）。
"""
import argparse
import json
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def compute_ic_for_period(factor_series: pd.Series, price: pd.Series, period: int) -> pd.Series:
    """对每个因子观测点，用其后 period 个交易日的收益，逐资产算一次 IC 不适用于单资产；
    单资产场景下返回的是"因子值 vs 未来收益"这条序列本身，IC 用其全样本 Spearman 相关表示。
    """
    price = price.sort_index()
    fwd_ret = price.pct_change(period).shift(-period)
    aligned = fwd_ret.reindex(factor_series.index, method=None)
    return aligned


def main():
    ap = argparse.ArgumentParser(description="Spearman IC 检验：打分是否领先未来收益（时间序列版）")
    ap.add_argument("--factor", required=True, help="因子/打分 CSV：date,asset,factor")
    ap.add_argument("--price", required=True, help="价格 CSV：date,asset,close")
    ap.add_argument("--periods", nargs="+", type=int, default=[21, 63, 126],
                     help="向前看的交易日数，默认 21 63 126（约1/3/6个月）")
    ap.add_argument("--out", default=None, help="结果输出为 JSON（默认打印到 stdout）")
    args = ap.parse_args()

    factor_df = pd.read_csv(args.factor, parse_dates=["date"])
    price_df = pd.read_csv(args.price, parse_dates=["date"])

    if factor_df.empty or price_df.empty:
        print("ERROR: 输入文件为空", file=sys.stderr)
        sys.exit(1)

    assets = sorted(set(factor_df["asset"]) & set(price_df["asset"]))
    if not assets:
        print("ERROR: factor 和 price 中的 asset 代码没有交集，检查代码格式是否一致", file=sys.stderr)
        sys.exit(1)

    result = {
        "assets_tested": assets,
        "periods_tested": args.periods,
        "per_asset": {},
        "pooled": {},
        "interpretation": [],
    }

    pooled_by_period = {p: {"factor": [], "fwd_return": []} for p in args.periods}

    for asset in assets:
        fac = factor_df[factor_df["asset"] == asset].set_index("date")["factor"].sort_index()
        px = price_df[price_df["asset"] == asset].set_index("date")["close"].sort_index()

        # 把打分日期对齐到价格序列最近的交易日（打分日期未必是交易日）
        px_reindexed = px.reindex(px.index.union(fac.index)).sort_index().ffill()

        asset_result = {}
        for period in args.periods:
            fwd_ret = px_reindexed.pct_change(period).shift(-period)
            fwd_at_factor_dates = fwd_ret.reindex(fac.index, method="nearest", tolerance=pd.Timedelta(10, unit="D"))

            pair = pd.DataFrame({"factor": fac, "fwd_return": fwd_at_factor_dates}).dropna()

            if len(pair) < 4:
                asset_result[str(period)] = {"n": len(pair), "ic": None, "note": "样本不足4个观测点，无法算相关系数"}
                continue

            ic, pval = spearmanr(pair["factor"], pair["fwd_return"])
            asset_result[str(period)] = {
                "n": int(len(pair)),
                "ic": round(float(ic), 4) if not np.isnan(ic) else None,
                "p_value": round(float(pval), 4) if not np.isnan(pval) else None,
            }
            pooled_by_period[period]["factor"].extend(pair["factor"].tolist())
            pooled_by_period[period]["fwd_return"].extend(pair["fwd_return"].tolist())

        result["per_asset"][asset] = asset_result

    # 多资产合并样本（把所有资产的因子-收益对拼在一起算一次整体IC，样本量小时有用）
    if len(assets) > 1:
        for period in args.periods:
            f = pooled_by_period[period]["factor"]
            r = pooled_by_period[period]["fwd_return"]
            if len(f) >= 4:
                ic, pval = spearmanr(f, r)
                result["pooled"][str(period)] = {
                    "n": len(f),
                    "ic": round(float(ic), 4) if not np.isnan(ic) else None,
                    "p_value": round(float(pval), 4) if not np.isnan(pval) else None,
                }

    # 判读（把每个 asset/period 的 IC 结果转成一句话）
    def verdict_line(scope, period, stats):
        if stats.get("ic") is None:
            return f"{scope} period={period}: {stats.get('note', '样本不足')}"
        ic = stats["ic"]
        n = stats["n"]
        pval = stats.get("p_value")
        if abs(ic) < 0.03:
            tier = "无显著预测力"
        elif abs(ic) < 0.08:
            tier = "弱信号，需更多样本确认"
        elif abs(ic) < 0.15:
            tier = "有一定预测力"
        else:
            tier = "预测力较强"
        direction = "正向（分数升→未来收益升）" if ic > 0 else "反向（分数升→未来收益降，需检查逻辑方向）"
        sig = ""
        if pval is not None:
            sig = "，统计显著(p<0.05)" if pval < 0.05 else "，统计不显著(p>=0.05)"
        return f"{scope} period={period}: IC={ic}, n={n}, {tier}, {direction}{sig}"

    for asset, periods_data in result["per_asset"].items():
        for period_str, stats in periods_data.items():
            result["interpretation"].append(verdict_line(asset, period_str, stats))
    for period_str, stats in result["pooled"].items():
        result["interpretation"].append(verdict_line("[合并全部标的]", period_str, stats))

    result["reading_notes"] = [
        "IC(Spearman秩相关) 取值范围 -1到1；|IC|<0.03视为无信号，>0.15视为较强信号，仅供参考非严格学术阈值。",
        "样本数n<12时结论仅作方向参考，不构成统计显著性证据——大多数季度更新的打分历史样本天然就少，这是本方法的固有局限，不是bug。",
        "p_value<0.05表示该相关性在此样本下统计显著，但小样本下p值本身也不稳定，仍需结合n和业务判断一起看。",
        "反向IC(分数升、收益反而降)不代表打分错了，可能是领先-滞后关系被算反、或该指标本质是反向指标（如拥挤度分数升=该跌）——先看指标定义再下结论。",
    ]

    out_str = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out_str)
        print(f"结果已写入 {args.out}")
    print(out_str)


if __name__ == "__main__":
    main()
