-- ========================================================
-- 投资团队持仓 MySQL Schema（脱敏版，含同日期去重）
-- 用法：导入到任意 MySQL 实例的目标库
-- ========================================================

-- 1. 建库（如不存在）
-- CREATE DATABASE IF NOT EXISTS quantitative
--     DEFAULT CHARACTER SET utf8mb4
--     DEFAULT COLLATE utf8mb4_unicode_ci;
-- USE quantitative;

-- 2. 持仓日表（核心：UNIQUE KEY 实现同日期去重）
CREATE TABLE IF NOT EXISTS holdings_daily (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    snapshot_date   DATE NOT NULL                    COMMENT '快照日期',
    ticker          VARCHAR(32) NOT NULL              COMMENT '标的代码',
    name            VARCHAR(64) NOT NULL DEFAULT ''   COMMENT '标的名称',
    market          VARCHAR(8)  NOT NULL DEFAULT 'A'  COMMENT '市场: A/HK/US',
    industry        VARCHAR(64) NOT NULL DEFAULT '未分类' COMMENT '行业',
    weight_pct      DECIMAL(8,4) NOT NULL             COMMENT '仓位占比%',
    quantity        DECIMAL(20,4) DEFAULT NULL        COMMENT '持有数量',
    cost_price      DECIMAL(20,4) DEFAULT NULL        COMMENT '成本价',
    current_price   DECIMAL(20,4) DEFAULT NULL        COMMENT '当前价',
    market_value    DECIMAL(20,4) DEFAULT NULL        COMMENT '市值',
    profit_pct      DECIMAL(10,4) DEFAULT NULL        COMMENT '浮动盈亏%',
    profit_amount   DECIMAL(20,4) DEFAULT NULL        COMMENT '浮动盈亏金额',
    source          VARCHAR(32) NOT NULL DEFAULT 'manual' COMMENT '数据来源',
    source_url      VARCHAR(512) DEFAULT NULL,
    raw_payload     JSON DEFAULT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_date_ticker (snapshot_date, ticker)  COMMENT '同日期去重核心',
    KEY idx_date (snapshot_date),
    KEY idx_ticker (ticker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='持仓日表';

-- 3. 同步日志
CREATE TABLE IF NOT EXISTS holdings_sync_log (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sync_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    snapshot_date   DATE NOT NULL,
    source          VARCHAR(32) NOT NULL,
    rows_inserted   INT UNSIGNED DEFAULT 0,
    rows_updated    INT UNSIGNED DEFAULT 0,
    rows_skipped    INT UNSIGNED DEFAULT 0,
    total_weight    DECIMAL(8,4),
    risk_warnings   TEXT,
    status          ENUM('SUCCESS','PARTIAL','FAILED') DEFAULT 'SUCCESS',
    PRIMARY KEY (id),
    KEY idx_sync_date (snapshot_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='持仓同步日志';

-- ========================================================
-- 常用查询
-- ========================================================

-- 最新一天的持仓
-- SELECT * FROM holdings_daily 
-- WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM holdings_daily)
-- ORDER BY weight_pct DESC;

-- 单标的历史变化
-- SELECT snapshot_date, weight_pct, current_price, profit_pct
-- FROM holdings_daily WHERE ticker = ?
-- ORDER BY snapshot_date DESC LIMIT 30;

-- 行业集中度
-- SELECT snapshot_date, industry, SUM(weight_pct) AS w
-- FROM holdings_daily GROUP BY snapshot_date, industry
-- ORDER BY snapshot_date DESC, w DESC;
