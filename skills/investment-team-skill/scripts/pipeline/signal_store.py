"""
信号库管理器 - 4号交易员调用此API登记信号

核心原则：
- 所有信号必须经过此 API 落库（不允许只写 Markdown）
- API 内置硬性风控：仓位>7%、缺止损、方向矛盾 → 直接 ValueError 拒绝
- 提供 get_win_rate() 给5号做客观考核
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get(
    "INVESTMENT_TEAM_DB",
    Path.cwd() / "engine" / "data" / "trading.db"
))


def submit_signal(
    ticker, market, direction, signal_type, strength,
    entry_price, stop_loss, take_profit_1=None, take_profit_2=None,
    position_pct=0.03, reasoning=None,
    macro_aligned=True, industry_aligned=True
):
    """
    4号交易员调用此函数登记信号。
    返回 signal_id，可用于追踪结算。
    """
    signal_id = f"SIG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    now = datetime.now()
    
    # 强制风控前置校验
    if position_pct > 0.07:
        raise ValueError(f"❌ 仓位 {position_pct*100:.2f}% 超过 7% 红线，信号拒绝")
    if stop_loss is None or stop_loss == 0:
        raise ValueError("❌ 必须设置止损位")
    if direction == "LONG" and stop_loss >= entry_price:
        raise ValueError(f"❌ 多单止损位 {stop_loss} 必须低于入场价 {entry_price}")
    if direction == "SHORT" and stop_loss <= entry_price:
        raise ValueError(f"❌ 空单止损位 {stop_loss} 必须高于入场价 {entry_price}")
    if strength < 3:
        raise ValueError(f"❌ 信号强度 {strength} < 3，不予输出")
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO signals (
            signal_id, issued_at, issued_date, ticker, market, direction,
            signal_type, strength, entry_price, stop_loss,
            take_profit_1, take_profit_2, position_pct,
            reasoning_json, macro_aligned, industry_aligned
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        signal_id, now, now.date(), ticker, market, direction,
        signal_type, strength, entry_price, stop_loss,
        take_profit_1, take_profit_2, position_pct,
        json.dumps(reasoning, ensure_ascii=False) if reasoning else None,
        1 if macro_aligned else 0,
        1 if industry_aligned else 0,
    ))
    conn.commit()
    conn.close()
    
    return signal_id


def list_pending_signals(horizon_days=3):
    """返回需要在今日做结算的信号列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM signals
        WHERE status = 'OPEN'
          AND date(issued_date, '+' || ? || ' day') <= date('now')
        ORDER BY issued_date
    """, (horizon_days,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_win_rate(window_days=30):
    """近 N 天的实际胜率统计 - 5号考核 4号的客观依据"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute("""
        SELECT 
            COUNT(*) as total_signals,
            SUM(CASE WHEN s.is_win=1 THEN 1 ELSE 0 END) as wins,
            AVG(s.pnl_pct) as avg_pnl,
            AVG(CASE WHEN s.is_win=1 THEN s.pnl_pct END) as avg_win_pnl,
            AVG(CASE WHEN s.is_win=0 THEN s.pnl_pct END) as avg_loss_pnl
        FROM settlements s
        JOIN signals sig ON s.signal_id = sig.signal_id
        WHERE date(sig.issued_date) >= date('now', '-' || ? || ' day')
    """, (window_days,)).fetchone()
    
    total = rows["total_signals"] or 0
    wins = rows["wins"] or 0
    win_rate = (wins / total * 100) if total > 0 else 0
    avg_win = rows["avg_win_pnl"] or 0
    avg_loss = rows["avg_loss_pnl"] or 0
    profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss < 0 else None
    
    conn.close()
    return {
        "window_days": window_days,
        "total_signals": total,
        "wins": wins,
        "win_rate_pct": round(win_rate, 2),
        "avg_pnl_pct": round(rows["avg_pnl"] or 0, 2),
        "avg_win_pnl_pct": round(avg_win, 2),
        "avg_loss_pnl_pct": round(avg_loss, 2),
        "profit_loss_ratio": round(profit_loss_ratio, 2) if profit_loss_ratio else None,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--win-rate":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        print(json.dumps(get_win_rate(days), ensure_ascii=False, indent=2))
    else:
        print("用法: python signal_store.py --win-rate 30")
