"""
缠论结构计算引擎 - v4.4 czsc 专业版 + legacy fallback
====================================================
v4.4 升级：
  - 主引擎切换为 czsc 开源缠论库（Rust 加速，220+ 信号）
  - 保持 analyze() 入口函数签名和输出 schema 100% 不变
  - 4号交易员无感切换，读取 structures.json 格式完全兼容
  - 如果 czsc 未安装，自动 fallback 到旧版自研逻辑

安装 czsc：
  pip install czsc -U

输出：结构化 JSON，4号交易员只做逻辑推演，不做读图判断。
"""
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional

# ─── czsc 可用性检测 ────────────────────────────────────────────────────
try:
    from czsc import CZSC, RawBar, Freq
    USE_CZSC = True
except ImportError:
    USE_CZSC = False
    print("⚠️ czsc 未安装，使用 legacy 自研缠论引擎。建议：pip install czsc -U")


# ═══════════════════════════════════════════════════════════════════════
#  公共数据结构（两个引擎共享输出格式）
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Bar:
    """K线（含时间戳）"""
    dt: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


@dataclass
class FX:
    """分型"""
    idx: int
    dt: str
    type: str           # "TOP" or "BOTTOM"
    high: float
    low: float


@dataclass
class Bi:
    """笔"""
    start_idx: int
    end_idx: int
    start_dt: str
    end_dt: str
    direction: str      # "UP" or "DOWN"
    high: float
    low: float
    bars_count: int


@dataclass
class Center:
    """中枢"""
    bis: list
    zg: float           # 中枢上沿
    zd: float           # 中枢下沿
    high: float
    low: float
    start_dt: str
    end_dt: str


# ═══════════════════════════════════════════════════════════════════════
#  主入口（统一 API）
# ═══════════════════════════════════════════════════════════════════════

def analyze(bars_raw: List[dict], level: str = "daily") -> dict:
    """
    主分析函数 - 输入原始K线，输出完整缠论结构 JSON

    Args:
        bars_raw: K线列表 [{dt, open, high, low, close, volume}, ...]
        level: 级别标签 "daily" / "30min" / "5min" 等

    Returns:
        结构化 dict，与 structures.json schema 完全一致
    """
    if USE_CZSC:
        return _analyze_czsc(bars_raw, level)
    else:
        return _analyze_legacy(bars_raw, level)


# ═══════════════════════════════════════════════════════════════════════
#  czsc 专业引擎实现
# ═══════════════════════════════════════════════════════════════════════

# czsc Freq 映射
LEVEL_TO_FREQ = {
    "1min":  Freq.F1 if USE_CZSC else None,
    "5min":  Freq.F5 if USE_CZSC else None,
    "15min": Freq.F15 if USE_CZSC else None,
    "30min": Freq.F30 if USE_CZSC else None,
    "60min": Freq.F60 if USE_CZSC else None,
    "daily": Freq.D if USE_CZSC else None,
    "weekly": Freq.W if USE_CZSC else None,
}


def _analyze_czsc(bars_raw: List[dict], level: str = "daily") -> dict:
    """
    使用 czsc 库进行缠论分析，输出与旧版完全一致的 JSON 格式
    """
    if len(bars_raw) < 30:
        return {"error": "数据不足", "min_required": 30, "actual": len(bars_raw)}

    # 转换为 czsc RawBar 格式
    freq = LEVEL_TO_FREQ.get(level, Freq.D)
    raw_bars = []
    for i, b in enumerate(bars_raw):
        dt_str = b.get("dt", b.get("date", ""))
        # czsc 需要 datetime 对象
        try:
            if len(dt_str) == 10:  # YYYY-MM-DD
                dt = datetime.strptime(dt_str, "%Y-%m-%d")
            elif len(dt_str) == 19:  # YYYY-MM-DD HH:MM:SS
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            else:
                dt = datetime.strptime(dt_str[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            dt = datetime(2020, 1, 1, 0, i)  # fallback

        raw_bars.append(RawBar(
            symbol="ANALYSIS",
            id=i,
            dt=dt,
            freq=freq,
            open=float(b.get("open", 0)),
            close=float(b.get("close", 0)),
            high=float(b.get("high", 0)),
            low=float(b.get("low", 0)),
            vol=float(b.get("volume", b.get("vol", 0))),
            amount=float(b.get("amount", b.get("turnover", 0))),
        ))

    # 运行 czsc 分析
    c = CZSC(raw_bars)

    # ── 提取笔 ──
    bis = []
    for i, bi in enumerate(c.bi_list):
        bis.append({
            "start_idx": bi.raw_bars[0].id if bi.raw_bars else i * 5,
            "end_idx": bi.raw_bars[-1].id if bi.raw_bars else i * 5 + 5,
            "start_dt": bi.raw_bars[0].dt.strftime("%Y-%m-%d") if bi.raw_bars else "",
            "end_dt": bi.raw_bars[-1].dt.strftime("%Y-%m-%d") if bi.raw_bars else "",
            "direction": "UP" if bi.direction.value == "向上" else "DOWN",
            "high": bi.high,
            "low": bi.low,
            "bars_count": len(bi.raw_bars) if bi.raw_bars else 0,
        })

    # ── 提取中枢（czsc 的 zs_list）──
    centers = []
    for zs in getattr(c, 'zs_list', []):
        centers.append({
            "bis": list(range(len(bis)))[-3:],  # 简化
            "zg": zs.zg,
            "zd": zs.zd,
            "high": zs.gg,
            "low": zs.dd,
            "start_dt": zs.raw_bars[0].dt.strftime("%Y-%m-%d") if hasattr(zs, 'raw_bars') and zs.raw_bars else "",
            "end_dt": zs.raw_bars[-1].dt.strftime("%Y-%m-%d") if hasattr(zs, 'raw_bars') and zs.raw_bars else "",
        })

    # ── 背驰判定（基于最后两笔同向比较）──
    divergence = _detect_divergence_czsc(c)

    # ── 当前结构定位 ──
    last_bi = bis[-1] if bis else None
    last_center = centers[-1] if centers else None

    if last_bi:
        if last_bi["direction"] == "UP":
            structure = "向上笔延伸中"
        else:
            structure = "向下笔延伸中"
    else:
        structure = "结构待形成"

    return {
        "engine": "czsc",
        "engine_version": _get_czsc_version(),
        "level": level,
        "bars_count": len(bars_raw),
        "processed_bars": len(c.bars_raw),
        "fractal_count": len(c.fx_list),
        "bi_count": len(c.bi_list),
        "center_count": len(centers),
        "current_structure": structure,
        "last_bi": last_bi,
        "last_center": last_center,
        "divergence": divergence,
        "support": last_center["zd"] if last_center else None,
        "resistance": last_center["zg"] if last_center else None,
        "all_centers": centers[-3:],
    }


def _detect_divergence_czsc(c) -> dict:
    """从 czsc 对象中提取背驰信息"""
    bi_list = c.bi_list
    if len(bi_list) < 2:
        return {"has_divergence": False, "reason": "笔数不足"}

    last_bi = bi_list[-1]

    # 找上一段同向笔
    prev_same = None
    for bi in reversed(bi_list[:-1]):
        if bi.direction == last_bi.direction:
            prev_same = bi
            break

    if prev_same is None:
        return {"has_divergence": False, "reason": "无同向参照笔"}

    # 使用 czsc 内置的力度对比（macd_area 属性，如果可用）
    last_power = getattr(last_bi, 'power', None) or getattr(last_bi, 'macd_area', 0)
    prev_power = getattr(prev_same, 'power', None) or getattr(prev_same, 'macd_area', 0)

    # 如果 czsc 版本不提供 power/macd_area，手动计算
    if last_power == 0 and prev_power == 0:
        last_power = abs(last_bi.high - last_bi.low)
        prev_power = abs(prev_same.high - prev_same.low)

    has_div = False
    direction = "UP" if last_bi.direction.value == "向上" else "DOWN"

    if direction == "UP":
        if last_bi.high > prev_same.high and last_power < prev_power:
            has_div = True
    else:
        if last_bi.low < prev_same.low and last_power < prev_power:
            has_div = True

    energy_ratio = round(last_power / prev_power, 2) if prev_power > 0 else None

    return {
        "has_divergence": has_div,
        "direction": direction,
        "last_macd_area": round(last_power, 2),
        "prev_macd_area": round(prev_power, 2),
        "energy_ratio": energy_ratio,
    }


def _get_czsc_version() -> str:
    """获取 czsc 版本号"""
    try:
        import czsc
        return getattr(czsc, '__version__', 'unknown')
    except Exception:
        return "unknown"


# ═══════════════════════════════════════════════════════════════════════
#  多级别联立分析（czsc BarGenerator 能力）
# ═══════════════════════════════════════════════════════════════════════

def analyze_multi_level(bars_raw_1min: List[dict], levels: List[str] = None) -> dict:
    """
    🆕 czsc 独有能力：从 1 分钟 K 线自动合成多级别并联立分析

    Args:
        bars_raw_1min: 1分钟 K 线列表
        levels: 需要分析的级别列表，默认 ["5min", "30min", "daily"]

    Returns:
        各级别的缠论结构（嵌套 dict）
    """
    if not USE_CZSC:
        return {"error": "多级别联立分析需要 czsc 库，请安装: pip install czsc -U"}

    from czsc import BarGenerator

    levels = levels or ["5min", "30min", "daily"]
    freq_map = {"5min": Freq.F5, "30min": Freq.F30, "60min": Freq.F60, "daily": Freq.D}

    # 创建 BarGenerator
    target_freqs = [freq_map[l] for l in levels if l in freq_map]
    bg = BarGenerator(base_freq=Freq.F1, freqs=target_freqs)

    # 逐根输入 1min K线
    for b in bars_raw_1min:
        dt_str = b.get("dt", b.get("date", ""))
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue

        bar = RawBar(
            symbol="ANALYSIS", id=0, dt=dt, freq=Freq.F1,
            open=float(b.get("open", 0)), close=float(b.get("close", 0)),
            high=float(b.get("high", 0)), low=float(b.get("low", 0)),
            vol=float(b.get("volume", 0)), amount=float(b.get("amount", 0)),
        )
        bg.update(bar)

    # 提取各级别分析结果
    results = {"multi_level": True, "levels": {}}
    for level_name, freq in zip(levels, target_freqs):
        bars_at_level = bg.bars.get(freq, [])
        if len(bars_at_level) >= 30:
            # 转回 dict 列表，用 analyze() 统一处理
            bars_dict = [{
                "dt": b.dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": b.open, "close": b.close,
                "high": b.high, "low": b.low,
                "volume": b.vol,
            } for b in bars_at_level]
            results["levels"][level_name] = analyze(bars_dict, level=level_name)
        else:
            results["levels"][level_name] = {"error": f"数据不足({len(bars_at_level)}根)"}

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Legacy 自研引擎（fallback，保留完整实现）
# ═══════════════════════════════════════════════════════════════════════

# ---------- 1. 包含关系处理 ----------
def _process_inclusion(bars: List[Bar]) -> List[Bar]:
    if len(bars) < 2:
        return bars[:]
    processed = [bars[0]]
    for i in range(1, len(bars)):
        prev = processed[-1]
        cur = bars[i]
        prev_contains_cur = prev.high >= cur.high and prev.low <= cur.low
        cur_contains_prev = cur.high >= prev.high and cur.low <= prev.low
        if not (prev_contains_cur or cur_contains_prev):
            processed.append(cur)
            continue
        if len(processed) >= 2:
            ref = processed[-2]
            direction_up = prev.high > ref.high
        else:
            direction_up = cur.close > prev.close
        if direction_up:
            merged = Bar(dt=cur.dt, open=prev.open, high=max(prev.high, cur.high),
                         low=max(prev.low, cur.low), close=cur.close,
                         volume=prev.volume + cur.volume)
        else:
            merged = Bar(dt=cur.dt, open=prev.open, high=min(prev.high, cur.high),
                         low=min(prev.low, cur.low), close=cur.close,
                         volume=prev.volume + cur.volume)
        processed[-1] = merged
    return processed


# ---------- 2. 分型识别 ----------
def _find_fx(bars: List[Bar]) -> List[FX]:
    fxs = []
    for i in range(1, len(bars) - 1):
        L, M, R = bars[i - 1], bars[i], bars[i + 1]
        if M.high > L.high and M.high > R.high and M.low > L.low and M.low > R.low:
            fxs.append(FX(idx=i, dt=M.dt, type="TOP", high=M.high, low=M.low))
        elif M.low < L.low and M.low < R.low and M.high < L.high and M.high < R.high:
            fxs.append(FX(idx=i, dt=M.dt, type="BOTTOM", high=M.high, low=M.low))
    return fxs


# ---------- 3. 笔的划分 ----------
def _find_bis(bars: List[Bar], fxs: List[FX]) -> List[Bi]:
    if len(fxs) < 2:
        return []
    bis = []
    last_fx = fxs[0]
    for i in range(1, len(fxs)):
        cur_fx = fxs[i]
        if cur_fx.type == last_fx.type:
            if cur_fx.type == "TOP" and cur_fx.high > last_fx.high:
                last_fx = cur_fx
            elif cur_fx.type == "BOTTOM" and cur_fx.low < last_fx.low:
                last_fx = cur_fx
            continue
        bars_count = cur_fx.idx - last_fx.idx + 1
        if bars_count < 5:
            continue
        direction = "UP" if last_fx.type == "BOTTOM" else "DOWN"
        bis.append(Bi(
            start_idx=last_fx.idx, end_idx=cur_fx.idx,
            start_dt=last_fx.dt, end_dt=cur_fx.dt,
            direction=direction, high=max(last_fx.high, cur_fx.high),
            low=min(last_fx.low, cur_fx.low), bars_count=bars_count,
        ))
        last_fx = cur_fx
    return bis


# ---------- 4. 中枢识别 ----------
def _find_centers(bis: List[Bi]) -> List[Center]:
    centers = []
    if len(bis) < 3:
        return centers
    i = 0
    while i + 2 < len(bis):
        b1, b2, b3 = bis[i], bis[i+1], bis[i+2]
        zg = min(b1.high, b2.high, b3.high)
        zd = max(b1.low, b2.low, b3.low)
        if zg > zd:
            included_bis = [i, i+1, i+2]
            j = i + 3
            while j < len(bis):
                bj = bis[j]
                if bj.high >= zd and bj.low <= zg:
                    included_bis.append(j)
                    zg = min(zg, bj.high)
                    zd = max(zd, bj.low)
                    j += 1
                else:
                    break
            centers.append(Center(
                bis=included_bis, zg=zg, zd=zd,
                high=max(bis[k].high for k in included_bis),
                low=min(bis[k].low for k in included_bis),
                start_dt=bis[included_bis[0]].start_dt,
                end_dt=bis[included_bis[-1]].end_dt,
            ))
            i = j
        else:
            i += 1
    return centers


# ---------- 5. MACD + 背驰 ----------
def _calc_macd(closes: List[float], fast=12, slow=26, signal=9):
    def ema(values, period):
        if not values:
            return []
        k = 2 / (period + 1)
        result = [values[0]]
        for v in values[1:]:
            result.append(result[-1] + k * (v - result[-1]))
        return result
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    dea = ema(dif, signal)
    macd_hist = [(d - de) * 2 for d, de in zip(dif, dea)]
    return dif, dea, macd_hist


def _detect_divergence_legacy(bars: List[Bar], bis: List[Bi]) -> dict:
    if len(bis) < 2:
        return {"has_divergence": False, "reason": "笔数不足"}
    closes = [b.close for b in bars]
    _, _, macd_hist = _calc_macd(closes)
    last_bi = bis[-1]
    prev_same_dir = None
    for b in reversed(bis[:-1]):
        if b.direction == last_bi.direction:
            prev_same_dir = b
            break
    if prev_same_dir is None:
        return {"has_divergence": False, "reason": "无同向参照笔"}

    def macd_area(start, end, direction):
        sign = 1 if direction == "UP" else -1
        return sum(abs(h) for h in macd_hist[start:end+1] if h * sign > 0)

    last_area = macd_area(last_bi.start_idx, last_bi.end_idx, last_bi.direction)
    prev_area = macd_area(prev_same_dir.start_idx, prev_same_dir.end_idx, prev_same_dir.direction)

    has_div = False
    if last_bi.direction == "UP":
        if last_bi.high > prev_same_dir.high and last_area < prev_area:
            has_div = True
    else:
        if last_bi.low < prev_same_dir.low and last_area < prev_area:
            has_div = True

    return {
        "has_divergence": has_div,
        "direction": last_bi.direction,
        "last_macd_area": round(last_area, 2),
        "prev_macd_area": round(prev_area, 2),
        "energy_ratio": round(last_area / prev_area, 2) if prev_area > 0 else None,
    }


# ---------- 6. Legacy 综合入口 ----------
def _analyze_legacy(bars_raw: List[dict], level: str = "daily") -> dict:
    """旧版自研引擎（fallback）"""
    bars = [Bar(**{k: v for k, v in b.items()
                   if k in ('dt', 'open', 'high', 'low', 'close', 'volume')})
            for b in bars_raw]

    if len(bars) < 30:
        return {"error": "数据不足", "min_required": 30, "actual": len(bars)}

    processed = _process_inclusion(bars)
    fxs = _find_fx(processed)
    bis = _find_bis(processed, fxs)
    centers = _find_centers(bis)
    divergence = _detect_divergence_legacy(processed, bis)

    last_bi = bis[-1] if bis else None
    last_center = centers[-1] if centers else None

    if last_bi:
        if last_bi.direction == "UP":
            structure = "向上笔延伸中" if last_bi.end_idx == len(processed) - 1 else "向上笔已结束"
        else:
            structure = "向下笔延伸中" if last_bi.end_idx == len(processed) - 1 else "向下笔已结束"
    else:
        structure = "结构待形成"

    return {
        "engine": "legacy",
        "engine_version": "v3.0-builtin",
        "level": level,
        "bars_count": len(bars),
        "processed_bars": len(processed),
        "fractal_count": len(fxs),
        "bi_count": len(bis),
        "center_count": len(centers),
        "current_structure": structure,
        "last_bi": asdict(last_bi) if last_bi else None,
        "last_center": asdict(last_center) if last_center else None,
        "divergence": divergence,
        "support": last_center.zd if last_center else None,
        "resistance": last_center.zg if last_center else None,
        "all_centers": [asdict(c) for c in centers[-3:]],
    }


# ═══════════════════════════════════════════════════════════════════════
#  CLI 入口
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        engine_info = f"czsc ({_get_czsc_version()})" if USE_CZSC else "legacy (v3.0-builtin)"
        print(f"缠论分析引擎 — 当前引擎: {engine_info}")
        print(f"用法: python chanlun.py <kline_json_file>")
        print(f"安装 czsc: pip install czsc -U")
        sys.exit(0)

    with open(sys.argv[1]) as f:
        bars_raw = json.load(f)

    result = analyze(bars_raw)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
