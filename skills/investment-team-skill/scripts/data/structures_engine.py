# 适配形态: agent + bot
"""
v6.2 缠论结构生成模块
- 调用 scripts/calc/chanlun.py 引擎（czsc 主 + legacy fallback）
- 把 K 线 DataFrame → structures dict
- 多 ticker 批量产 structures_<date>.json
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from .common import DataCollectionError
from .kline_fetcher import hist_kline_with_fallback


def collect_structures_for_tickers(today: str, tickers: list[dict]) -> dict:
    """
    跑缠论引擎生成 structures dict（多 ticker）。

    Args:
        today: ISO 日期字符串 'YYYY-MM-DD'
        tickers: [{"ticker": "601138", "name": "工业富联", "type": "STOCK"}, ...]

    Returns:
        {"<ticker>": {"name": ..., "levels": {"daily": {...}}}}
    """
    out: dict = {}

    czsc_available = False
    try:
        import czsc  # type: ignore # noqa: F401
        czsc_available = True
    except ImportError:
        print("  ⚠️  czsc 未安装，输出 minimal structures（无 fractal/bi/center 字段）", file=sys.stderr)

    for t in tickers:
        code = t["ticker"]
        try:
            ttype = t.get("type", "STOCK")
            df = hist_kline_with_fallback(code, ticker_type=ttype)
            if df is None or df.empty or len(df) < 50:
                continue

            close_col = "收盘" if "收盘" in df.columns else "close"
            high_col = "最高" if "最高" in df.columns else "high"
            low_col = "最低" if "最低" in df.columns else "low"

            last_price = float(df.iloc[-1][close_col])
            recent_high = float(df.iloc[-30:][high_col].max())
            recent_low = float(df.iloc[-30:][low_col].min())
            last_dir = "up" if df.iloc[-1][close_col] > df.iloc[-5][close_col] else "down"

            # v6.2: 如果 czsc 装了，尝试用 chanlun.analyze() 出完整结构
            daily_block: dict = {
                "engine": "czsc" if czsc_available else "minimal",
                "engine_version": _czsc_version() if czsc_available else "0.0",
                "level": "daily",
                "bars_count": len(df),
                "fractal_count": 0,
                "bi_count": 0,
                "center_count": 0,
                "current_structure": f"笔{last_dir}行中",
                "last_bi": {
                    "start_idx": len(df) - 30,
                    "end_idx": len(df) - 1,
                    "direction": last_dir,
                    "high": recent_high,
                    "low": recent_low,
                },
                "last_center": {
                    "zg": round(recent_high * 0.99, 2),
                    "zd": round(recent_low * 1.01, 2),
                    "bis": [],
                },
                "support": recent_low,
                "resistance": recent_high,
                "current_price": last_price,
                "divergence": {
                    "has_divergence": False,
                    "direction": "none",
                    "energy_ratio": 0,
                    "last_macd_area": 0,
                    "prev_macd_area": 0,
                },
            }

            if czsc_available:
                try:
                    chanlun_result = _run_chanlun_engine(df)
                    if chanlun_result:
                        daily_block.update(chanlun_result)
                except Exception as ce:
                    print(f"  ⚠️  {code} czsc 引擎异常，降级 minimal：{ce}", file=sys.stderr)

            out[code] = {
                "name": t.get("name", code),
                "levels": {"daily": daily_block},
            }
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️  {code} structures 失败：{e}", file=sys.stderr)

    if not out:
        raise DataCollectionError(
            source="kline_double_fallback",
            reason="所有 ticker 都没拿到 K 线（akshare + xueqiu 双源失败）",
        )

    return out


def _czsc_version() -> str:
    try:
        import czsc  # type: ignore
        return getattr(czsc, "__version__", "0.0.0")
    except ImportError:
        return "0.0"


def _run_chanlun_engine(df) -> dict | None:
    """把 K 线 DataFrame 喂给 scripts/calc/chanlun.py:analyze()。
    返回引擎输出的 fractal/bi/center/divergence 字段（仅在 czsc 可用时调用）。
    """
    SCRIPTS_DIR = Path(__file__).resolve().parents[1]
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from calc.chanlun import analyze  # type: ignore
    except ImportError:
        return None

    bars = []
    close_col = "收盘" if "收盘" in df.columns else "close"
    open_col = "开盘" if "开盘" in df.columns else "open"
    high_col = "最高" if "最高" in df.columns else "high"
    low_col = "最低" if "最低" in df.columns else "low"
    vol_col = "成交量" if "成交量" in df.columns else "volume"
    date_col = "日期" if "日期" in df.columns else "date"

    for _, row in df.iterrows():
        bars.append({
            "dt": str(row[date_col]),
            "open": float(row[open_col]),
            "high": float(row[high_col]),
            "low": float(row[low_col]),
            "close": float(row[close_col]),
            "volume": float(row[vol_col]) if vol_col in df.columns else 0,
        })

    if not bars:
        return None
    result = analyze(bars)
    if not isinstance(result, dict):
        return None
    return {
        "fractal_count": result.get("fractal_count", 0),
        "bi_count": result.get("bi_count", 0),
        "center_count": result.get("center_count", 0),
        "current_structure": result.get("current_structure", "未知"),
        "last_bi": result.get("last_bi") or {},
        "last_center": result.get("last_center") or {},
        "divergence": result.get("divergence") or {},
        "support": result.get("support"),
        "resistance": result.get("resistance"),
    }
