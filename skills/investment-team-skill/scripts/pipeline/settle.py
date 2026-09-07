"""
T+N 自动结算器 - 3号每日盘后调用
读取 OPEN 状态信号 → 拉取 T+N 真实收盘价 → 计算盈亏 → 回填 settlements 表

使用 westock-data CLI 拉取实际收盘价（也可改成其他数据源）
"""
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, date
from pathlib import Path

DB_PATH = Path(os.environ.get(
    "INVESTMENT_TEAM_DB",
    Path.cwd() / "engine" / "data" / "trading.db"
))

HORIZONS = [3, 5, 10]  # 结算横线
COMMISSION_PCT = 0.2   # 假设双边手续费 0.2%


def fetch_close_price(ticker, target_date):
    """用 westock-data 拉取目标日期附近的收盘价"""
    try:
        result = subprocess.run(
            ["npx", "-y", "westock-data-clawhub@1.0.4",
             "kline", ticker, "--period", "day", "--limit", "30"],
            capture_output=True, text=True, timeout=60
        )
        lines = result.stdout.strip().split("\n")
        for line in lines[2:]:
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if len(cols) >= 6 and cols[0] == target_date:
                return {
                    "date": cols[0],
                    "open": float(cols[1]),
                    "close": float(cols[2]),
                    "high": float(cols[3]),
                    "low": float(cols[4]),
                }
        return None
    except Exception as e:
        print(f"⚠️ 拉取 {ticker} {target_date} 失败: {e}")
        return None


def calc_settlement(signal, kline):
    """计算单条信号的盈亏"""
    direction = signal["direction"]
    entry = signal["entry_price"]
    stop = signal["stop_loss"]
    tp1 = signal.get("take_profit_1")
    
    period_low = kline["low"]
    period_high = kline["high"]
    final_close = kline["close"]
    
    hit_stop_loss = 0
    hit_take_profit = 0
    actual_exit = final_close
    
    if direction == "LONG":
        if period_low <= stop:
            hit_stop_loss = 1
            actual_exit = stop
        elif tp1 and period_high >= tp1:
            hit_take_profit = 1
            actual_exit = tp1
        pnl_pct = (actual_exit - entry) / entry * 100
    else:
        if period_high >= stop:
            hit_stop_loss = 1
            actual_exit = stop
        elif tp1 and period_low <= tp1:
            hit_take_profit = 1
            actual_exit = tp1
        pnl_pct = (entry - actual_exit) / entry * 100
    
    pnl_pct -= COMMISSION_PCT
    
    return {
        "actual_close": final_close,
        "pnl_pct": round(pnl_pct, 2),
        "is_win": 1 if pnl_pct > 0 else 0,
        "hit_stop_loss": hit_stop_loss,
        "hit_take_profit": hit_take_profit,
    }


def settle_all():
    """主流程：扫描所有需要结算的信号，逐个回填"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    settled_count = 0
    
    for horizon in HORIZONS:
        target_date = (date.today() - timedelta(days=horizon)).isoformat()
        
        signals = conn.execute("""
            SELECT * FROM signals
            WHERE status = 'OPEN'
              AND issued_date = ?
              AND signal_id NOT IN (
                  SELECT signal_id FROM settlements 
                  WHERE settle_horizon = ?
              )
        """, (target_date, f"T+{horizon}")).fetchall()
        
        for sig in signals:
            sig = dict(sig)
            print(f"🔍 结算 {sig['signal_id']} | {sig['ticker']} | T+{horizon}")
            
            kline = fetch_close_price(sig["ticker"], date.today().isoformat())
            if not kline:
                print(f"   ⚠️ 无法拉取 {sig['ticker']} 今日K线，跳过")
                continue
            
            result = calc_settlement(sig, kline)
            
            conn.execute("""
                INSERT INTO settlements 
                (signal_id, settled_at, settle_horizon, actual_close, pnl_pct, is_win, hit_stop_loss, hit_take_profit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sig["signal_id"], datetime.now(), f"T+{horizon}",
                result["actual_close"], result["pnl_pct"], result["is_win"],
                result["hit_stop_loss"], result["hit_take_profit"]
            ))
            
            if horizon == 10:
                conn.execute(
                    "UPDATE signals SET status='CLOSED' WHERE signal_id=?",
                    (sig["signal_id"],)
                )
            
            settled_count += 1
            status_emoji = "✅ 盈" if result["is_win"] else "❌ 亏"
            print(f"   {status_emoji} {result['pnl_pct']:+.2f}%")
    
    conn.commit()
    conn.close()
    print(f"\n📊 本次结算 {settled_count} 条信号")


if __name__ == "__main__":
    print(f"🕐 启动结算 - {datetime.now()}")
    settle_all()
