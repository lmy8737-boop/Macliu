"""
finance_collector.py — v6.0 财务数据采集（akshare）

用途：抓取 ROE/营收/净利润/现金流/资产负债率等关键财务指标，
      为 beauty_score.py 提供"颜值"评分原料。

数据源：akshare（全免费）
  - stock_financial_abstract(symbol): 关键财务指标摘要
  - stock_financial_abstract_ths(symbol, indicator): 同花顺财报
  - stock_zh_a_hist(symbol): K 线（用于市值/股价）

CLI:
  python finance_collector.py 600519 000858 300750
  python finance_collector.py --tickers-file tickers.txt
  python finance_collector.py --watchlist  # 从 outputs/02_industry/02_Watchlist.md 提取

输出：engine/data/finance/finance_<date>.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from functools import lru_cache

try:
    import akshare as ak
    import pandas as pd
    import requests
except ImportError:
    print("⚠️  缺少 akshare/pandas/requests。请：pip install -r mattermost-bot/requirements.txt", file=sys.stderr)
    sys.exit(1)

SKILL_HOME = Path(os.environ.get(
    "INVESTMENT_TEAM_HOME",
    str(Path(__file__).resolve().parents[2])
))
DATA_DIR = Path(os.environ.get(
    "INVESTMENT_TEAM_DATA_DIR",
    SKILL_HOME / "engine" / "data"
))
OUTPUT_DIR = DATA_DIR / "finance"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
SEC_UA = "Mozilla/5.0 investment-research-workflow contact research@example.com"


def normalize_ticker(ticker: str) -> str:
    """把常见 ticker 规整为输出 key。

    A股保留 6 位数字；美股保留大写 ticker；港股保留 5 位数字。
    v6.6.3 修复：旧版会把 MSFT 规整成 msft 并继续走 A 股接口，
    最终拼出 shmsft，导致美股/港股财务全部空值。
    """
    t = ticker.strip().lower()
    if re.match(r"^[a-z]{1,6}(?:\.[on])?$", t):
        return t.split(".")[0].upper()
    if t.endswith(".hk") or t.startswith("hk"):
        return re.sub(r"\D", "", t).zfill(5)
    t = re.sub(r"^(sh|sz|hk|us)", "", t)
    t = re.sub(r"\..*$", "", t)
    return t


def classify_ticker(ticker: str) -> dict:
    raw = ticker.strip()
    upper = raw.upper()

    if re.match(r"^[A-Z]{1,6}(?:\.[ON])?$", upper):
        code = upper.split(".")[0]
        return {"market": "us", "code": code, "yahoo": code}

    if upper.endswith(".HK") or upper.startswith("HK"):
        num = re.sub(r"\D", "", upper).zfill(5)
        return {"market": "hk", "code": num, "yahoo": f"{int(num)}.HK"}

    num = re.sub(r"\D", "", raw)
    if num and len(num) <= 5:
        num = num.zfill(5)
        return {"market": "hk", "code": num, "yahoo": f"{int(num)}.HK"}

    return {"market": "cn", "code": num, "yahoo": f"{num}.{'SS' if num.startswith(('6', '9')) else 'SZ'}"}


def safe_float(value, default=0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _http_get_json(url: str, params: dict | None = None) -> dict:
    is_sec = "sec.gov" in url
    headers = {"User-Agent": SEC_UA if is_sec else UA}
    if is_sec:
        headers["Accept"] = "application/json"
    timeout = 30 if is_sec else 5
    attempts = 3 if is_sec else 1
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            r = requests.get(url, params=params or {}, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt < attempts - 1:
                time.sleep(1.2 * (attempt + 1))
    raise last_err  # type: ignore[misc]


@lru_cache(maxsize=1)
def _sec_ticker_map() -> dict:
    """SEC ticker -> CIK 映射。仅美股用；失败时返回空 dict，不影响 A股。"""
    try:
        data = _http_get_json("https://www.sec.gov/files/company_tickers.json")
        return {
            str(v.get("ticker", "")).upper(): str(v.get("cik_str", "")).zfill(10)
            for v in data.values()
            if v.get("ticker") and v.get("cik_str")
        }
    except Exception as e:
        print(f"  ⚠️  SEC ticker map 失败: {e}", file=sys.stderr)
        return {}


def _latest_fact(facts: dict, names: list[str], form_prefix: tuple[str, ...] = ("10-K", "20-F")) -> tuple[float | None, dict | None]:
    """从 SEC companyfacts 中取最新 fact。"""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    rows: list[dict] = []
    for name in names:
        item = us_gaap.get(name, {})
        for unit_rows in item.get("units", {}).values():
            for row in unit_rows:
                if row.get("form", "").startswith(form_prefix) and row.get("val") is not None:
                    rows.append(row)
    rows.sort(key=lambda x: (str(x.get("end", "")), str(x.get("filed", ""))), reverse=True)
    if not rows:
        return None, None
    return safe_float(rows[0].get("val"), None), rows[0]


def _annual_history(facts: dict, names: list[str], limit: int = 3) -> list[tuple[float, dict]]:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    rows: list[dict] = []
    for name in names:
        item = us_gaap.get(name, {})
        for unit_rows in item.get("units", {}).values():
            for row in unit_rows:
                if row.get("form", "").startswith(("10-K", "20-F")) and row.get("fp") == "FY" and row.get("val") is not None:
                    rows.append(row)
    rows.sort(key=lambda x: (str(x.get("end", "")), str(x.get("filed", ""))), reverse=True)
    out: list[tuple[float, dict]] = []
    seen_ends: set[str] = set()
    for row in rows:
        end = str(row.get("end", ""))
        if end in seen_ends:
            continue
        seen_ends.add(end)
        out.append((safe_float(row.get("val")), row))
        if len(out) >= limit:
            break
    return out


def fetch_global_equity(info: dict, raw_ticker: str) -> dict:
    """美股/港股轻量财务采集。

    美股：Yahoo chart 抓行情元数据，SEC companyfacts 抓年报级财务。
    港股：当前先抓 Yahoo chart 行情元数据，财务字段标注待补。
    """
    code = info["code"]
    out = {
        "ticker": code,
        "market": info["market"],
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data_route": "yahoo_chart+sec_companyfacts" if info["market"] == "us" else "yahoo_chart",
    }

    try:
        chart = _http_get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{info['yahoo']}",
            {"range": "5d", "interval": "1d"},
        )
        meta = chart.get("chart", {}).get("result", [{}])[0].get("meta", {})
        out["name"] = meta.get("shortName") or meta.get("longName") or raw_ticker
        out["currency"] = meta.get("currency", "")
        out["price"] = safe_float(meta.get("regularMarketPrice"))
        out["previous_close"] = safe_float(meta.get("chartPreviousClose"))
        out["exchange"] = meta.get("fullExchangeName") or meta.get("exchangeName", "")
    except Exception as e:
        print(f"  ⚠️  {code} yahoo_chart 失败: {e}", file=sys.stderr)

    if info["market"] != "us":
        out["financial_note"] = "港股财务分支待接入东财 GMAININDICATOR/Yahoo quoteSummary；本次仅返回行情元数据。"
        return out

    cik = _sec_ticker_map().get(code.upper())
    if not cik:
        out["financial_note"] = "SEC CIK 未匹配，无法抓 companyfacts。"
        return out

    try:
        facts = _http_get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        revenue_names = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]
        np_names = ["NetIncomeLoss", "ProfitLoss"]
        cfo_names = ["NetCashProvidedByUsedInOperatingActivities"]
        asset_names = ["Assets"]
        liability_names = ["Liabilities"]
        equity_names = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]

        rev_hist = _annual_history(facts, revenue_names, limit=3)
        np_hist = _annual_history(facts, np_names, limit=3)
        latest_rev = rev_hist[0][0] if rev_hist else 0
        prev_rev = rev_hist[1][0] if len(rev_hist) > 1 else 0
        latest_np = np_hist[0][0] if np_hist else 0
        prev_np = np_hist[1][0] if len(np_hist) > 1 else 0
        cfo, cfo_row = _latest_fact(facts, cfo_names)
        assets, _ = _latest_fact(facts, asset_names, form_prefix=("10-K", "10-Q"))
        liabilities, _ = _latest_fact(facts, liability_names, form_prefix=("10-K", "10-Q"))
        equity, _ = _latest_fact(facts, equity_names, form_prefix=("10-K", "10-Q"))

        out["cik"] = cik
        out["revenue_yi"] = round(latest_rev / 1e8, 2) if latest_rev else 0
        out["np_yi"] = round(latest_np / 1e8, 2) if latest_np else 0
        out["net_profit_history"] = [round(v / 1e8, 2) for v, _ in np_hist]
        out["rev_yoy_latest"] = round((latest_rev / prev_rev - 1) * 100, 2) if latest_rev and prev_rev else 0
        out["np_yoy_latest"] = round((latest_np / prev_np - 1) * 100, 2) if latest_np and prev_np else 0
        out["roe_ttm"] = round(latest_np / equity * 100, 2) if latest_np and equity else 0
        out["roe_3y_avg"] = out["roe_ttm"]
        out["net_margin"] = round(latest_np / latest_rev * 100, 2) if latest_np and latest_rev else 0
        out["gross_margin"] = 0
        if not liabilities and assets and equity:
            liabilities = assets - equity
        out["debt_ratio"] = round(liabilities / assets * 100, 2) if liabilities and assets else 0
        out["cfo_to_np"] = round(cfo / latest_np, 3) if cfo and latest_np else 0
        out["report_period_used"] = rev_hist[0][1].get("end", "") if rev_hist else ""
        out["latest_quarter"] = cfo_row.get("end", "") if cfo_row else ""
    except Exception as e:
        print(f"  ⚠️  {code} sec_companyfacts 失败: {e}", file=sys.stderr)

    return out


def fetch_one(ticker: str) -> dict:
    """单只股票财务指标采集

    返回 schema：见 references/beauty_scoring.md
    {
      "roe_3y_avg": float,
      "roe_ttm": float,
      "roic": float,
      "net_margin": float,
      "gross_margin": float,
      "rev_yoy": [近1年, 近2年, 近3年],
      "np_yoy": [近1年, 近2年, 近3年],
      "rev_qoq_latest": float,
      "debt_ratio": float,
      "cfo_to_np": float,
      "interest_bearing_debt_billion": float,
      "pe_ttm": float,
      "peg": float,
      "dividend_yield": float,
      "industry": str
    }
    """
    info = classify_ticker(ticker)
    code = info["code"]
    if info["market"] in {"us", "hk"}:
        return fetch_global_equity(info, ticker)

    out = {
        "ticker": code,
        "market": "cn",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data_route": "akshare_cn",
    }

    # 1. 关键财务指标摘要（含 ROE/净利率/资产负债率等）
    try:
        df = ak.stock_financial_abstract(symbol=code)
        if df is None or df.empty:
            raise ValueError("akshare returned empty")

        # v6.3 P0-1 fix: akshare 返回的 df 必须 drop "选项" 列，否则 cols[0] 取到的是
        # "常用指标" 字符串而不是日期，导致所有 safe_float 转 0.0（v6.0/v6.1/v6.2 通病）
        df = df.set_index("指标")
        if "选项" in df.columns:
            df = df.drop(columns=["选项"])
        cols = list(df.columns)
        if not cols:
            raise ValueError("no columns")

        # v6.3 P0-1 fix: 同名指标在 df.index 里出现多次（akshare 把"归母净利润"/"营业总收入"
        # /"销售净利率"等列了 2 次），df.loc[k] 返 DataFrame 而不是 Series。下面的辅助
        # 函数统一处理重复 index。
        def _get(key: str, col: str):
            if key not in df.index:
                return None
            sub = df.loc[key]
            try:
                import pandas as _pd
                if isinstance(sub, _pd.DataFrame):
                    sub = sub.iloc[0]
            except ImportError:
                pass
            try:
                return float(sub[col]) if sub[col] is not None else None
            except (ValueError, TypeError, KeyError):
                return None

        def _first_existing(keys: list[str]):
            """返回第一个真实存在于 df.index 的 key"""
            for k in keys:
                if k in df.index:
                    return k
            return None

        # v6.3 P0-1: 优先用最新年报（cols 中第一个 1231 结尾的列），避免 Q1 季度累计
        # ROE/净利率不年化的问题
        latest_year_col = next((c for c in cols if str(c).endswith("1231")), cols[0])
        latest_col = cols[0]  # 用于"最新一期"的 YoY 增长率（季度比同期更新鲜）

        # ROE TTM：用最新年报
        roe_key = _first_existing(["净资产收益率(ROE)", "加权净资产收益率", "净资产收益率"])
        out["roe_ttm"] = _get(roe_key, latest_year_col) or 0

        # ROE 3 年均值：取最近 3 个 12-31 年报
        annual_cols = [c for c in cols if str(c).endswith("1231")][:3]
        roe_vals = [v for v in (_get(roe_key, c) for c in annual_cols) if v is not None and v != 0]
        out["roe_3y_avg"] = round(sum(roe_vals) / len(roe_vals), 2) if roe_vals else 0

        # 净利率（年报）
        nm_key = _first_existing(["销售净利率", "净利率"])
        out["net_margin"] = _get(nm_key, latest_year_col) or 0

        # 毛利率
        gm_key = _first_existing(["毛利率", "销售毛利率"])
        out["gross_margin"] = _get(gm_key, latest_year_col) or 0

        # 资产负债率
        out["debt_ratio"] = _get("资产负债率", latest_year_col) or 0

        # 营收 YoY：用最新一期（季度更新鲜）
        rev_yoy_key = _first_existing([
            "营业总收入增长率", "营业总收入同比增长率",
            "营业收入同比增长率", "营业收入增长率",
        ])
        out["rev_yoy_latest"] = _get(rev_yoy_key, latest_col) or 0

        # 净利润 YoY：用最新一期
        np_yoy_key = _first_existing([
            "归属母公司净利润增长率", "净利润同比增长率",
            "归母净利润同比增长率", "归母净利润增长率",
        ])
        out["np_yoy_latest"] = _get(np_yoy_key, latest_col) or 0

        # 营收 YoY 历史（年报）
        out["rev_yoy_history"] = [
            v for v in (_get(rev_yoy_key, c) for c in annual_cols) if v is not None
        ]

        # CFO / 净利润（年报）
        cfo_key = _first_existing(["经营现金流量净额", "经营活动产生的现金流量净额"])
        np_val_key = _first_existing(["归母净利润", "净利润"])
        cfo = _get(cfo_key, latest_year_col) or 0
        np_val = _get(np_val_key, latest_year_col) or 0
        out["cfo_to_np"] = round(cfo / np_val, 3) if np_val and np_val > 0 else 0

        # 当年净利润绝对额（亿元）
        out["np_yi"] = round(np_val / 1e8, 2) if np_val else 0

        # 净利润 3 年历史
        out["net_profit_history"] = [
            round(v / 1e8, 2) for v in (_get(np_val_key, c) for c in annual_cols) if v is not None
        ]

        # 营收（亿元）
        rev_key = _first_existing(["营业总收入", "营业收入"])
        rev_val = _get(rev_key, latest_year_col) or 0
        out["revenue_yi"] = round(rev_val / 1e8, 2) if rev_val else 0

        # 报告期标记（用于报告里诚实标注数据时点）
        out["report_period_used"] = str(latest_year_col)
        out["latest_quarter"] = str(latest_col)

    except Exception as e:
        print(f"  ⚠️  {code} financial_abstract 失败: {e}", file=sys.stderr)
        # 不抛错，留空字段；硬过滤会把它过滤掉

    # 2. 实时 PE/PB/总市值/股息率（akshare 实时快照）
    try:
        spot = ak.stock_individual_info_em(symbol=code)
        if spot is not None and not spot.empty:
            info = dict(zip(spot["item"], spot["value"]))
            out["industry"] = info.get("行业", "")
            out["total_mv_billion"] = safe_float(info.get("总市值")) / 1e8 if info.get("总市值") else 0
    except Exception as e:
        pass

    try:
        # 个股估值（PE/PB）
        df_val = ak.stock_a_indicator_lg(symbol=code)
        if df_val is not None and not df_val.empty:
            latest = df_val.iloc[-1]
            out["pe_ttm"] = safe_float(latest.get("pe_ttm"))
            out["pb"] = safe_float(latest.get("pb"))
            out["dividend_yield"] = safe_float(latest.get("dv_ratio"))
    except Exception as e:
        pass

    # 3. PEG（用 PE / 净利润 YoY）
    if out.get("pe_ttm") and out.get("np_yoy_latest") and out["np_yoy_latest"] > 0:
        out["peg"] = round(out["pe_ttm"] / out["np_yoy_latest"], 2)
    else:
        out["peg"] = 0

    return out


def collect_finance(tickers: list[str], today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    print(f"🌱 v6.6.3 finance_collector | date={today} | tickers={len(tickers)}")
    print(f"   skill_home={SKILL_HOME}")

    result = {
        "date": today,
        "generated_by": "finance_collector.py [REAL DATA via akshare]",
        "tickers": {},
    }

    for i, t in enumerate(tickers, 1):
        try:
            data = fetch_one(t)
            result["tickers"][normalize_ticker(t)] = data
            print(f"  [{i}/{len(tickers)}] ✓ {t} route={data.get('data_route', '')} ROE={data.get('roe_ttm', 0):.1f}% 营收YoY={data.get('rev_yoy_latest', 0):.1f}%")
        except Exception as e:
            print(f"  [{i}/{len(tickers)}] ✗ {t} 失败: {e}", file=sys.stderr)
        # akshare 反爬要节流
        time.sleep(0.5)

    return result


def write_output(data: dict, today: str):
    out_path = OUTPUT_DIR / f"finance_{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 已写入 {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="v6.0 财务数据采集（akshare）")
    parser.add_argument("tickers", nargs="*", help="股票代码列表")
    parser.add_argument("--tickers-file", help="从文件读 ticker，每行一个")
    parser.add_argument("--watchlist", action="store_true",
                        help="从 outputs/02_industry/02_Watchlist.md 自动提取")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    tickers = list(args.tickers)

    if args.tickers_file:
        with open(args.tickers_file) as f:
            tickers.extend(line.strip() for line in f if line.strip())

    if args.watchlist:
        wl_path = SKILL_HOME / "outputs" / "02_industry" / "02_Watchlist.md"
        if wl_path.exists():
            content = wl_path.read_text(encoding="utf-8")
            # 简单提取 6 位数字代码
            for m in re.finditer(r"\b(\d{6})\b", content):
                tickers.append(m.group(1))
            tickers = list(dict.fromkeys(tickers))  # 去重保序
            print(f"📋 从 watchlist 提取到 {len(tickers)} 个 ticker")

    if not tickers:
        print("❌ 至少要提供 1 个 ticker", file=sys.stderr)
        sys.exit(1)

    data = collect_finance(tickers, today=args.date)
    write_output(data, args.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
