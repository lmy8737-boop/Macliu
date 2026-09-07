# 投资团队角色考核与推荐回溯机制

## 1. 核心原则

**每个角色的每次推荐都要"负责到底"**。不是给完建议就走人，T+7/T+14/T+30 要回来对账。

---

## 2. 推荐责任登记表

每次运行时，所有输出建议**强制登记**到 `engine/data/recommendations.db`（SQLite）：

```sql
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issued_date TEXT NOT NULL,           -- 发出日期
    role_id INTEGER NOT NULL,            -- 1-6号
    role_name TEXT NOT NULL,             -- 角色中文名
    recommendation TEXT NOT NULL,        -- 具体建议内容
    ticker TEXT,                         -- 相关标的（可空）
    direction TEXT,                      -- BUY/SELL/HOLD/配置调整
    target_price REAL,                   -- 目标价（如有）
    stop_loss REAL,                      -- 止损位（如有）
    confidence TEXT,                     -- 置信度（高/中/低）
    status TEXT DEFAULT 'OPEN',          -- OPEN/HIT/MISS/EXPIRED
    review_t7 TEXT,                      -- T+7 回溯评价
    review_t14 TEXT,                     -- T+14 回溯评价
    review_t30 TEXT,                     -- T+30 回溯评价
    actual_result TEXT,                  -- 实际结果
    pnl_pct REAL,                       -- 实际盈亏%
    score INTEGER,                      -- 打分 1-10
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 3. 回溯考核机制

### 自动触发（Automation / Cron）
- **T+7**（1周后）：3号自动拉取推荐标的最新价格，计算盈亏，填入 `review_t7`
- **T+14**（2周后）：再次拉取，填入 `review_t14`
- **T+30**（1月后）：最终结算，填入 `review_t30` + `actual_result` + `pnl_pct` + `score`

### 考核维度

| 角色 | 考核标准 | 扣分条件 |
|------|---------|---------|
| 1号 宏观 | 周期定位是否兑现（PMI/PPI/利率方向对不对）| 定位完全错误 −3分 |
| 2号 行业 | Watchlist 标的 T+30 涨跌幅 vs 基准 | 跑输基准的比例 >60% −2分 |
| 3号 数据 | 数据准确率（是否有标注错误）| 每个错误 −1分 |
| 4号 交易 | 信号实际胜率 vs 声明胜率 | 实际胜率 < 声明−10pct −3分 |
| 5号 监工 | 发现的红旗是否真实 / 漏检率 | 漏检重大幻觉 −5分 |
| 6号 秘书 | 行动方案执行效果 vs 预期回撤 | 实际回撤 > 声明×2 −3分 |

### 🆕 v4.7 反偷懒扣分（叠加在原有维度之上）

**单次扣分规则**：

| 触发事件 | 适用角色 | 单次扣分 | 数据来源 |
|---------|---------|---------|---------|
| FORCED_PASS + reject_type=SHALLOW | 1/2/4 号 | **-2 分** | review_log.reject_type |
| FORCED_PASS + reject_type=UNVERIFIED | 1/2/3/4 号 | **-2 分** | review_log.reject_type |
| FORCED_PASS + reject_type=COPYING | 2/4 号 | **-2 分** | review_log.reject_type |
| FORCED_PASS + reject_type=PERFUNCTORY_REWORK | 1/2/4 号 | **-3 分** | review_log（敷衍是高频偷懒） |
| FORCED_REJECT + reject_type=SUPERVISOR_LAZY | **5 号** | **-5 分** | audit_log.script_name='supervisor_self_check' verdict=FAIL |

**月度累计触发规则**：

| 累计次数 | 触发动作 |
|---------|---------|
| 月内同角色偷懒 ≥3 次 | 自动生成 `outputs/00_meta/prompt_rewrite_<role>_YYYY-MM.md` 工单 |
| 月内 5 号 supervisor_lazy ≥3 次 | **CRITICAL**：6 号秘书直接呈报老板 + 暂停该角色独立审核权 1 周（改由临时双 5 号交叉审） |
| 连续 3 月任一偷懒类型 ≥3 次 | 触发该角色 Prompt 整体重写 + 5 号深度审计 |

**数据接入路径**：

```bash
# 月度偷懒榜（含触发清单）
python3 scripts/router/review_router.py --monthly-report YYYY-MM

# 偷懒排行
python3 scripts/router/review_router.py --laziness-rank
```

输出会聚合：
- `review_log` 维度（按 reject_type 分类的 FORCED_PASS）
- `audit_log` 维度（4 个检测脚本 + supervisor_self_check 的 FAIL/SOFT_FAIL 计数）
- 自动计算 `trigger_prompt_rewrite` 列表

### 月度考核报告

```markdown
# 月度角色考核报告 [YYYY-MM]

## 各角色推荐登记汇总
| 角色 | 本月推荐数 | HIT数 | MISS数 | 胜率 | 平均盈亏 | 月度评分 |

## 1号宏观回溯
- 上月周期定位: [XX] → 实际走势: [XX] → 评分: [X/10]

## 2号行业回溯
- Watchlist 14只 T+30 表现:
  | 标的 | 推荐价 | 当前价 | 涨跌幅 | vs 沪深300 |

## 4号交易回溯
- 近30天信号: [X]条 / 胜率: [X]% / 盈亏比: [X.X]

## 趋势追踪
- 打回率: 本月 [X]% vs 上月 [X]%
- 各角色评分趋势:（连续3月下降则触发 Prompt 重写）
```

## 4. 6号秘书集成（每次运行内参底部新增）

```markdown
## 📊 上期推荐回溯（负责制追踪）
| 期数 | 推荐 | 推荐时价 | 当前价 | 盈亏 | 评价 |
| 05-18 | 方案A减仓欧科亿 | 113.08 | XX | +X% | HIT/MISS |
| 05-18 | 加仓NVDA至2.5% | $219 | $XX | +X% | HIT/MISS |
```

## 5. 与 5号监工联动

- 如果某角色连续 3 次月度评分 < 6/10：触发 **Prompt 重写** + 5号深度审计
- 如果某角色推荐胜率连续 3 月 < 40%：触发 **降级** + 该角色产出额外增加 1 轮 5号审核

---

## 6. 执行工具

```bash
# 登记本次推荐（运行结束时自动调用）
python3 $SKILL_DIR/scripts/pipeline/register_recommendations.py \
  --date 2026-05-25 \
  --file outputs/06_secretary/06_高管决策内参.md

# T+7 回溯（cron 每周调用）
python3 $SKILL_DIR/scripts/pipeline/review_recommendations.py --period t7

# 月度考核报告
python3 $SKILL_DIR/scripts/pipeline/monthly_review.py --month 2026-05
```
