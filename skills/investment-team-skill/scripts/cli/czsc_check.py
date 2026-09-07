#!/usr/bin/env python3
"""czsc_check.py — v6.4 一键缠论查询工具

用法（在 SKILL_HOME 目录下执行）：
    .venv-czsc/bin/python scripts/cli/czsc_check.py <symbol> [count] [-m|--multi-level]

雪球 symbol 格式：
    A 股：    SH600519 / SZ301305
    港股：    01133 / 00700（前面补 0 凑 5 位）
    美股：    APH / NVDA / TSLA（直接字母代码）
    指数：    SH000001（上证指数）

count：日级拉多少根日线，默认 300

参数（v6.4.4 起）：
    -m, --multi-level   同时拉日级 + 周级，输出共振判定

v6.5.0 新增：
    --auto-setup        如果 import czsc 失败，自动调 scripts/setup/auto_setup_czsc.sh
                        三级 fallback 安装（uv → python3.11 venv → pip --user），
                        默认开启。失败时打印根因+用户操作建议。
    --no-auto-setup     关闭自启动（保留 v6.4 行为：失败直接报错）
"""
from __future__ import annotations

import os
import sys
import time
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# 让 from data import xxx 能 work
SKILL_HOME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_HOME / "scripts"))


# ============ v6.5.0 czsc 自启动（在 import czsc 之前必须先确保 venv 可用） ============

def _ensure_czsc_runtime() -> None:
    """v6.5.0：在系统 Python（或当前 Python）import czsc 之前先确保运行时可用。

    场景 A：当前 Python 是 .venv-czsc/bin/python — 直接尝试 import，成功即返回
    场景 B：当前是系统 Python — 调用 setup 脚本，成功后用 .venv-czsc 重启自己
    场景 C：自启动失败 — 抛 RuntimeError，让 caller 走 fallback
    """
    # 试 import：成功就直接返回
    try:
        import czsc  # noqa: F401
        return
    except Exception:
        pass

    if "--no-auto-setup" in sys.argv:
        raise RuntimeError("czsc import 失败且 --no-auto-setup，无法继续")

    setup_sh = SKILL_HOME / "scripts" / "setup" / "auto_setup_czsc.sh"
    if not setup_sh.exists():
        raise RuntimeError(f"v6.5 自启动脚本缺失：{setup_sh}")

    print("🔧 [czsc_check.py v6.5.0] 检测到 czsc 不可用，启动自动安装...", file=sys.stderr)
    try:
        proc = subprocess.run(["bash", str(setup_sh)], timeout=600)
    except subprocess.TimeoutExpired:
        raise RuntimeError("czsc 自启动超时（>10min）")

    if proc.returncode != 0:
        raise RuntimeError(f"czsc 自启动失败（exit={proc.returncode}）— 见 .venv-czsc-setup.log")

    # 自启动成功后用 .venv-czsc 重启当前脚本
    venv_python = SKILL_HOME / ".venv-czsc" / "bin" / "python"
    if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
        print(f"♻️  [v6.5.0] 用 .venv-czsc 重启 czsc_check.py（{venv_python}）...", file=sys.stderr)
        # 移除 --auto-setup 避免循环；保留其他参数
        new_argv = [a for a in sys.argv if a not in ("--auto-setup",)]
        os.execv(str(venv_python), [str(venv_python)] + new_argv)


# 默认 auto-setup 开启（除非用户明示 --no-auto-setup）
if "--no-auto-setup" not in sys.argv:
    _ensure_czsc_runtime()


from data.kline_fetcher import _xueqiu_session  # noqa: E402


def fetch_kline(symbol: str, period: str, count: int):
    """拉雪球 K 线，返回 (RawBar 列表, items 列表)"""
    s = _xueqiu_session()
    end_ms = int(time.time() * 1000)
    url = (
        f"https://stock.xueqiu.com/v5/stock/chart/kline.json"
        f"?symbol={symbol}&begin={end_ms}&period={period}&type=before&count=-{count}"
    )
    j = s.get(url, timeout=10).json()
    items = (j.get("data") or {}).get("item") or []
    if not items:
        return None, j

    import czsc
    freq_map = {"day": czsc.Freq.D, "week": czsc.Freq.W, "month": czsc.Freq.M}
    freq = freq_map[period]
    bars = []
    for i, it in enumerate(items):
        if it[5] is None:
            continue
        bars.append(czsc.RawBar(
            symbol=symbol, id=i,
            dt=datetime.utcfromtimestamp(it[0] / 1000),
            freq=freq,
            open=float(it[2]), high=float(it[3]),
            low=float(it[4]), close=float(it[5]),
            vol=float(it[1]) if it[1] else 0,
            amount=float(it[9]) if len(it) > 9 and it[9] else 0,
        ))
    return bars, items


def render_single_level(c, bars, label: str = "日级"):
    """渲染单级别 czsc 分析结果（笔 / 中枢 / 当前价）"""
    import czsc
    print(f"分型 fx:  {len(c.fx_list)}")
    print(f"笔   bi:  {len(c.bi_list)}")
    print(f"K 线:    {len(bars)} 根（{bars[0].dt.strftime('%Y-%m-%d')} → "
          f"{bars[-1].dt.strftime('%Y-%m-%d')}）")
    print(f"当前价:   {bars[-1].close}")
    print()

    if c.bi_list:
        last_n = min(5, len(c.bi_list))
        print(f"🔍 最近 {last_n} 笔（{label}）：")
        print()
        for i, bi in enumerate(c.bi_list[-last_n:], start=len(c.bi_list) - last_n + 1):
            arrow = "⬆️" if "上" in str(bi.direction) or "Up" in str(bi.direction) else "⬇️"
            high = float(bi.high)
            low = float(bi.low)
            amp_pct = (high - low) / low * 100 if low > 0 else 0
            print(f"  笔 #{i:>2} {arrow} {str(bi.direction):>8} | "
                  f"{bi.fx_a.dt.strftime('%Y-%m-%d')} → {bi.fx_b.dt.strftime('%Y-%m-%d')} | "
                  f"高 {high:>9.3f}  低 {low:>9.3f}  幅度 {amp_pct:>6.2f}%")
        print()

    # 中枢识别（用 czsc.ZS 真值，v6.4.2）
    bi_list = c.bi_list
    centers = []
    i = 0
    while i + 2 < len(bi_list):
        try:
            zs = czsc.ZS(bi_list[i:i + 3])
            valid = zs.is_valid() if callable(getattr(zs, "is_valid", None)) else (zs.zg > zs.zd)
            if valid and zs.zg > zs.zd:
                centers.append(zs)
                i += 3
            else:
                i += 1
        except Exception:
            i += 1

    if centers:
        cur = float(bars[-1].close)
        last_n_zs = min(3, len(centers))
        print(f"🎯 中枢识别（共 {len(centers)} 个，最近 {last_n_zs} 个）：")
        print()
        for zs in centers[-last_n_zs:]:
            zg = float(zs.zg)
            zd = float(zs.zd)
            zz = float(zs.zz)
            if cur > zg:
                pos = "🟢 当前在上"
            elif cur < zd:
                pos = "🔴 当前在下"
            else:
                pos = "🟡 当前在内"
            print(f"  {zs.sdt.strftime('%Y-%m-%d')} → {zs.edt.strftime('%Y-%m-%d')} | "
                  f"zg {zg:>9.3f}  zd {zd:>9.3f}  zz(中线) {zz:>9.3f} | {pos}")
        print()
    return centers


def render_resonance(daily_bars, weekly_bars, daily_c, weekly_c, daily_zs, weekly_zs):
    """v6.4.4 共振判定（在 czsc_check.py 内部直接计算，避免 subprocess）"""
    cur = float(daily_bars[-1].close)

    # 日级最新笔方向
    daily_dir = "?"
    if daily_c.bi_list:
        last_d = daily_c.bi_list[-1]
        daily_dir = "向上" if "上" in str(last_d.direction) or "Up" in str(last_d.direction) else "向下"

    # 周级最新笔方向
    weekly_dir = "?"
    if weekly_c.bi_list:
        last_w = weekly_c.bi_list[-1]
        weekly_dir = "向上" if "上" in str(last_w.direction) or "Up" in str(last_w.direction) else "向下"

    # 周级最新中枢位置
    weekly_zs_pos = "未识别"
    weekly_zs_str = "—"
    if weekly_zs:
        last_w_zs = weekly_zs[-1]
        zg = float(last_w_zs.zg)
        zd = float(last_w_zs.zd)
        weekly_zs_str = f"[{zd:.3f}, {zg:.3f}]"
        if cur > zg:
            weekly_zs_pos = "在周中枢上方"
        elif cur < zd:
            weekly_zs_pos = "在周中枢下方"
        else:
            weekly_zs_pos = "在周中枢内"

    # 综合判定
    if daily_dir == "向上" and weekly_dir == "向上":
        if weekly_zs_pos == "在周中枢上方":
            verdict = "📈 强多共振"
            level = "强多"
        else:
            verdict = "📈 弱多（周级中枢内/未确认）"
            level = "弱多"
    elif daily_dir == "向下" and weekly_dir == "向下":
        if weekly_zs_pos == "在周中枢下方":
            verdict = "📉 强空共振"
            level = "强空"
        else:
            verdict = "📉 弱空（周级中枢内/未确认）"
            level = "弱空"
    elif daily_dir == "向上" and weekly_dir == "向下":
        verdict = "⚠️ 日级反抗周级（小反大，胜率低）"
        level = "日多周空"
    elif daily_dir == "向下" and weekly_dir == "向上":
        verdict = "⚠️ 日级反抗周级（小反大，胜率低）"
        level = "日空周多"
    else:
        verdict = "⚪ 不共振"
        level = "中性"

    print("═" * 70)
    print(f" 🎯 v6.4.4 多周期共振判定")
    print("═" * 70)
    print(f"  verdict:        {verdict}")
    print(f"  级别一致性:    {level}")
    print(f"  日级最新笔:    {daily_dir}")
    print(f"  周级最新笔:    {weekly_dir}")
    print(f"  周级最新中枢:  {weekly_zs_str}")
    print(f"  当前价位置:    {weekly_zs_pos}（cur = {cur}）")
    print("═" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="v6.4 czsc 一键缠论查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("symbol", help="雪球 symbol（如 01133 / SZ301305 / APH）")
    parser.add_argument("count", nargs="?", type=int, default=300,
                        help="日级 K 线数（默认 300）")
    parser.add_argument("-m", "--multi-level", action="store_true",
                        help="🆕 v6.4.4: 同时跑日级 + 周级 + 共振判定")
    parser.add_argument("--weekly-count", type=int, default=100,
                        help="多级别模式下周 K 数（默认 100，约 2 年）")
    args = parser.parse_args()

    symbol = args.symbol
    if symbol.isdigit() and len(symbol) in (4, 5):
        symbol = symbol.zfill(5)

    # ─── 拉日级 K 线 ───────────────────────────────
    print(f"📡 拉取日级 K 线 {symbol} ({args.count} 根) ...")
    daily_bars, _ = fetch_kline(symbol, "day", args.count)
    if not daily_bars:
        print(f"❌ 雪球返回空。可能 symbol 错误。"); sys.exit(1)
    print(f"   ✓ {len(daily_bars)} 根")

    # ─── 跑日级 czsc ───────────────────────────────
    import czsc
    print(f"📐 跑 czsc {czsc.__version__} 日级缠论引擎 ...")
    t0 = time.time()
    daily_c = czsc.CZSC(daily_bars)
    print(f"   ✓ {(time.time()-t0)*1000:.0f} ms")
    print()

    print("═" * 70)
    print(f" {symbol} — czsc {czsc.__version__} 缠论真值（日级）")
    print("═" * 70)
    daily_zs = render_single_level(daily_c, daily_bars, label="日级")

    if not args.multi_level:
        # 单级别模式：日级最后一笔总结
        if daily_c.bi_list:
            last = daily_c.bi_list[-1]
            print("═" * 70)
            print(f"最新笔方向: {last.direction}")
            high = float(last.high); low = float(last.low)
            if "上" in str(last.direction) or "Up" in str(last.direction):
                print(f"上行起点: {last.fx_a.dt.strftime('%Y-%m-%d')} @ {low:.3f}")
                print(f"上行终点: {last.fx_b.dt.strftime('%Y-%m-%d')} @ {high:.3f}")
            else:
                print(f"下行起点: {last.fx_a.dt.strftime('%Y-%m-%d')} @ {high:.3f}")
                print(f"下行终点: {last.fx_b.dt.strftime('%Y-%m-%d')} @ {low:.3f}")
            print("═" * 70)
            print()
            print(f"💡 想看多周期共振？加 -m 或 --multi-level")
        return

    # ─── v6.4.4 多级别模式：再拉周 K + 跑 czsc ──────
    print()
    print(f"📡 拉取周级 K 线 {symbol} ({args.weekly_count} 根周 K，约 2 年) ...")
    weekly_bars, _ = fetch_kline(symbol, "week", args.weekly_count)
    if not weekly_bars:
        print(f"⚠️ 周 K 拉取失败，退化为日级单级别")
        return
    print(f"   ✓ {len(weekly_bars)} 根周 K")

    print(f"📐 跑 czsc 周级缠论引擎 ...")
    t0 = time.time()
    weekly_c = czsc.CZSC(weekly_bars)
    print(f"   ✓ {(time.time()-t0)*1000:.0f} ms")
    print()

    print("═" * 70)
    print(f" {symbol} — czsc {czsc.__version__} 缠论真值（周级）")
    print("═" * 70)
    weekly_zs = render_single_level(weekly_c, weekly_bars, label="周级")

    # ─── 共振判定 ───────────────────────────────
    print()
    render_resonance(daily_bars, weekly_bars, daily_c, weekly_c, daily_zs, weekly_zs)


if __name__ == "__main__":
    main()
