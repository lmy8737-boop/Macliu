"""czsc_analyzer.py — v6.4 缠论真值引擎（子环境专用脚本）
==========================================================

设计原则
--------
**只在 .venv-czsc 子环境中运行**，不污染主环境。
主环境（prepare_data.py / 报告渲染）通过 subprocess 调用本脚本，
输入 stdin CSV，输出 stdout JSON。

启动条件
--------
1. 已用 uv / brew 装好 Python 3.11+
2. 已创建 .venv-czsc 虚拟环境
3. .venv-czsc 里已 pip install czsc (会自动拉 0.10.x + rs_czsc)

环境构建命令（一次性）
----------------------
    curl -LsSf https://astral.sh/uv/install.sh | sh
    cd <skill_home>
    ~/.local/bin/uv venv --python 3.11 .venv-czsc
    ~/.local/bin/uv pip install --python .venv-czsc/bin/python czsc

调用方式
--------
    # 主进程（系统 Python 3.9 OK）
    venv_python = SKILL_HOME / '.venv-czsc' / 'bin' / 'python'
    script = SKILL_HOME / 'scripts' / 'calc' / 'czsc_analyzer.py'
    csv_str = ohlcv_df.to_csv(index=False)
    proc = subprocess.run(
        [str(venv_python), str(script)],
        input=csv_str, text=True,
        capture_output=True, timeout=30
    )
    if proc.returncode == 0:
        result = json.loads(proc.stdout)

输入 CSV 列要求
---------------
    必需：date, open, high, low, close
    可选：volume, amount, symbol, freq

输出 JSON Schema
----------------
    {
      "czsc_version": "0.10.12",
      "symbol": "TEST",
      "freq": "D",
      "rows_input": 200,
      "fx_count": 15,                    # 分型数
      "bi_count": 14,                    # 笔数
      "bi_list": [                       # 最近 N 笔（默认全部）
        {
          "direction": "向上" | "向下",
          "high": 158.20, "low": 142.50,
          "amplitude": 15.70, "amplitude_pct": 11.02,
          "start_dt": "2026-01-15", "end_dt": "2026-02-08",
          "bars_count": 18,
          "fx_a_dt": "2026-01-15", "fx_b_dt": "2026-02-08"
        },
        ...
      ],
      "last_bi": { ... },                # 最新一笔
      "last_3_bis": [...],               # 最近 3 笔（前期 + 当前）
      "zs_list": [                       # 中枢（如果识别到）
        {
          "high": 152.80, "low": 144.20,
          "start_dt": "2026-01-20", "end_dt": "2026-02-15",
          "bi_count": 3
        }
      ],
      "divergence": {                    # 背驰（MACD 面积法）
        "detected": true | false,
        "type": "顶背驰" | "底背驰" | None,
        "current_bi_macd_area": 12.5,
        "prior_bi_macd_area": 18.7,
        "ratio": 0.668                   # 当前面积 / 前一同向笔面积
      },
      "elapsed_ms": 245
    }

错误时的输出
------------
    {"error": "<msg>", "stage": "import|parse|czsc|other"}
    返回码：1
"""
from __future__ import annotations

import sys
import json
import time
from io import StringIO


def _err(msg: str, stage: str = "other") -> None:
    """统一错误输出"""
    print(json.dumps({"error": msg, "stage": stage}, ensure_ascii=False),
          file=sys.stdout)
    sys.exit(1)


def _macd_area_for_bi(bi, slow=26, fast=12, signal=9):
    """⚠️ v6.4 已知 bug 函数（保留兼容，新代码请用 _macd_area_for_bi_v2）

    问题：每一笔通常只有 12-14 根 K 线，slow=26 永远不满足，直接 return 0.0。
    v6.4.1 修复方案：用 _calc_macd_full + _macd_area_for_bi_v2（基于整段计算）。
    """
    try:
        import numpy as np
        bars = bi.bars
        if not bars or len(bars) < slow:
            return 0.0
        closes = np.array([float(b.close) for b in bars])
        ema_fast = _ema(closes, fast)
        ema_slow = _ema(closes, slow)
        diff = ema_fast - ema_slow
        dea = _ema(diff, signal)
        macd = (diff - dea) * 2
        if str(bi.direction) == "Direction.Up" or "上" in str(bi.direction):
            return float(sum(m for m in macd if m > 0))
        else:
            return float(sum(abs(m) for m in macd if m < 0))
    except Exception:
        return 0.0


# v6.4.1 新版：基于整段 bars 算 MACD 一次，再按笔切片
def _calc_macd_full(bars_raw, fast=12, slow=26, signal=9):
    """对整段 K 线计算 MACD 序列，返回 {dt: macd_value} 字典。

    v6.4.1：解决"每笔太短不够 slow=26"问题。
    """
    try:
        import numpy as np
        if not bars_raw or len(bars_raw) < slow:
            return {}
        closes = np.array([float(b.close) for b in bars_raw])
        ema_fast = _ema(closes, fast)
        ema_slow = _ema(closes, slow)
        diff = ema_fast - ema_slow
        dea = _ema(diff, signal)
        macd = (diff - dea) * 2
        return {b.dt: float(m) for b, m in zip(bars_raw, macd)}
    except Exception:
        return {}


def _macd_area_for_bi_v2(bi, macd_full):
    """v6.4.1: 按笔的 raw_bars 时间戳，从全局 MACD 字典切片求面积

    向上笔 → 求所有正 MACD 柱面积之和
    向下笔 → 求所有负 MACD 柱面积绝对值之和
    """
    if not macd_full:
        return 0.0
    is_up = ("上" in str(bi.direction)) or ("Up" in str(bi.direction))
    area = 0.0
    # 优先用 bi.raw_bars（原始 K 线，更准），fallback 到 bi.bars（NewBar 合并后）
    bars = bi.raw_bars if hasattr(bi, "raw_bars") and bi.raw_bars else bi.bars
    for b in bars:
        m = macd_full.get(b.dt, 0.0)
        if is_up and m > 0:
            area += m
        elif (not is_up) and m < 0:
            area += abs(m)
    return area


def _ema(values, period):
    import numpy as np
    out = np.zeros_like(values)
    multiplier = 2.0 / (period + 1)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = (values[i] - out[i - 1]) * multiplier + out[i - 1]
    return out


def _detect_divergence(c):
    """检测当前最新一笔是否构成背驰（顶/底背驰）— v6.4.1 修复版"""
    bi_list = c.bi_list
    if len(bi_list) < 3:
        return {"detected": False, "type": None, "reason": "笔数不足 3"}
    last_bi = bi_list[-1]
    # 找前一同向笔
    prior_same = None
    for bi in reversed(bi_list[:-1]):
        if str(bi.direction) == str(last_bi.direction):
            prior_same = bi
            break
    if prior_same is None:
        return {"detected": False, "type": None, "reason": "无前一同向笔"}

    # ─── v6.4.1: 用整段 bars_raw 算一次 MACD，再按笔切片 ─────────
    macd_full = _calc_macd_full(c.bars_raw)
    cur_area = _macd_area_for_bi_v2(last_bi, macd_full)
    prior_area = _macd_area_for_bi_v2(prior_same, macd_full)

    if prior_area <= 0:
        return {"detected": False, "type": None,
                "current_bi_macd_area": round(cur_area, 3),
                "prior_bi_macd_area": round(prior_area, 3),
                "reason": "前一笔 MACD 面积 ≤0，无法对比"}
    ratio = cur_area / prior_area
    # 价格新高/新低 + MACD 面积缩小 = 背驰
    is_up = ("上" in str(last_bi.direction)) or ("Up" in str(last_bi.direction))
    if is_up:
        # 顶背驰：当前笔高点 > 前一同向笔高点 + MACD 面积 < 前一同向笔
        if last_bi.high > prior_same.high and ratio < 0.85:
            return {"detected": True, "type": "顶背驰",
                    "current_bi_macd_area": round(cur_area, 3),
                    "prior_bi_macd_area": round(prior_area, 3),
                    "ratio": round(ratio, 3),
                    "reason": f"当前笔创新高 {last_bi.high:.2f} > 前 {prior_same.high:.2f}，但 MACD 面积仅前 {ratio*100:.1f}%"}
    else:
        # 底背驰：当前笔低点 < 前一同向笔低点 + MACD 面积 < 前一同向笔
        if last_bi.low < prior_same.low and ratio < 0.85:
            return {"detected": True, "type": "底背驰",
                    "current_bi_macd_area": round(cur_area, 3),
                    "prior_bi_macd_area": round(prior_area, 3),
                    "ratio": round(ratio, 3),
                    "reason": f"当前笔创新低 {last_bi.low:.2f} < 前 {prior_same.low:.2f}，但 MACD 面积仅前 {ratio*100:.1f}%"}
    return {"detected": False, "type": None,
            "current_bi_macd_area": round(cur_area, 3),
            "prior_bi_macd_area": round(prior_area, 3),
            "ratio": round(ratio, 3),
            "reason": "未触发背驰条件（价格未创新高/低 或 MACD 面积比例 ≥0.85）"}


def _detect_centers(bi_list):
    """⚠️ v6.4 minimal 中枢算法（保留兼容，新代码请用 _detect_centers_czsc）

    v6.4.2 已升级：用 czsc.ZS 真值（多 4 个属性 + is_valid 过滤）。
    """
    if len(bi_list) < 3:
        return []
    centers = []
    i = 0
    while i + 2 < len(bi_list):
        b1, b2, b3 = bi_list[i], bi_list[i + 1], bi_list[i + 2]
        zs_high = min(max(b1.high, b1.low), max(b2.high, b2.low), max(b3.high, b3.low))
        zs_low = max(min(b1.high, b1.low), min(b2.high, b2.low), min(b3.high, b3.low))
        if zs_high > zs_low:
            centers.append({
                "high": round(float(zs_high), 3),
                "low": round(float(zs_low), 3),
                "start_dt": b1.fx_a.dt.strftime("%Y-%m-%d"),
                "end_dt": b3.fx_b.dt.strftime("%Y-%m-%d"),
                "bi_count": 3,
            })
            i += 3
        else:
            i += 1
    return centers


def _detect_centers_czsc(bi_list):
    """v6.4.2: 用 czsc.ZS 真值识别中枢（替代 minimal）

    优势：
    - 同样的 zg/zd（与 minimal 实测一致）
    - 多 4 个标准属性: gg (中枢中最高) / dd (中枢中最低) / zz (中线) / sdir/edir (进出方向)
    - czsc.ZS.is_valid() 过滤掉无效中枢
    - 时间戳直接来自笔的 fx 端点，不用 strftime 转换
    """
    if len(bi_list) < 3:
        return []
    try:
        from czsc import ZS
    except Exception:
        # 降级到 minimal
        return _detect_centers(bi_list)

    centers = []
    i = 0
    while i + 2 < len(bi_list):
        try:
            zs = ZS(bi_list[i:i + 3])
            # czsc 0.10.x: is_valid 是方法，需要调用
            valid = zs.is_valid() if callable(getattr(zs, "is_valid", None)) else (zs.zg > zs.zd)
            if valid and zs.zg > zs.zd:
                centers.append({
                    "high": round(float(zs.zg), 3),       # 中枢上沿（zhongshu gao）
                    "low": round(float(zs.zd), 3),        # 中枢下沿（zhongshu di）
                    "mid": round(float(zs.zz), 3),        # 🆕 中线（zg+zd 平均）
                    "max_high": round(float(zs.gg), 3),   # 🆕 中枢中最高（gao gao）
                    "min_low": round(float(zs.dd), 3),    # 🆕 中枢中最低（di di）
                    "start_dt": zs.sdt.strftime("%Y-%m-%d"),
                    "end_dt": zs.edt.strftime("%Y-%m-%d"),
                    "enter_direction": str(zs.sdir),      # 🆕 进入方向
                    "exit_direction": str(zs.edir),       # 🆕 离开方向
                    "bi_count": 3,
                    "engine": "czsc.ZS",
                })
                i += 3
            else:
                i += 1
        except Exception:
            i += 1
    return centers


def _bi_to_dict(bi):
    """笔对象 → JSON 友好 dict"""
    direction = str(bi.direction)
    # 标准化方向（czsc 0.10.x: Direction.Up / Direction.Down）
    if "Up" in direction or "上" in direction:
        direction_zh = "向上"
    elif "Down" in direction or "下" in direction:
        direction_zh = "向下"
    else:
        direction_zh = direction
    high = float(bi.high)
    low = float(bi.low)
    return {
        "direction": direction_zh,
        "direction_raw": direction,
        "high": round(high, 3),
        "low": round(low, 3),
        "amplitude": round(high - low, 3),
        "amplitude_pct": round((high - low) / low * 100, 2) if low > 0 else None,
        "start_dt": bi.fx_a.dt.strftime("%Y-%m-%d"),
        "end_dt": bi.fx_b.dt.strftime("%Y-%m-%d"),
        "fx_a_value": round(float(bi.fx_a.fx), 3),
        "fx_b_value": round(float(bi.fx_b.fx), 3),
        "bars_count": len(bi.bars) if hasattr(bi, "bars") and bi.bars else 0,
    }


def _detect_3rd_pivot(c, macd_full=None):
    """v6.4.3: 第三类买卖点识别（基于 czsc.ZS + MACD 面积强弱判定）

    缠论标准定义：
    - 三买：1+2+3 笔构成中枢，第 4 笔向上离开，第 5 笔回踩但不回中枢内（low > zg）
    - 三卖：1+2+3 笔构成中枢，第 4 笔向下离开，第 5 笔反弹但不回中枢内（high < zd）

    强弱判定（用 v6.4.1 MACD 面积真值）：
    - 强势 3 买/卖：离开笔 MACD 面积 ≥ 中枢内同向笔的最大值（动能足）
    - 弱势 3 买/卖：相反（潜在假突破）

    返回：dict 含 detected / type / strength / 中枢和笔的引用 / 解读
    """
    bi_list = c.bi_list
    if len(bi_list) < 5:
        return {"detected": False, "type": None, "reason": "笔数不足 5（最少 1+2+3 中枢 + 4 离开 + 5 回踩）"}

    try:
        from czsc import ZS
    except Exception:
        return {"detected": False, "type": None, "reason": "czsc.ZS 不可用"}

    # 从最后往前找：尝试 [N-5, N-4, N-3] 三笔中枢 + N-2 离开笔 + N-1 当前回踩笔
    # 也兼容 [N-4, N-3, N-2] + N-1 离开笔 + （等待回踩中）
    candidates = []
    if len(bi_list) >= 5:
        # 标准型态：3 笔中枢 + 4 离开 + 5 回踩
        candidates.append((bi_list[-5:-2], bi_list[-2], bi_list[-1], "完整型态"))
    if len(bi_list) >= 4:
        # 仅形成离开笔，回踩还未发生
        candidates.append((bi_list[-4:-1], bi_list[-1], None, "等待回踩"))

    for zs_bis, leave_bi, retrace_bi, stage in candidates:
        try:
            zs = ZS(zs_bis)
            if not (zs.is_valid() if callable(getattr(zs, "is_valid", None)) else (zs.zg > zs.zd)):
                continue
            zg = float(zs.zg)
            zd = float(zs.zd)

            leave_dir = "向上" if "上" in str(leave_bi.direction) or "Up" in str(leave_bi.direction) else "向下"

            if leave_dir == "向上":
                # 离开笔必须真的离开（高点超过 zg）
                if float(leave_bi.high) <= zg:
                    continue
                if retrace_bi is None:
                    return {
                        "detected": False, "stage": stage,
                        "type": "潜在三买", "type_zh": "potential_3buy",
                        "reason": f"中枢 [{zd:.2f},{zg:.2f}] 已被向上突破至 {float(leave_bi.high):.2f}，等待回踩确认",
                        "zs_zg": round(zg, 3), "zs_zd": round(zd, 3),
                        "leave_bi_high": round(float(leave_bi.high), 3),
                    }
                # 回踩笔必须向下
                if "上" in str(retrace_bi.direction) or "Up" in str(retrace_bi.direction):
                    continue
                retrace_low = float(retrace_bi.low)
                if retrace_low > zg:
                    # ✅ 三买确认：回踩低点 > 中枢上沿
                    strength = _judge_3rd_strength(zs_bis, leave_bi, "向上", macd_full)
                    return {
                        "detected": True, "type": "三买", "type_en": "3rd_buy", "stage": stage,
                        "strength": strength["level"],
                        "zs_zg": round(zg, 3), "zs_zd": round(zd, 3),
                        "zs_dt": f"{zs.sdt.strftime('%Y-%m-%d')} → {zs.edt.strftime('%Y-%m-%d')}",
                        "leave_bi_dt": f"{leave_bi.fx_a.dt.strftime('%Y-%m-%d')} → {leave_bi.fx_b.dt.strftime('%Y-%m-%d')}",
                        "leave_bi_high": round(float(leave_bi.high), 3),
                        "retrace_bi_dt": f"{retrace_bi.fx_a.dt.strftime('%Y-%m-%d')} → {retrace_bi.fx_b.dt.strftime('%Y-%m-%d')}",
                        "retrace_low": round(retrace_low, 3),
                        "macd_strength": strength,
                        "reason": f"中枢 [{zd:.2f},{zg:.2f}] 向上突破至 {float(leave_bi.high):.2f}，回踩 {retrace_low:.2f} 未回中枢（>{zg:.2f}），三买确认 ✅",
                    }
            else:  # 离开笔向下
                if float(leave_bi.low) >= zd:
                    continue
                if retrace_bi is None:
                    return {
                        "detected": False, "stage": stage,
                        "type": "潜在三卖", "type_zh": "potential_3sell",
                        "reason": f"中枢 [{zd:.2f},{zg:.2f}] 已被向下击穿至 {float(leave_bi.low):.2f}，等待反弹确认",
                        "zs_zg": round(zg, 3), "zs_zd": round(zd, 3),
                        "leave_bi_low": round(float(leave_bi.low), 3),
                    }
                if "下" in str(retrace_bi.direction) or "Down" in str(retrace_bi.direction):
                    continue
                retrace_high = float(retrace_bi.high)
                if retrace_high < zd:
                    strength = _judge_3rd_strength(zs_bis, leave_bi, "向下", macd_full)
                    return {
                        "detected": True, "type": "三卖", "type_en": "3rd_sell", "stage": stage,
                        "strength": strength["level"],
                        "zs_zg": round(zg, 3), "zs_zd": round(zd, 3),
                        "zs_dt": f"{zs.sdt.strftime('%Y-%m-%d')} → {zs.edt.strftime('%Y-%m-%d')}",
                        "leave_bi_dt": f"{leave_bi.fx_a.dt.strftime('%Y-%m-%d')} → {leave_bi.fx_b.dt.strftime('%Y-%m-%d')}",
                        "leave_bi_low": round(float(leave_bi.low), 3),
                        "retrace_bi_dt": f"{retrace_bi.fx_a.dt.strftime('%Y-%m-%d')} → {retrace_bi.fx_b.dt.strftime('%Y-%m-%d')}",
                        "retrace_high": round(retrace_high, 3),
                        "macd_strength": strength,
                        "reason": f"中枢 [{zd:.2f},{zg:.2f}] 向下击穿至 {float(leave_bi.low):.2f}，反弹 {retrace_high:.2f} 未回中枢（<{zd:.2f}），三卖确认 ✅",
                    }
        except Exception:
            continue

    return {"detected": False, "type": None, "reason": "未在最后 5 笔识别到第三类买卖点（中枢 + 离开 + 回踩 三段未对齐）"}


def _judge_3rd_strength(zs_bis, leave_bi, direction, macd_full):
    """判定 3 买 / 3 卖的强弱（基于 MACD 面积对比）

    强势：离开笔 MACD 面积 ≥ 中枢内同向笔最大值（动能比中枢任何一笔都强）
    中性：相当
    弱势：离开笔 MACD 面积 < 中枢内同向笔最大值（潜在假突破）
    """
    if not macd_full:
        return {"level": "未知", "reason": "MACD 数据不可用"}
    leave_area = _macd_area_for_bi_v2(leave_bi, macd_full)
    same_dir_areas = []
    for bi in zs_bis:
        bi_dir = "向上" if "上" in str(bi.direction) or "Up" in str(bi.direction) else "向下"
        if bi_dir == direction:
            same_dir_areas.append(_macd_area_for_bi_v2(bi, macd_full))
    if not same_dir_areas:
        return {"level": "未知", "leave_macd_area": round(leave_area, 3), "reason": "中枢内无同向笔可对比"}
    max_zs_area = max(same_dir_areas)
    avg_zs_area = sum(same_dir_areas) / len(same_dir_areas)
    if leave_area >= max_zs_area * 1.1:
        level = "强势"
    elif leave_area >= avg_zs_area * 0.8:
        level = "中性"
    else:
        level = "弱势"
    return {
        "level": level,
        "leave_macd_area": round(leave_area, 3),
        "zs_max_same_dir_area": round(max_zs_area, 3),
        "zs_avg_same_dir_area": round(avg_zs_area, 3),
        "ratio_to_max": round(leave_area / max_zs_area, 3) if max_zs_area > 0 else None,
        "reason": (
            f"离开笔 MACD 面积 {leave_area:.2f} vs 中枢同向笔最大 {max_zs_area:.2f} "
            f"({leave_area/max_zs_area*100:.0f}%) → {level}"
        ) if max_zs_area > 0 else f"离开笔 MACD 面积 {leave_area:.2f}",
    }


def main():
    t0 = time.time()
    # ─── 1. 读输入 ───────────────────────────────────────────
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            _err("stdin empty (要求 CSV 输入)", "parse")
        import pandas as pd
        df = pd.read_csv(StringIO(raw))
    except Exception as e:
        _err(f"CSV 解析失败: {e!r:.200}", "parse")

    if "date" not in df.columns:
        _err(f"CSV 缺少 'date' 列。当前列: {list(df.columns)}", "parse")
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            _err(f"CSV 缺少 '{col}' 列", "parse")

    # ─── 2. 导入 czsc（必须在子环境）─────────────────────────
    try:
        import czsc
        from czsc import CZSC, RawBar, Freq
    except Exception as e:
        _err(f"czsc 未安装/导入失败: {e!r:.200}（确认在 .venv-czsc 子环境运行）", "import")

    # ─── 3. 转 RawBar ────────────────────────────────────────
    try:
        symbol = df.get("symbol", ["UNK"])[0] if "symbol" in df.columns else "UNK"
        freq_str = df.get("freq", ["D"])[0] if "freq" in df.columns else "D"
        freq_map = {"D": Freq.D, "1D": Freq.D, "60min": Freq.F60,
                    "30min": Freq.F30, "15min": Freq.F15}
        freq = freq_map.get(freq_str, Freq.D)

        bars = []
        for i, row in df.iterrows():
            bars.append(RawBar(
                symbol=str(symbol),
                id=int(i),
                dt=pd.to_datetime(row["date"]).to_pydatetime(),
                freq=freq,
                open=float(row["open"]),
                close=float(row["close"]),
                high=float(row["high"]),
                low=float(row["low"]),
                vol=float(row.get("volume", 0)) if "volume" in df.columns else 0.0,
                amount=float(row.get("amount", 0)) if "amount" in df.columns else 0.0,
            ))
    except Exception as e:
        _err(f"RawBar 转换失败: {e!r:.200}", "parse")

    # ─── 4. 跑 czsc ──────────────────────────────────────────
    try:
        c = CZSC(bars)
    except Exception as e:
        _err(f"czsc.CZSC() 计算失败: {e!r:.200}", "czsc")

    # ─── 5. 抽取结构 ──────────────────────────────────────────
    bi_list_full = [_bi_to_dict(bi) for bi in c.bi_list]
    last_bi = bi_list_full[-1] if bi_list_full else None
    last_3_bis = bi_list_full[-3:] if len(bi_list_full) >= 3 else bi_list_full

    zs_list = _detect_centers_czsc(c.bi_list)  # v6.4.2: 用 czsc.ZS 真值
    divergence = _detect_divergence(c)
    # v6.4.3: 第三类买卖点识别
    macd_full_for_pivot = _calc_macd_full(c.bars_raw)
    pivot_3rd = _detect_3rd_pivot(c, macd_full=macd_full_for_pivot)

    elapsed_ms = int((time.time() - t0) * 1000)

    out = {
        "czsc_version": czsc.__version__,
        "symbol": str(symbol),
        "freq": freq_str,
        "rows_input": len(df),
        "fx_count": len(c.fx_list),
        "bi_count": len(c.bi_list),
        "bi_list": bi_list_full,
        "last_bi": last_bi,
        "last_3_bis": last_3_bis,
        "zs_list": zs_list,
        "zs_count": len(zs_list),
        "divergence": divergence,
        "pivot_3rd": pivot_3rd,  # v6.4.3 新增
        "elapsed_ms": elapsed_ms,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
