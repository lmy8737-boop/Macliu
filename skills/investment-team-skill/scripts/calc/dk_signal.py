# 适配形态: agent + bot
"""
v6.4.7 DK 波段信号（民间近似版 v1）

⚠️ 重要声明：
    东方财富证券客户端的官方 DK 波段信号是付费增值功能，算法属商业机密未公开，
    且公开 API（push2 / datacenter / emrnweb 三个域名）均无法直接拉取 DK 字段。
    本模块基于 3 因子合成一个【与官方 DK 设计哲学相近】的近似信号：
        1. 价格趋势：EMA12 与 EMA26 的金/死叉
        2. 主力资金：东财 push2 公开接口拉取最近 N 日主力净流入累计
        3. 超买超卖：KDJ 的 J 值
    投票机制：3 条中至少 2 条满足 → 触发 D（买）或 K（卖）

    与东财官方 DK 的差异：
    - 东财 DK 使用大数据 + 私有公式（含板块联动、龙虎榜、北向资金等更多维度）
    - 本模块仅用价量 + 主力资金 3 因子
    - 在 A 股大趋势行情中两者方向通常一致，震荡市可能分歧

用法（CLI）：
    .venv-czsc/bin/python scripts/cli/dk_check.py SH601208
    .venv-czsc/bin/python scripts/cli/dk_check.py SH601208 --lookback 60

用法（API）：
    from calc.dk_signal import compute_dk_signal
    df = compute_dk_signal(kline_df, fund_flow_df)
    last = df.iloc[-1]
    print(last['signal'], last['trend_days'], last['trend_pct'])
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

# ════════════════════════════════════════════════════════════════════
#  Step 1: 拉东财 push2 主力资金流向（公开接口，不需 akshare）
# ════════════════════════════════════════════════════════════════════

def _eastmoney_secid(symbol: str) -> str:
    """雪球 symbol → 东财 secid

    SH601208 → 1.601208
    SZ301305 → 0.301305
    HK01133 → 116.01133
    NVDA → 105.NVDA（美股纳斯达克）/ 106.NVDA（NYSE 兜底）
    """
    s = symbol.upper().strip()
    if s.startswith("SH"):
        return f"1.{s[2:]}"
    if s.startswith("SZ"):
        return f"0.{s[2:]}"
    if s.startswith("HK"):
        return f"116.{s[2:]}"
    if s.startswith("BJ"):
        return f"0.{s[2:]}"
    # 美股暂时不支持资金流向（东财此接口仅 A 股 + 港股）
    if s.isalpha():
        return f"105.{s}"
    # A 股纯数字
    if s.isdigit():
        if s.startswith(("6", "9", "5")):
            return f"1.{s}"
        return f"0.{s}"
    return f"1.{s}"


def fetch_fund_flow(symbol: str, lookback_days: int = 120) -> pd.DataFrame:
    """拉主力资金流向（日级）— 双源优先级

    主源：雪球 capital/history.json（v6.4.7 默认，沙盒/本地都通）
    备源：东财 push2 fflow/daykline（更细致字段，但部分网络环境被反爬）

    返回 DataFrame 含字段：date / main_net (元) / close (主源不含，已设 0)
    """
    # === 主源：雪球 ===
    try:
        df = _fetch_xueqiu_fund_flow(symbol, lookback_days)
        if not df.empty:
            return df
    except Exception:
        pass

    # === 备源：东财 ===
    try:
        return _fetch_eastmoney_fund_flow(symbol, lookback_days)
    except Exception:
        return pd.DataFrame()


def _fetch_xueqiu_fund_flow(symbol: str, lookback_days: int = 120) -> pd.DataFrame:
    """雪球 capital/history.json — 日级主力资金净流入

    返回字段：date / main_net (元)
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from data.kline_fetcher import _xueqiu_session

    s = _xueqiu_session()
    url = f"https://stock.xueqiu.com/v5/stock/capital/history.json?symbol={symbol}&size={lookback_days}"
    r = s.get(url, timeout=10)
    j = r.json()
    items = (j.get("data") or {}).get("items") or []
    rows = []
    for it in items:
        try:
            rows.append({
                "date":     pd.to_datetime(it["timestamp"], unit="ms"),
                "main_net": float(it["amount"]),
            })
        except (ValueError, KeyError):
            continue
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("date").reset_index(drop=True)


def _fetch_eastmoney_fund_flow(symbol: str, lookback_days: int = 120) -> pd.DataFrame:
    """东财 push2 主力资金流向（备源）

    接口：push2.eastmoney.com/api/qt/stock/fflow/daykline/get
    返回字段（fields2）：
        f51=date, f52=主力净, f53=小单, f54=中单, f55=大单, f56=超大单,
        f57=主力净占比, f58=小单占比, f59=中单占比, f60=大单占比,
        f61=超大单占比, f62=close, f63=涨跌幅
    """
    import requests

    secid = _eastmoney_secid(symbol)
    url = (
        "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
        f"?lmt={lookback_days}&klt=101&secid={secid}"
        f"&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63"
        f"&_={int(time.time()*1000)}"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
        "Accept": "*/*",
    }
    r = requests.get(url, headers=headers, timeout=10)
    j = r.json()
    klines = (j.get("data") or {}).get("klines") or []
    if not klines:
        return pd.DataFrame()

    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 13:
            continue
        try:
            rows.append({
                "date":       pd.to_datetime(parts[0]),
                "main_net":   float(parts[1]),
                "small":      float(parts[2]),
                "medium":     float(parts[3]),
                "large":      float(parts[4]),
                "xlarge":     float(parts[5]),
                "main_pct":   float(parts[6]),
                "close":      float(parts[11]),
                "pct_chg":    float(parts[12]),
            })
        except (ValueError, IndexError):
            continue
    df = pd.DataFrame(rows)
    return df.sort_values("date").reset_index(drop=True)


# ════════════════════════════════════════════════════════════════════
#  Step 2: 三个因子计算
# ════════════════════════════════════════════════════════════════════

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """计算 KDJ
    df 需含 high / low / close 列
    返回 K / D / J 三列
    """
    low_n  = df["low"].rolling(n, min_periods=1).min()
    high_n = df["high"].rolling(n, min_periods=1).max()
    rsv = (df["close"] - low_n) / (high_n - low_n + 1e-9) * 100
    k = rsv.ewm(alpha=1/m1, adjust=False).mean()
    d = k.ewm(alpha=1/m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return pd.DataFrame({"K": k, "D": d, "J": j})


def _macd_cross(close: pd.Series, fast: int = 12, slow: int = 26):
    """EMA 金/死叉
    返回与 close 等长的 Series:
       +1 = 当日金叉, -1 = 当日死叉, 0 = 无交叉
    """
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    diff = ema_fast - ema_slow
    sign = np.sign(diff)
    cross = sign.diff()
    out = pd.Series(0, index=close.index)
    out[cross > 0] = +1
    out[cross < 0] = -1
    return out, ema_fast, ema_slow


# ════════════════════════════════════════════════════════════════════
#  Step 3: DK 合成（投票机制）
# ════════════════════════════════════════════════════════════════════

@dataclass
class DKConfig:
    """民间近似 v1 默认参数"""
    ema_fast: int = 12
    ema_slow: int = 26
    kdj_n:    int = 9
    kdj_m1:   int = 3
    kdj_m2:   int = 3
    fund_window: int = 5    # 主力资金累计窗口（日）
    j_oversold:   int = 20  # KDJ J 超卖阈值
    j_overbought: int = 80  # 超买阈值
    vote_threshold: int = 2 # 3 票中至少几票才触发


def compute_dk_signal(
    kline: pd.DataFrame,
    fund_flow: Optional[pd.DataFrame] = None,
    cfg: Optional[DKConfig] = None,
) -> pd.DataFrame:
    """合成 DK 信号

    Args:
        kline: 日 K 线 DataFrame，需含 date(datetime) / open / high / low / close / volume
        fund_flow: 可选，东财 fetch_fund_flow() 返回的 DataFrame
                  含 date / main_net；若为 None 则跳过资金因子，只用 EMA + KDJ 2 票
        cfg: DKConfig 实例

    Returns:
        DataFrame，新增列：
          - ema_fast / ema_slow / kdj_J
          - vote_ema / vote_fund / vote_kdj （+1=买票 / -1=卖票 / 0=中立）
          - vote_total（净票数：+3=最强买 / -3=最强卖）
          - signal: 'D' (买) / 'K' (卖) / '-' (无)
          - trend_days: 当前 D/K 状态持续天数
          - trend_pct: 当前状态持续期间累计涨跌幅
    """
    cfg = cfg or DKConfig()
    df = kline.sort_values("date").reset_index(drop=True).copy()

    # —— 因子 1：EMA 金/死叉 ——
    cross, ef, es = _macd_cross(df["close"], cfg.ema_fast, cfg.ema_slow)
    df["ema_fast"] = ef
    df["ema_slow"] = es
    # vote_ema：金叉后维持 +1 直到下次死叉
    sign = np.where(ef > es, 1, -1)
    df["vote_ema"] = sign

    # —— 因子 2：主力资金（5 日累计）——
    if fund_flow is not None and not fund_flow.empty:
        ff = fund_flow[["date", "main_net"]].copy()
        df = df.merge(ff, on="date", how="left")
        df["main_net"] = df["main_net"].fillna(0)
        df["main_net_5d"] = df["main_net"].rolling(cfg.fund_window, min_periods=1).sum()
        df["vote_fund"] = np.where(df["main_net_5d"] > 0, 1, -1)
    else:
        df["main_net"] = 0
        df["main_net_5d"] = 0
        df["vote_fund"] = 0  # 无资金数据时该票弃权

    # —— 因子 3：KDJ J ——
    kdj = _kdj(df, cfg.kdj_n, cfg.kdj_m1, cfg.kdj_m2)
    df["kdj_J"] = kdj["J"]
    df["vote_kdj"] = 0
    df.loc[df["kdj_J"] < cfg.j_oversold, "vote_kdj"] = +1   # 超卖买
    df.loc[df["kdj_J"] > cfg.j_overbought, "vote_kdj"] = -1  # 超买卖

    # —— 投票合成 ——
    df["vote_total"] = df["vote_ema"] + df["vote_fund"] + df["vote_kdj"]

    # 信号（≥ vote_threshold 净票数）
    def _sig(v):
        if v >= cfg.vote_threshold:
            return "D"
        if v <= -cfg.vote_threshold:
            return "K"
        return "-"
    df["signal"] = df["vote_total"].apply(_sig)

    # —— 趋势天数 + 趋势涨幅 ——
    # 状态变化时重置计数
    state = df["signal"].replace("-", np.nan).ffill().fillna("-")
    df["state"] = state
    state_change = (state != state.shift()).astype(int)
    df["state_group"] = state_change.cumsum()

    df["trend_days"] = df.groupby("state_group").cumcount() + 1

    # 累计涨幅：当前状态起点 close 到当前 close
    def _cum_pct(g):
        if len(g) == 0:
            return pd.Series([], dtype=float)
        base = g["close"].iloc[0]
        return (g["close"] / base - 1) * 100

    df["trend_pct"] = df.groupby("state_group", group_keys=False).apply(_cum_pct).values

    return df


# ════════════════════════════════════════════════════════════════════
#  Step 4: 总结输出（CLI 调用）
# ════════════════════════════════════════════════════════════════════

def summarize(df: pd.DataFrame, last_n: int = 5) -> dict:
    """提取最近 N 个 D/K 信号点 + 当前状态总结"""
    last = df.iloc[-1]
    # 找最近 N 个状态切换
    sigs = df[df["signal"].isin(["D", "K"])].copy()

    # 提取每个 state_group 的第一个信号（即触发日）
    triggers = sigs.groupby("state_group").first().reset_index()
    triggers = triggers.sort_values("date").tail(last_n)

    return {
        "current": {
            "date":         last["date"].strftime("%Y-%m-%d"),
            "close":        round(float(last["close"]), 3),
            "state":        last["state"],
            "trend_days":   int(last["trend_days"]),
            "trend_pct":    round(float(last["trend_pct"]), 2),
            "vote_ema":     int(last["vote_ema"]),
            "vote_fund":    int(last["vote_fund"]),
            "vote_kdj":     int(last["vote_kdj"]),
            "vote_total":   int(last["vote_total"]),
            "kdj_J":        round(float(last["kdj_J"]), 1),
            "main_net_5d":  round(float(last.get("main_net_5d", 0)) / 1e8, 2),  # 转亿
        },
        "recent_triggers": [
            {
                "date":       r["date"].strftime("%Y-%m-%d"),
                "signal":     r["signal"],
                "close":      round(float(r["close"]), 3),
                "trend_days": int(r["trend_days"]),
                "trend_pct":  round(float(r["trend_pct"]), 2),
            }
            for _, r in triggers.iterrows()
        ],
    }
