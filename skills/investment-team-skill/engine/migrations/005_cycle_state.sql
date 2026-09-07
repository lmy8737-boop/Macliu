-- 005_cycle_state.sql
-- v5.0 Mattermost 群升级 - 群聊形态新增表
--
-- 设计原则：
--   - 不动 v4.7 已有的 review_log / audit_log
--   - cycle_state 是"主流程状态机"持久化（重启恢复用）
--   - message_log 是"群里所有 bot 发言历史"（rolling window 重建用 + 月报溯源用）
--
-- 与 review_log/audit_log 的关联：
--   - cycle_state.cycle_id 自增主键
--   - review_log/audit_log 通过 cycle_state.cycle_id 反查（view 已附）
--   - message_log.review_id / audit_id FK 反查具体一条群消息触发了哪次审核

CREATE TABLE IF NOT EXISTS cycle_state (
    cycle_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TIMESTAMP NOT NULL,
    started_by       TEXT NOT NULL,                    -- foreman / user_id
    initial_prompt   TEXT,                             -- 用户那句"开盘前讨论..."
    channel_id       TEXT NOT NULL,
    phase            TEXT NOT NULL,                    -- PHASE_1 / PHASE_2 / ... / PHASE_6 / DONE / ABORTED
    current_role     TEXT,                             -- 1-7 / null（并行阶段）
    retry_count      INTEGER DEFAULT 0,                -- 当前角色返工次数
    pending_audits   TEXT,                             -- JSON：{buzzword: PASS, data_verify: PENDING, ...}
    last_review_id   INTEGER,                          -- 最近一次 5 号 review_log.review_id
    status           TEXT DEFAULT 'RUNNING',           -- RUNNING / WAITING_USER / DONE / ABORTED
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at     TIMESTAMP,
    notes            TEXT,
    FOREIGN KEY (last_review_id) REFERENCES review_log(review_id)
);

CREATE INDEX IF NOT EXISTS idx_cycle_state_status   ON cycle_state(status);
CREATE INDEX IF NOT EXISTS idx_cycle_state_started  ON cycle_state(started_at);

-- 群里所有发言历史（含 bot 与用户）
CREATE TABLE IF NOT EXISTS message_log (
    msg_id           TEXT PRIMARY KEY,                 -- Mattermost post.id
    cycle_id         INTEGER,                          -- 所属 cycle（非主流程消息可空）
    channel_id       TEXT NOT NULL,
    role_id          TEXT,                             -- 1-7 / foreman / human / null
    user_id          TEXT NOT NULL,                    -- Mattermost user_id
    sent_at          TIMESTAMP NOT NULL,
    raw_text         TEXT,                             -- 文本部分
    card_payload     TEXT,                             -- attachment JSON（如有）
    msg_type         TEXT NOT NULL,                    -- AGENT_OUTPUT / FOREMAN_NOTICE / USER_MENTION / SYSTEM
    parent_msg_id    TEXT,                             -- thread root（追问场景）
    review_id        INTEGER,                          -- 关联 review_log
    audit_id         INTEGER,                          -- 关联 audit_log
    persona_segment  INTEGER DEFAULT 0,                -- 长消息分段时第几段
    persona_total    INTEGER DEFAULT 1,                -- 长消息分段总数
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cycle_id) REFERENCES cycle_state(cycle_id),
    FOREIGN KEY (review_id) REFERENCES review_log(review_id),
    FOREIGN KEY (audit_id) REFERENCES audit_log(audit_id)
);

CREATE INDEX IF NOT EXISTS idx_message_log_cycle    ON message_log(cycle_id);
CREATE INDEX IF NOT EXISTS idx_message_log_role     ON message_log(role_id);
CREATE INDEX IF NOT EXISTS idx_message_log_sent     ON message_log(sent_at);
CREATE INDEX IF NOT EXISTS idx_message_log_channel  ON message_log(channel_id);

-- 月度榜状态记忆（开机时检查上次发月报日期）
CREATE TABLE IF NOT EXISTS monthly_report_log (
    report_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    report_month     TEXT NOT NULL UNIQUE,             -- "2026-05"
    sent_at          TIMESTAMP NOT NULL,
    sent_msg_id      TEXT,                             -- 6 号发到群里的那条 msg_id
    payload          TEXT                              -- get_laziness_report 的 JSON
);

-- 便利视图：把 cycle 串起 review/audit
CREATE VIEW IF NOT EXISTS v_cycle_review_audit AS
SELECT
    c.cycle_id,
    c.started_at,
    c.phase,
    c.status,
    r.review_id,
    r.target_role,
    r.status AS review_status,
    r.reject_type,
    r.final_status,
    a.audit_id,
    a.script_name,
    a.verdict
FROM cycle_state c
LEFT JOIN review_log r ON r.review_id = c.last_review_id
LEFT JOIN audit_log  a ON a.review_id = r.review_id;
