# 适配形态: agent + bot
"""
v6.2 K 线拉取模块
- akshare 主源（通过 push2his 走东财历史接口）
- 雪球 fallback（akshare 反爬时自动接管）

老板纠偏 v6.0.2 → v6.2 剥离：原本嵌在 mattermost-bot/scripts/real_data_collector.py 里，
现在独立模块，agent 形态可以 import 此处直接用，不再依赖 bot 子目录。
"""
from __future__ import annotations

import sys
import time
from datetime import datetime

from .common import (
    DataCollectionError,
    call_with_retry,
    import_akshare,
    import_pandas,
)

# 模块级雪球 session 缓存，避免每次重新拿 cookie
_XUEQIU_SESSION = None


def _xueqiu_session():
    """惰性建立带 cookie 的雪球 session

    v6.2 修复（2026-06-01 下午）：雪球升级了风控——首页 `https://xueqiu.com` 不再写
    `xq_a_token` 等关键 cookie，必须访问 `/about/` 这类静态页才拿得到完整 token。
    没有 xq_a_token，v5/stock/chart/kline.json 会返回 error_code=400016
    "遇到错误，请刷新页面或者重新登录"。

    旧 v6.1 偶发能跑通是因为 session 里残留旧 cookie，新进程必失败。
    """
    global _XUEQIU_SESSION
    if _XUEQIU_SESSION is not None:
        return _XUEQIU_SESSION
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://xueqiu.com/",
        "Accept": "application/json, text/plain, */*",
    })
    # warmup：必须访问能拿到 xq_a_token 的页面（首页 / 仅写 acw_tc 不够）
    s.get("https://xueqiu.com/about/", timeout=8)
    if "xq_a_token" not in s.cookies:
        # 兜底：再试一次首页（少数 IP 仍会写）
        s.get("https://xueqiu.com", timeout=8)
    _XUEQIU_SESSION = s
    return s


def _xueqiu_symbol(code: str) -> str:
    """ticker → 雪球 symbol（v6.3 patch: 加美股 + 港股支持）

    - 全字母（美股 APH/NVDA/AAPL/AMZN）→ 直接返回（雪球用裸字母即识别美股）
    - 4-5 位纯数字（港股 0700 / 09988）→ HK 前缀
    - 6/9/5/11/13 开头 → 沪市 SH
    - 0/3 开头 → 深市 SZ
    - 1 开头多位 → 深市 SZ
    """
    if not code:
        return code
    base = code.split(".")[0]  # 兼容 APH.N / 0700.HK 后缀
    if base.isalpha():
        return base.upper()
    if base.isdigit() and len(base) in (4, 5):
        return f"HK{base.zfill(5)}"
    if base.startswith(("6", "9", "5", "11", "13", "20")):
        return f"SH{base}"
    if base.startswith(("0", "3")):
        return f"SZ{base}"
    if base.startswith("1"):
        return f"SZ{base}"
    return f"SH{base}"


def _xueqiu_kline_to_akshare_df(items, columns):
    """把雪球 K 线 JSON 映射到 akshare 中文列名 DataFrame"""
    pd = import_pandas()
    if not items:
        return pd.DataFrame()
    col_idx = {c: i for i, c in enumerate(columns)}
    rows = []
    for it in items:
        if it is None or it[col_idx.get("close", 5)] is None:
            continue
        ts = it[col_idx["timestamp"]] / 1000
        date_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        open_p = it[col_idx.get("open", 2)]
        high = it[col_idx.get("high", 3)]
        low = it[col_idx.get("low", 4)]
        close = it[col_idx.get("close", 5)]
        vol = it[col_idx.get("volume", 1)]
        amount = it[col_idx["amount"]] if "amount" in col_idx and it[col_idx["amount"]] is not None else (vol * close if vol and close else 0)
        chg = it[col_idx["chg"]] if "chg" in col_idx else 0
        percent = it[col_idx["percent"]] if "percent" in col_idx else 0
        turn = it[col_idx["turnoverrate"]] if "turnoverrate" in col_idx else 0
        rows.append({
            "日期": date_str,
            "开盘": open_p,
            "收盘": close,
            "最高": high,
            "最低": low,
            "成交量": vol,
            "成交额": amount,
            "振幅": ((high - low) / (close - chg) * 100) if (close - chg) else 0,
            "涨跌幅": percent,
            "涨跌额": chg,
            "换手率": turn or 0,
        })
    return pd.DataFrame(rows)


def xueqiu_hist(code: str, count: int = 500, period: str = "day"):
    """通过雪球公开 API 拉 K 线，返回 akshare 风格 DataFrame
    Args:
        code: A 股 / 港股 / 美股代码
        count: 倒数最近 N 根 K 线（默认 500）
        period: K 线周期 — "day" / "week" / "month"（v6.4.4 加）
    """
    if period not in ("day", "week", "month"):
        raise ValueError(f"period 只支持 day/week/month，got {period!r}")
    s = _xueqiu_session()
    symbol = _xueqiu_symbol(code)
    end_ms = int(time.time() * 1000)
    url = (
        f"https://stock.xueqiu.com/v5/stock/chart/kline.json"
        f"?symbol={symbol}&begin={end_ms}&period={period}&type=before&count=-{count}"
    )
    r = s.get(url, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"雪球 K 线 status={r.status_code}")
    j = r.json()
    if j.get("error_code") not in (0, "0", None):
        raise RuntimeError(f"雪球 error_code={j.get('error_code')} msg={j.get('error_description')}")
    data = j.get("data") or {}
    items = data.get("item") or []
    columns = data.get("column") or []
    return _xueqiu_kline_to_akshare_df(items, columns)


def hist_kline_with_fallback(code: str, ticker_type: str = "STOCK"):
    """v6.0.2 → v6.2 抽离版：akshare 优先 → 失败 fallback 雪球。
    上层缠论 / scanner / chip 都可调此函数，无需感知数据源差异。
    返回 akshare 风格 DataFrame（中文列名）。
    """
    ak = import_akshare()
    try:
        if ticker_type == "ETF":
            return call_with_retry(
                ak.fund_etf_hist_em,
                symbol=code, period="daily", adjust="qfq",
                max_retries=2,
            )
        else:
            return call_with_retry(
                ak.stock_zh_a_hist,
                symbol=code, period="daily", adjust="qfq",
                max_retries=2,
            )
    except Exception as ak_err:
        try:
            df = xueqiu_hist(code, count=500)
            if df is None or df.empty:
                raise RuntimeError("雪球返回空")
            print(f"  [fallback xueqiu] {code}: rows={len(df)}", file=sys.stderr)
            return df
        except Exception as xq_err:
            raise RuntimeError(
                f"akshare+xueqiu 双源失败 — akshare: {ak_err!r:.80}; xueqiu: {xq_err!r:.80}"
            )
