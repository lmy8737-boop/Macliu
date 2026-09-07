-- v6.0 Mattermost 群升级 - 思考链记录表
-- 群里只发 ≤150 字精简消息，完整思考链落入此表
-- 关联：每条 message_log（AGENT_OUTPUT 类型）应有对应 thought_log 行

CREATE TABLE IF NOT EXISTS agent_thought_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER REFERENCES cycle_state(cycle_id),
    role_id TEXT NOT NULL,             -- 1-7 / foreman
    thought_type TEXT,                 -- reasoning / data_lookup / decision_chain / rework
    full_chain TEXT NOT NULL,          -- 完整 LLM 思考链（[THOUGHT_LOG] 区块原文）
    chat_reply_summary TEXT,           -- 对应群里发的精简消息（[CHAT_REPLY] 区块）
    summary_msg_id TEXT,               -- 关联到 message_log.msg_id（mm post_id）
    char_count_full INTEGER,           -- 完整思考字数
    char_count_summary INTEGER,        -- 精简消息字数（应 ≤150）
    extras_json TEXT,                  -- 卡片 payload / 额外结构化数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_thought_log_cycle ON agent_thought_log(cycle_id);
CREATE INDEX IF NOT EXISTS idx_thought_log_role ON agent_thought_log(role_id);
CREATE INDEX IF NOT EXISTS idx_thought_log_msg ON agent_thought_log(summary_msg_id);
CREATE INDEX IF NOT EXISTS idx_thought_log_created ON agent_thought_log(created_at DESC);

-- 反偷懒：思考链长度不能为 0（无思考的 AGENT_OUTPUT 视作偷懒）
-- 在 5 号 audit 链补加：thought_log.char_count_full < 100 → 警告
