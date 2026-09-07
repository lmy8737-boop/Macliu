"""
SQLite 信号库初始化
- signals: 4号每条信号必须落库
- settlements: 3号 T+N 回填实际盈亏
- holdings_snapshot: 每日盘前持仓快照
- review_log: 5号审核记录（PASS/REJECT/FORCED_PASS）
- risk_events: 风控事件流水
- audit_log: v4.7 反偷懒机器审计记录（buzzword/data_verify/independence/semantic_diff/supervisor_self_check）
- cycle_state: v5.0 群聊主流程状态机持久化（重启恢复用）
- message_log: v5.0 群里所有 bot/用户发言历史（rolling window 重建用）
- monthly_report_log: v5.0 月度偷懒榜发送记忆（开机补发判断）
- agent_thought_log: v6.0 完整 LLM 思考链记录（群里只发精简消息，思考链落库）

数据库路径：环境变量 INVESTMENT_TEAM_DB（默认 ./engine/data/trading.db）
"""
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get(
    "INVESTMENT_TEAM_DB",
    Path.cwd() / "engine" / "data" / "trading.db"
))

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id        TEXT PRIMARY KEY,
    issued_at        TIMESTAMP NOT NULL,
    issued_date      DATE NOT NULL,
    ticker           TEXT NOT NULL,
    market           TEXT NOT NULL,
    direction        TEXT NOT NULL,
    signal_type      TEXT NOT NULL,
    strength         INTEGER NOT NULL,
    entry_price      REAL NOT NULL,
    stop_loss        REAL NOT NULL,
    take_profit_1    REAL,
    take_profit_2    REAL,
    position_pct     REAL NOT NULL,
    reasoning_json   TEXT,
    macro_aligned    INTEGER,
    industry_aligned INTEGER,
    status           TEXT DEFAULT 'OPEN',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(issued_date);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);

CREATE TABLE IF NOT EXISTS settlements (
    settlement_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id        TEXT NOT NULL,
    settled_at       TIMESTAMP NOT NULL,
    settle_horizon   TEXT NOT NULL,
    actual_close     REAL NOT NULL,
    pnl_pct          REAL NOT NULL,
    is_win           INTEGER NOT NULL,
    hit_stop_loss    INTEGER DEFAULT 0,
    hit_take_profit  INTEGER DEFAULT 0,
    notes            TEXT,
    FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
);

CREATE INDEX IF NOT EXISTS idx_settlements_signal ON settlements(signal_id);

CREATE TABLE IF NOT EXISTS holdings_snapshot (
    snapshot_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date    DATE NOT NULL,
    ticker           TEXT NOT NULL,
    market           TEXT NOT NULL,
    weight_pct       REAL NOT NULL,
    cost_price       REAL,
    current_price    REAL,
    profit_pct       REAL,
    industry         TEXT,
    UNIQUE(snapshot_date, ticker)
);

CREATE TABLE IF NOT EXISTS risk_events (
    event_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date       DATE NOT NULL,
    event_type       TEXT NOT NULL,
    severity         TEXT NOT NULL,
    related_signal   TEXT,
    description      TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_log (
    review_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    review_date      DATE NOT NULL,
    target_role      TEXT NOT NULL,
    target_artifact  TEXT NOT NULL,
    status           TEXT NOT NULL,
    reject_reason    TEXT,
    retry_count      INTEGER DEFAULT 0,
    final_status     TEXT,
    reject_type      TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- v4.7: 反偷懒机器审计记录
-- 一次 review 可产生 4-5 行 audit（4 检测脚本 + supervisor_self_check）
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id        INTEGER,
    script_name      TEXT NOT NULL,
    target_role      TEXT NOT NULL,
    target_artifact  TEXT,
    verdict          TEXT NOT NULL,
    detail_json      TEXT,
    audit_date       DATE NOT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (review_id) REFERENCES review_log(review_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_log_date    ON audit_log(audit_date);
CREATE INDEX IF NOT EXISTS idx_audit_log_role    ON audit_log(target_role);
CREATE INDEX IF NOT EXISTS idx_audit_log_script  ON audit_log(script_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_verdict ON audit_log(verdict);
CREATE INDEX IF NOT EXISTS idx_audit_log_review  ON audit_log(review_id);

-- v5.0: 群聊主流程状态机（重启恢复）
CREATE TABLE IF NOT EXISTS cycle_state (
    cycle_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TIMESTAMP NOT NULL,
    started_by       TEXT NOT NULL,
    initial_prompt   TEXT,
    channel_id       TEXT NOT NULL,
    phase            TEXT NOT NULL,
    current_role     TEXT,
    retry_count      INTEGER DEFAULT 0,
    pending_audits   TEXT,
    last_review_id   INTEGER,
    status           TEXT DEFAULT 'RUNNING',
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at     TIMESTAMP,
    notes            TEXT,
    FOREIGN KEY (last_review_id) REFERENCES review_log(review_id)
);

CREATE INDEX IF NOT EXISTS idx_cycle_state_status   ON cycle_state(status);
CREATE INDEX IF NOT EXISTS idx_cycle_state_started  ON cycle_state(started_at);

-- v5.0: 群里所有发言历史
CREATE TABLE IF NOT EXISTS message_log (
    msg_id           TEXT PRIMARY KEY,
    cycle_id         INTEGER,
    channel_id       TEXT NOT NULL,
    role_id          TEXT,
    user_id          TEXT NOT NULL,
    sent_at          TIMESTAMP NOT NULL,
    raw_text         TEXT,
    card_payload     TEXT,
    msg_type         TEXT NOT NULL,
    parent_msg_id    TEXT,
    review_id        INTEGER,
    audit_id         INTEGER,
    persona_segment  INTEGER DEFAULT 0,
    persona_total    INTEGER DEFAULT 1,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cycle_id) REFERENCES cycle_state(cycle_id),
    FOREIGN KEY (review_id) REFERENCES review_log(review_id),
    FOREIGN KEY (audit_id) REFERENCES audit_log(audit_id)
);

CREATE INDEX IF NOT EXISTS idx_message_log_cycle    ON message_log(cycle_id);
CREATE INDEX IF NOT EXISTS idx_message_log_role     ON message_log(role_id);
CREATE INDEX IF NOT EXISTS idx_message_log_sent     ON message_log(sent_at);
CREATE INDEX IF NOT EXISTS idx_message_log_channel  ON message_log(channel_id);

-- v5.0: 月度榜发送记忆
CREATE TABLE IF NOT EXISTS monthly_report_log (
    report_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    report_month     TEXT NOT NULL UNIQUE,
    sent_at          TIMESTAMP NOT NULL,
    sent_msg_id      TEXT,
    payload          TEXT
);

-- v6.0: 完整 LLM 思考链记录
-- 群里只发 ≤150 字精简消息（[CHAT_REPLY] 区块），完整思考（[THOUGHT_LOG] 区块）落入此表
-- 关联：每条 message_log（AGENT_OUTPUT 类型）应有对应 thought_log 行
CREATE TABLE IF NOT EXISTS agent_thought_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id           INTEGER REFERENCES cycle_state(cycle_id),
    role_id            TEXT NOT NULL,
    thought_type       TEXT,
    full_chain         TEXT NOT NULL,
    chat_reply_summary TEXT,
    summary_msg_id     TEXT,
    char_count_full    INTEGER,
    char_count_summary INTEGER,
    extras_json        TEXT,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_thought_log_cycle ON agent_thought_log(cycle_id);
CREATE INDEX IF NOT EXISTS idx_thought_log_role ON agent_thought_log(role_id);
CREATE INDEX IF NOT EXISTS idx_thought_log_msg ON agent_thought_log(summary_msg_id);
CREATE INDEX IF NOT EXISTS idx_thought_log_created ON agent_thought_log(created_at DESC);
"""


def init_db():
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    print(f"✅ 信号库初始化: {DB_PATH}")
    
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f"📋 已创建表: {[t[0] for t in tables]}")
    conn.close()


if __name__ == "__main__":
    init_db()
