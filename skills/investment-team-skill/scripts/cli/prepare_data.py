#!/usr/bin/env python3
# 适配形态: agent
"""
prepare_data.py — v6.2 skill agent 数据采集一站式入口
====================================================
目标：让 skill agent 形态独立完成全部数据采集，不再依赖 mattermost-bot 子目录。

用法：
    # 单股深度（stock mode）—— 拉 K 线 → 缠论 → 财务（target + peers）
    python3 scripts/cli/prepare_data.py --mode stock --target 601138
    python3 scripts/cli/prepare_data.py --mode stock --target 601138 --peers 603296,000938,002230

    # 全盘（portfolio mode）—— 全部 6 类
    python3 scripts/cli/prepare_data.py --mode portfolio

    # ETF（etf mode）—— 跳过 finance
    python3 scripts/cli/prepare_data.py --mode etf --target 510300

    # 仅宏观（macro mode）—— 最快
    python3 scripts/cli/prepare_data.py --mode macro

输出：
    engine/data/structures/structures_<date>.json
    engine/data/finance/finance_<date>.json
    engine/data/holdings/holdings_latest.json (read-only)
    engine/data/macro/macro_indicators.json
    engine/data/scanner/scanner_<date>.json   (仅 portfolio)
    engine/data/chip/chip_analysis_<date>.json (仅 portfolio/etf)

设计原则：
  - skill agent 形态优先：不依赖 mattermost-bot
  - 复用 scripts/data/* 层（与 bot 共享数据层）
  - peer 池可由 industry_peers.yaml 自动推导
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date as Date
from pathlib import Path

# 让 from data import xxx 能 work
SKILL_HOME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_HOME / "scripts"))

from data.common import DATA_DIR, DataCollectionError  # noqa: E402
from data.structures_engine import collect_structures_for_tickers  # noqa: E402
from data.finance_fetcher import collect_finance_for_tickers  # noqa: E402


# ============ v6.3 P0 修复：启动前置自动化 ============

def _ensure_trading_db() -> None:
    """v6.3 P0-2: agent 形态首次部署时自动建 trading.db（幂等）。
    没有 DB → beauty_score / signal_store / 5 号 audit 链全废，强制兜底。
    """
    db_path = SKILL_HOME / "engine" / "data" / "trading.db"
    if db_path.exists():
        return
    sys.path.insert(0, str(SKILL_HOME / "scripts" / "db"))
    try:
        os.environ.setdefault("INVESTMENT_TEAM_DB", str(db_path))
        from init_db import init_db as _init  # type: ignore
        _init()
    except Exception as e:
        print(f"⚠️  trading.db 自动初始化失败：{e}", file=sys.stderr)


def _ensure_holdings_imported(today: str) -> None:
    """v6.3 P0-3: 如果根目录有 holdings.csv 但 holdings_latest.json 是空 fixture，
    自动调 scripts/pipeline/import_holdings.py 同步。
    holdings.csv 是隐私文件，约定放在 SKILL_HOME 根目录（应加入 .gitignore）。
    """
    csv_path = SKILL_HOME / "holdings.csv"
    if not csv_path.exists():
        return  # 老板还没建 holdings.csv，跳过

    json_path = SKILL_HOME / "engine" / "data" / "holdings" / "holdings_latest.json"
    # 检查 json 是否需要更新（csv mtime > json mtime 或 json 是空 fixture）
    needs_update = True
    if json_path.exists():
        if json_path.stat().st_mtime > csv_path.stat().st_mtime:
            try:
                data = json.loads(json_path.read_text())
                if data.get("positions"):  # 已有持仓数据且较新，跳过
                    needs_update = False
            except Exception:
                pass
    if not needs_update:
        return

    sys.path.insert(0, str(SKILL_HOME / "scripts" / "pipeline"))
    try:
        import importlib
        mod = importlib.import_module("import_holdings")
        if hasattr(mod, "main"):
            old_argv = sys.argv
            # import_holdings.py 用 -i / -d 作为参数（不是 --csv）
            sys.argv = ["import_holdings.py", "-i", str(csv_path), "-d", today]
            try:
                mod.main()
                print(f"  ✓ holdings.csv → holdings_latest.json 已同步")
            finally:
                sys.argv = old_argv
    except Exception as e:
        print(f"⚠️  持仓自动导入失败：{e}", file=sys.stderr)


# ============ v6.4 czsc 子环境（缠论真值）+ v6.5 自启动 ============

def _ensure_czsc_venv(auto_install: bool = True) -> Path | None:
    """v6.4 + v6.5: 检测/确认 .venv-czsc 子环境是否就绪。
    返回 venv 内的 python 可执行文件路径，未就绪则返回 None（fallback 到江恩位）。

    v6.5 升级：默认 auto_install=True — 若 venv 不存在或 import czsc 失败，
    会自动调用 scripts/setup/auto_setup_czsc.sh 三级 fallback 安装：
        Tier 1: uv venv --python 3.11 + uv pip install czsc（首选 ~5 分钟）
        Tier 2: 系统 python3.11 -m venv + pip install czsc
        Tier 3: python3 -m pip install --user czsc（兜底，不创建 venv）

    手工构建一次（~5 分钟，仍支持向后兼容）：
        curl -LsSf https://astral.sh/uv/install.sh | sh
        cd <SKILL_HOME>
        ~/.local/bin/uv venv --python 3.11 .venv-czsc
        ~/.local/bin/uv pip install --python .venv-czsc/bin/python czsc
    """
    venv_python = SKILL_HOME / ".venv-czsc" / "bin" / "python"

    def _health_check() -> bool:
        if not venv_python.exists():
            return False
        try:
            import subprocess
            proc = subprocess.run(
                [str(venv_python), "-c", "import czsc; print(czsc.__version__)"],
                capture_output=True, text=True, timeout=10,
            )
            return proc.returncode == 0 and bool(proc.stdout.strip())
        except Exception:
            return False

    if _health_check():
        return venv_python

    if not auto_install:
        return None

    # ============ v6.5 自启动 ============
    setup_sh = SKILL_HOME / "scripts" / "setup" / "auto_setup_czsc.sh"
    if not setup_sh.exists():
        print(f"  ⚠️  v6.5 自启动脚本缺失：{setup_sh}", file=sys.stderr)
        return None

    print("  🔧 v6.5 czsc 自启动：检测到 .venv-czsc 不可用，开始三级 fallback 安装...",
          file=sys.stderr)
    try:
        import subprocess
        proc = subprocess.run(
            ["bash", str(setup_sh)],
            capture_output=True, text=True, timeout=600,  # 10 分钟超时
        )
        if proc.stderr:
            for line in proc.stderr.splitlines():
                print(f"  {line}", file=sys.stderr)
        if proc.returncode == 0 and _health_check():
            print("  ✅ v6.5 czsc 自启动成功，缠论真值已可用", file=sys.stderr)
            return venv_python
        print(f"  ⚠️  v6.5 czsc 自启动失败（exit={proc.returncode}），fallback 到江恩位",
              file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("  ⚠️  v6.5 czsc 自启动超时（>10min），fallback 到江恩位", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️  v6.5 czsc 自启动异常：{e!r}", file=sys.stderr)
    return None


def run_czsc_analysis(ohlcv_df, ticker: str = "UNK", freq: str = "D") -> dict | None:
    """v6.4: 通过 .venv-czsc 子环境跑缠论真值分析。
    输入 OHLCV DataFrame（含 date/open/high/low/close 列），返回 czsc 标准 JSON。
    venv 不在 / 调用失败 → 返回 None，上层 fallback 到江恩位 + 0.382 回撤。

    输出 schema 见 scripts/calc/czsc_analyzer.py 文件头注释。
    """
    venv_python = _ensure_czsc_venv()
    if not venv_python:
        return None

    import subprocess
    from io import StringIO
    script_path = SKILL_HOME / "scripts" / "calc" / "czsc_analyzer.py"
    if not script_path.exists():
        return None

    # 准备 CSV
    df = ohlcv_df.copy()
    if "date" not in df.columns:
        # 兼容 akshare 中文列名（"日期"）
        if "日期" in df.columns:
            df = df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                                      "最高": "high", "最低": "low",
                                      "成交量": "volume", "成交额": "amount"})
        else:
            return None
    df["symbol"] = ticker
    df["freq"] = freq
    csv_str = df.to_csv(index=False)

    try:
        proc = subprocess.run(
            [str(venv_python), str(script_path)],
            input=csv_str, text=True, capture_output=True, timeout=30,
        )
        if proc.returncode != 0:
            print(f"  ⚠️  czsc 子环境调用失败 ({ticker}): {proc.stderr[:200]}", file=sys.stderr)
            return None
        result = json.loads(proc.stdout)
        if "error" in result:
            print(f"  ⚠️  czsc 分析报错 ({ticker}): {result['error'][:200]}", file=sys.stderr)
            return None
        return result
    except Exception as e:
        print(f"  ⚠️  czsc 调用异常 ({ticker}): {e!r:.200}", file=sys.stderr)
        return None


def run_multi_level_czsc(daily_df, weekly_df, ticker: str = "UNK") -> dict | None:
    """v6.4.4: 多级别缠论联动分析（日级 + 周级 + 共振判定）

    输入：
        daily_df  — 日 K 线 DataFrame（≥200 根日 K 推荐）
        weekly_df — 周 K 线 DataFrame（≥80 根周 K 推荐，约 1.5 年）
        ticker    — 标的代码

    输出 schema：
        {
          "daily":   {<czsc_analyzer 单级别 schema>},
          "weekly":  {<czsc_analyzer 单级别 schema>},
          "resonance": {
            "level_alignment": "强多" | "强空" | "日多周空" | "日空周多" | "中性",
            "weekly_zs_position": "在中枢内" | "在中枢上方" | "在中枢下方",
            "daily_pivot_3rd_in_weekly_context": "符合" | "逆势" | "中性",
            "verdict": "📈 强多共振" | "📉 强空共振" | "⚠️ 日级反抗周级" | "⚪ 不共振",
            "explanation": "<人类可读解释>"
          }
        }
    """
    daily = run_czsc_analysis(daily_df, ticker=ticker, freq="D")
    weekly = run_czsc_analysis(weekly_df, ticker=ticker, freq="W")
    if not daily or not weekly:
        return None
    return {
        "daily": daily,
        "weekly": weekly,
        "resonance": _judge_multi_level_resonance(daily, weekly, daily_df),
    }


def _judge_multi_level_resonance(daily: dict, weekly: dict, daily_df) -> dict:
    """v6.4.4: 日级 + 周级缠论共振判定"""
    # 1. 笔向对比
    daily_last = daily.get("last_bi") or {}
    weekly_last = weekly.get("last_bi") or {}
    daily_dir = daily_last.get("direction", "?")
    weekly_dir = weekly_last.get("direction", "?")

    # 2. 当前价（取日 K 最后一根 close）
    cur_price = float(daily_df["close"].iloc[-1]) if "close" in daily_df.columns else None

    # 3. 周级最新中枢位置
    weekly_zs = weekly.get("zs_list") or []
    last_w_zs = weekly_zs[-1] if weekly_zs else None
    weekly_zs_pos = "未识别"
    weekly_zs_str = "—"
    if last_w_zs and cur_price is not None:
        zg = last_w_zs.get("high")
        zd = last_w_zs.get("low")
        weekly_zs_str = f"[{zd:.3f}, {zg:.3f}]"
        if cur_price > zg:
            weekly_zs_pos = "在周中枢上方"
        elif cur_price < zd:
            weekly_zs_pos = "在周中枢下方"
        else:
            weekly_zs_pos = "在周中枢内"

    # 4. 日级三买/三卖 vs 周级方向是否一致
    daily_pivot = daily.get("pivot_3rd") or {}
    daily_pivot_type = daily_pivot.get("type", None)
    pivot_in_weekly_context = "中性"
    if daily_pivot_type and weekly_dir != "?":
        is_buy = "买" in str(daily_pivot_type)
        if is_buy and weekly_dir == "向上":
            pivot_in_weekly_context = "符合周级（顺势三买）"
        elif is_buy and weekly_dir == "向下":
            pivot_in_weekly_context = "逆势（小级反抗大级，胜率低）"
        elif (not is_buy) and weekly_dir == "向下":
            pivot_in_weekly_context = "符合周级（顺势三卖）"
        elif (not is_buy) and weekly_dir == "向上":
            pivot_in_weekly_context = "逆势（小级反抗大级，胜率低）"

    # 5. 综合判定
    if daily_dir == "向上" and weekly_dir == "向上":
        if weekly_zs_pos == "在周中枢上方":
            level_alignment = "强多"
            verdict = "📈 强多共振"
        else:
            level_alignment = "弱多"
            verdict = "📈 多头共振（周级中枢内/未确认）"
    elif daily_dir == "向下" and weekly_dir == "向下":
        if weekly_zs_pos == "在周中枢下方":
            level_alignment = "强空"
            verdict = "📉 强空共振"
        else:
            level_alignment = "弱空"
            verdict = "📉 空头共振（周级中枢内/未确认）"
    elif daily_dir == "向上" and weekly_dir == "向下":
        level_alignment = "日多周空"
        verdict = "⚠️ 日级反抗周级（小反大）"
    elif daily_dir == "向下" and weekly_dir == "向上":
        level_alignment = "日空周多"
        verdict = "⚠️ 日级反抗周级（小反大）"
    else:
        level_alignment = "中性"
        verdict = "⚪ 不共振"

    cur_price_str = f"{cur_price:.3f}" if cur_price is not None else "?"
    explanation = (
        f"日级最新笔 {daily_dir}（{daily_last.get('start_dt','-')}→{daily_last.get('end_dt','-')}），"
        f"周级最新笔 {weekly_dir}（{weekly_last.get('start_dt','-')}→{weekly_last.get('end_dt','-')}），"
        f"当前价 {cur_price_str} 处于 {weekly_zs_pos}（周级中枢 {weekly_zs_str}）。"
    )

    return {
        "level_alignment": level_alignment,
        "verdict": verdict,
        "daily_last_bi_direction": daily_dir,
        "weekly_last_bi_direction": weekly_dir,
        "weekly_zs_position": weekly_zs_pos,
        "weekly_zs": weekly_zs_str,
        "current_price": cur_price,
        "daily_pivot_3rd_type": daily_pivot_type,
        "daily_pivot_3rd_in_weekly_context": pivot_in_weekly_context,
        "explanation": explanation,
    }


# 默认 ticker 池（与 v6.1 collector 保持一致）
DEFAULT_ETF_TICKERS = [
    {"ticker": "510300", "name": "沪深300ETF", "type": "ETF"},
    {"ticker": "510050", "name": "上证50ETF", "type": "ETF"},
    {"ticker": "588000", "name": "科创50ETF", "type": "ETF"},
    {"ticker": "510500", "name": "中证500ETF", "type": "ETF"},
    {"ticker": "510880", "name": "红利ETF",   "type": "ETF"},
    {"ticker": "512890", "name": "红利低波ETF", "type": "ETF"},
]
DEFAULT_STOCK_TICKERS = [
    {"ticker": "600519", "name": "贵州茅台", "type": "STOCK"},
    {"ticker": "300750", "name": "宁德时代", "type": "STOCK"},
    {"ticker": "300308", "name": "中际旭创", "type": "STOCK"},
    {"ticker": "002241", "name": "歌尔股份", "type": "STOCK"},
    {"ticker": "002837", "name": "英维克",   "type": "STOCK"},
]

# stock/etf mode 跳过的步骤（节省时间）
MODE_STEPS = {
    "portfolio": {"structures", "scanner", "chip", "holdings", "macro", "finance"},
    "stock":     {"structures", "holdings", "macro", "finance"},
    "etf":       {"structures", "scanner", "chip", "holdings", "macro"},
    "macro":     {"holdings", "macro"},
}


def _peers_from_industry_yaml(target_ticker: str) -> list[str]:
    """从 references/industry_peers.yaml 推导同行 ticker。仅在 stock mode 用。"""
    yaml_path = SKILL_HOME / "references" / "industry_peers.yaml"
    if not yaml_path.exists():
        return []
    try:
        import yaml  # type: ignore
        cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  industry_peers.yaml 读失败：{e}", file=sys.stderr)
        return []
    ticker_to_group = cfg.get("ticker_to_group", {}) or {}
    group = ticker_to_group.get(target_ticker)
    if not group:
        return []
    grp_def = (cfg.get(group) or {}).get("members", [])
    peers = [t for t in grp_def if t != target_ticker]
    return peers[:5]  # 至多 5 个 peer


def _build_ticker_pool(mode: str, target: str | None, peers: list[str], extra_tickers: list[str]) -> list[dict]:
    """根据 mode 构建本次采集要跑的 ticker 池"""
    if mode == "macro":
        return []
    if mode == "stock":
        if not target:
            raise ValueError("stock mode 必须指定 --target")
        # peers 自动补全
        if not peers:
            peers = _peers_from_industry_yaml(target)
        all_codes = [target] + peers
        return [{"ticker": c, "name": c, "type": "STOCK"} for c in all_codes]
    if mode == "etf":
        if not target:
            raise ValueError("etf mode 必须指定 --target")
        return [{"ticker": target, "name": target, "type": "ETF"}]
    # portfolio
    if extra_tickers:
        # extra_tickers 覆盖默认池（按代码长度智能识别 ETF/STOCK）
        out = []
        for c in extra_tickers:
            tt = "ETF" if c.startswith(("5", "1")) else "STOCK"
            out.append({"ticker": c, "name": c, "type": tt})
        return out
    return DEFAULT_ETF_TICKERS + DEFAULT_STOCK_TICKERS


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="v6.2 skill agent 数据采集入口")
    parser.add_argument("--date", default=None, help="ISO 日期，默认今日")
    parser.add_argument("--mode", choices=list(MODE_STEPS.keys()), default="portfolio",
                        help="采集模式（默认 portfolio）")
    parser.add_argument("--target", default=None, help="stock/etf 模式必需：目标 ticker")
    parser.add_argument("--peers", default="", help="stock 模式：逗号分隔同行（可选；空则自动从 industry_peers.yaml 推）")
    parser.add_argument("--tickers", default="", help="portfolio 模式：覆盖默认池（逗号分隔）")
    parser.add_argument("--no-finance", action="store_true", help="跳过财务（仅缠论 + holdings）")
    parser.add_argument("--no-macro", action="store_true", help="跳过宏观")
    args = parser.parse_args()

    today = args.date or Date.today().isoformat()
    mode = args.mode
    target = args.target
    peers = [p.strip() for p in args.peers.split(",") if p.strip()]
    extra = [t.strip() for t in args.tickers.split(",") if t.strip()]

    # v6.3 P0 修复前置：每次启动都跑（幂等）
    print(f"🔧 v6.3 启动前置：trading.db init + holdings sync ...")
    _ensure_trading_db()
    _ensure_holdings_imported(today)

    pool = _build_ticker_pool(mode, target, peers, extra)
    steps = set(MODE_STEPS[mode])
    if args.no_finance:
        steps.discard("finance")
    if args.no_macro:
        steps.discard("macro")

    print(f"🌱 v6.3 prepare_data | date={today} | mode={mode}")
    if mode == "stock":
        print(f"   target={target}  peers={peers or '(auto)'}")
    print(f"   tickers={[t['ticker'] for t in pool]}")
    print(f"   steps={sorted(steps)}")
    print(f"   skill_home={SKILL_HOME}")

    paths: dict[str, Path] = {}
    t_start = time.time()

    # 1. structures
    if "structures" in steps and pool:
        print(f"\n[structures] 跑缠论引擎 ...")
        tickers_dict = collect_structures_for_tickers(today, pool)
        # v6.2: schema 与 bot collector 一致（顶层 date/generated_by/tickers）
        structures = {
            "date": today,
            "generated_by": "v6.2 prepare_data.py [agent CLI]",
            "tickers": tickers_dict,
        }
        p = DATA_DIR / "structures" / f"structures_{today}.json"
        _write_json(p, structures)
        paths["structures"] = p
        print(f"  ✓ {p.relative_to(SKILL_HOME) if SKILL_HOME in p.parents else p}  ({len(tickers_dict)} ticker)")

    # 2. scanner（仅 portfolio）
    if "scanner" in steps and pool:
        print(f"\n[scanner] 全市场扫描 ...")
        try:
            sys.path.insert(0, str(SKILL_HOME / "mattermost-bot" / "scripts"))
            from real_data_collector import collect_scanner  # type: ignore
            scanner = collect_scanner(today, pool)
            p = DATA_DIR / "scanner" / f"scanner_{today}.json"
            _write_json(p, scanner)
            paths["scanner"] = p
            print(f"  ✓ {p.name}")
        except ImportError:
            print(f"  ⚠️  scanner 模块未抽离到 scripts/data，本次跳过（v6.3 重构计划内）")

    # 3. chip（仅 portfolio/etf）
    if "chip" in steps:
        print(f"\n[chip] ETF 国家队筹码 ...")
        try:
            sys.path.insert(0, str(SKILL_HOME / "mattermost-bot" / "scripts"))
            from real_data_collector import collect_chip_analysis  # type: ignore
            chip = collect_chip_analysis(today)
            p = DATA_DIR / "chip" / f"chip_analysis_{today}.json"
            _write_json(p, chip)
            paths["chip"] = p
            print(f"  ✓ {p.name}")
        except ImportError:
            print(f"  ⚠️  chip 模块未抽离到 scripts/data，本次跳过")

    # 4. holdings（read-only 校验）
    if "holdings" in steps:
        from data.holdings_loader import load_holdings
        h = load_holdings(today)
        if h:
            print(f"\n[holdings] ✓ holdings_latest.json (read-only)")
        else:
            print(f"\n[holdings] ⚠️  无 holdings_latest.json（首次使用？）")

    # 5. macro
    if "macro" in steps:
        print(f"\n[macro] 宏观指标 ...")
        try:
            sys.path.insert(0, str(SKILL_HOME / "mattermost-bot" / "scripts"))
            from real_data_collector import collect_macro_indicators  # type: ignore
            macro = collect_macro_indicators(today)
            p = DATA_DIR / "macro" / "macro_indicators.json"
            _write_json(p, macro)
            paths["macro"] = p
            print(f"  ✓ {p.name}")
        except ImportError:
            print(f"  ⚠️  macro 模块未抽离到 scripts/data，本次跳过")

    # 6. finance（颜值评分原料）
    if "finance" in steps and pool:
        print(f"\n[finance] 财务指标 ...")
        ticker_codes = [t["ticker"] for t in pool if t.get("type") == "STOCK"]
        if ticker_codes:
            finance = collect_finance_for_tickers(ticker_codes, today)
            p = DATA_DIR / "finance" / f"finance_{today}.json"
            _write_json(p, finance)
            paths["finance"] = p
            print(f"  ✓ {p.name}  ({len(finance.get('tickers', {}))} ticker)")

    elapsed = time.time() - t_start
    print(f"\n✅ v6.2 prepare_data 完成 | mode={mode} | {len(paths)}/{len(steps)} 类输出 | {elapsed:.1f}s")
    if paths.get("structures"):
        print(f"   下一步：python3 scripts/calc/beauty_score.py --tickers {' '.join([t['ticker'] for t in pool if t.get('type')=='STOCK'])} --protocol auto")


if __name__ == "__main__":
    try:
        main()
    except DataCollectionError as e:
        print(f"❌ 数据采集失败：{e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 未预期错误：{e}", file=sys.stderr)
        sys.exit(2)
