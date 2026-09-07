-- 004_audit_log.sql
-- v4.7 反偷懒机器化兜底 - audit_log 表
--
-- 设计：一次 5 号 review 产 4-5 行 audit（buzzword/data_verify/independence/semantic_diff/supervisor_self_check）
-- 不动 review_log，通过 review_id 外键关联
--
-- 使用：scripts/audit/*.py 写入；scripts/router/review_router.py --monthly-report 读取聚合

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id        INTEGER,                            -- FK → review_log.review_id（可为空：脚本独立运行时）
    script_name      TEXT NOT NULL,                      -- buzzword | data_verify | independence | semantic_diff | supervisor_self_check
    target_role      TEXT NOT NULL,                      -- 1 | 2 | 3 | 4 | 5
    target_artifact  TEXT,                               -- 被审核的文件路径
    verdict          TEXT NOT NULL,                      -- PASS | FAIL | SOFT_FAIL
    detail_json      TEXT,                               -- 完整脚本输出 JSON（含命中位置、数据点、相似度等）
    audit_date       DATE NOT NULL,                      -- 审计日期，便于月度聚合
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (review_id) REFERENCES review_log(review_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_log_date     ON audit_log(audit_date);
CREATE INDEX IF NOT EXISTS idx_audit_log_role     ON audit_log(target_role);
CREATE INDEX IF NOT EXISTS idx_audit_log_script   ON audit_log(script_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_verdict  ON audit_log(verdict);
CREATE INDEX IF NOT EXISTS idx_audit_log_review   ON audit_log(review_id);
