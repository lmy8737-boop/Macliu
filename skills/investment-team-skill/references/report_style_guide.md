# 投研团队报告风格指南（v6.2.1 标准）

> 适配形态：✅ agent + ✅ bot
>
> **目的**：所有给老板看的标的分析 / 专题报告 / 持仓体检 / 控制权变更专题，**强制使用统一深色酷炫主题**。
>
> **历史参考**：harbin-electric / china-isotope / huahong-tech / kaiwang-tech / national-team-chip / shougang-lanzatech / futu-analysis / gds-analysis / aipc-core-stocks。

---

## 一、铁律（任一违反 → 6 号秘书自身红牌）

| # | 铁律 | 违反示例 |
|---|------|---------|
| 1 | **必须用深色主题**（`--bg: #0f1117`），禁用白底/浅色简版 | huaqin-tech-analysis（浅色简版）= 禁用 |
| 2 | **不要假装跑了 czsc / 缠论引擎**（czsc 因 pyobjc-core 编译失败装不上） | "3 号缠论 minimal 引擎降级"段落 = 禁用 |
| 3 | **技术面用江恩位 + 笔起点 + 估值倍数**（老报告通用语言） | 写"分型/笔/中枢/背驰能量比"= 禁用 |
| 4 | **数据来源必须诚实标注**（v6.2 雪球 / WebFetch / 公开年报 / 手工 fixture） | 假装"czsc 严格缠论输出"= 禁用 |
| 5 | **隐私铁律**：仓位只用百分比，禁用绝对金额 | "建仓 40 万"= 禁用，"建仓 5%" = 允许 |
| 6 | **必须用 templates/dark_report_template.html 起手** | 自己手撸 CSS = 禁用 |
| 7 | **🆕 v6.3 反幻觉铁律**：报告里出现的所有财务数字（ROE/营收/净利/PE/CFO/资产负债率）**必须**来自 `engine/data/finance/finance_<date>.json` 真实拉取；从 LLM 知识或 WebSearch 拼出来的数字必须明确标注 `[LLM_FIXTURE]` 警示 + 引用源链接 | fii 报告写"工业富联资产负债率 50.4%"（真实是 63.37%）= 禁用 |

---

## 一·之二、🆕 v6.3 反幻觉协议（详细）

> **背景**：v6.2.1 报告标准化后发现一个隐蔽 bug——v6.0/v6.1/v6.2 的 `finance_collector.py` 因 akshare 字段映射错误，所有 ROE/营收/CFO/PE 字段返回 0。但 agent 写报告时**用 LLM 训练数据 + WebSearch 拼出"看起来合理"的数字**填进 finance fixture，老板看到的是"假装真实"的财务数据。fii 报告里的 "工业富联资产负债率 50.4% / CFO/NP 1.03" 全部错误（真实 63.37% / 0.148）。

### 1.2.1 三档数据可信度

| 等级 | 来源 | 标注 |
|------|------|------|
| 🟢 **A 级（最可信）** | `finance_<date>.json` 真实拉取（akshare/雪球/财报）+ `report_period_used` 字段标注期数 | 直接展示，无需特殊标注 |
| 🟡 **B 级（可信但需溯源）** | WebSearch ≥2 个独立财经媒体一致 | 必须在数字旁加 `<sup>[源]</sup>` 引用，参考来源 li 必有 ≥2 条 |
| 🔴 **C 级（LLM fixture，慎用）** | 仅 LLM 训练数据 / 单源 WebSearch / 估算 | 必须用 `<span class="tag tag-yellow">[LLM_FIXTURE]</span>` 包住数字 + 在末尾"信息来源"卡里专门列"LLM fixture 说明"段 |

### 1.2.2 6 号自查清单 + 1 项

```bash
# 输出报告前必跑：
target_date=$(date +%F)
finance_json=engine/data/finance/finance_${target_date}.json

# 1. 报告里出现的每个 ROE/营收/净利数字都必须在 finance_json 里能找到匹配
# 2. 找不到的必须显式标注 [LLM_FIXTURE]
grep -oE "ROE.*[0-9]{1,3}\.[0-9]+%|营收.*[0-9]+\s*亿|净利.*[0-9]+\s*亿|PE.*[0-9]+x" report.html
```

### 1.2.3 finance_collector 不通时的协议

| 情况 | agent 应对 |
|------|----------|
| `finance_<date>.json` 不存在 | **不写带财务数字的报告**，先跑 `python3 scripts/cli/prepare_data.py --mode stock --target XXX` |
| `finance_<date>.json` 存在但目标 ticker 缺 | 报告 `[LLM_FIXTURE]` 模式 + 标注"finance_collector 未拉到此 ticker，本次用公开年报合成"+ ≥2 源 WebSearch 引用 |
| `roe_ttm == 0` 且 `np_yoy_latest == 0` | 视为 finance_collector bug 复发，触发 ABORT 不出报告，提示老板 v6.3 的 P0-1 修复可能 regress 了 |

### 1.2.4 v6.0/v6.1/v6.2 老报告的隐瞒罪行

我（agent）之前写的 fii / jinhai 报告里所有财务数字都是 LLM fixture：
- fii: ROE 19.5% / CFO/NP 1.03 / 营收 5929 亿 / 资产负债率 50.4%
- 真实（v6.3 P0-1 修复后从 akshare 拉到的）：ROE 21.65% / CFO/NP **0.148** / 营收 **9029 亿** / 资产负债率 **63.37%**

**反差最大的是 CFO/NP（1.03 vs 0.148，差了 7 倍）**。从此 v6.3 后，所有报告必须先跑 finance_collector 真实拉。

---

## 二、文件命名规范

```
~/Desktop/cc/{slug}-analysis-{YYYY-MM-DD}.html
```

- `slug`：公司英文名 / 品牌缩写 / 主题词，全小写，连字符分隔
  - 例：`harbin-electric` / `china-isotope` / `jinhai-tech` / `national-team-chip`
- 多版本：`-v2`、`-v3` 后缀（参考 `futu-analysis-v2-2026-05-27.html`）

---

## 三、配色规范（CSS 变量）

```css
:root {
    --bg:     #0f1117;   /* 黑色背景 */
    --card:   #1a1d27;   /* 深灰卡片 */
    --border: #2a2d3a;   /* 卡片边框 */
    --text:   #e1e4eb;   /* 主文字色 */
    --muted:  #8b8fa3;   /* 次要文字 / 标签 */
    --accent: #6c9fff;   /* 蓝色强调 */
    --green:  #4ade80;   /* 利好 / 通过 / 正向 */
    --red:    #f87171;   /* 利空 / 否决 / 负向 */
    --yellow: #fbbf24;   /* 警示 / 待定 */
    --orange: #fb923c;   /* 行业研究员 / 中性提醒 */
    --purple: #a78bfa;   /* 穿越者 / 宏观 */
}
```

### 角色色（national-team-chip 风格）

| 角色 | 颜色 | 用法 |
|------|------|------|
| 1 号 宏观 | `--purple` | role-card.macro 顶部 3px 紫色条 |
| 2 号 行业 | `--orange` | role-card.industry |
| 3 号 数据 | `--accent` | role-card.data（蓝色） |
| 4 号 交易 | `--green` | role-card.trader |
| 5 号 监工 | `--red` | role-card.supervisor |
| 6 号 秘书 | `--yellow` | role-card.secretary |
| 7 号 穿越者 | `--purple` | role-card.traveler |

---

## 四、章节结构（推荐顺序）

| # | 章节 | 何时必备 / 选用 | 核心组件 |
|---|------|--------------|---------|
| 1 | **Header** | 必备 | `.header` + `verdict-box.{good,warn,bad}` |
| 2 | **代码勘误**（如有）| 当用户给的代码错误时必备 | `.card` border-color: var(--red) + `blockquote.bear` |
| 3 | **核心 metrics** | 必备 | `.grid-3` × 3 张 `.card`，每卡 4 个 `metric-row` |
| 4 | **信息验证**（事件型必备）| 控制权变更/重大公告类必备 | `.card` + `table` + `tag.tag-green` |
| 5 | **关键事件时间线** | 事件型必备 | `catalyst-item.{done,pending,bad}` |
| 6 | **基本面**（业务结构 + 财报趋势 + 三大引擎） | 必备 | 3 个 `h3` + 表 + `.grid-3` `.stat-card` |
| 7 | **同行对照**（peer 对照） | 推荐 | `table` + 高亮目标行 + `blockquote.bull` |
| 8 | **核弹级催化 / 关键风险** | 视具体而定 | `.card` border-color: var(--accent) + `.grid-2` |
| 9 | **估值情景**（必备） | 必备 | `table` 三档（🔴⚪🟢）+ `blockquote.bear/bull` |
| 10 | **技术面**（江恩位 + 笔起点） | 必备 | `table` + `blockquote.warn` |
| 11 | **5 号监工 audit** | 必备 | `status-{pass,warn,bad}` 椭圆徽章 + 检查 table |
| 12 | **Action Box** | 必备 | `.action-box` + 4 个 `action-option` |
| 13 | **后续跟踪节点** | 必备 | `catalyst-item.{bad,pending}` |
| 14 | **信息来源** | 必备 | `<ul>` + `<a>` 引用 |
| 15 | **Footer** | 必备 | `.footer` + 数据采集命令 |

---

## 五、组件使用决策树

### 5.1 `verdict-box`（顶部判定盒，三选一）
- **`.good`**（绿）：明确推荐买入 / 持有 / 加仓
- **`.warn`**（黄）：观望 / 等待右侧 / 高位减仓
- **`.bad`**（红）：明确否决 / 强烈不建议追高

### 5.2 `tag.tag-{color}`（chip 徽章）
| 颜色 | 用法 |
|------|------|
| green | ✅ 通过 / 利好 / 正向 |
| red | ❌ 否决 / 利空 / 红线 |
| yellow | ⚠️ 警示 / 待定 |
| blue | 中性强调 / 信息标记 |
| orange | 行业 / 中性提醒 |
| purple | 穿越者 / 长期视角 |

### 5.3 `status-{pass,warn,bad}`（5 号 audit 状态徽章）
- 单结论：用单个 status 徽章
- 多动作分别裁定：可同时挂 2 个（如：`status-bad` REJECT 建仓 + `status-pass` PASS 减仓）

### 5.4 `blockquote.{bull,bear,warn}`
- `.bull`（绿色左条）：积极结论 / 超额收益机会
- `.bear`（红色左条）：风险警示 / 否决理由
- `.warn`（黄色左条）：注意事项 / 待跟踪

### 5.5 `catalyst-item.{done,pending,bad}`
- `.done` ✅：已确认事实 / 已兑现催化剂
- `.pending` ⏳：待跟踪 / 进行中
- `.bad` 🚩：红牌项 / 监管悬剑 / 风险信号

### 5.6 `action-option.{recommended,bad}`
- `.recommended`（绿边）：推荐动作（最佳实践 1-2 个）
- `.bad`（红边）：明确否决的动作（"❌ 不要追高"）
- 默认（无修饰）：中性选项 / 备选动作

### 5.7 `stat-card`（三引擎 / 关键数字 highlight）
适合用在"基本面 → 三大增长引擎"或者宏观视角的"4 个并列周期"。

---

## 六、技术面段落标准（替代 czsc 缠论）

**禁用词**：分型、笔、中枢、背驰能量比、czsc、minimal、fractal_count、bi_count

**通用词**：
| 词 | 含义 |
|----|------|
| 江恩支撑 | 来自雪球公开 K 线分析 |
| 江恩压力 | 同上 |
| 30 日区间 | v6.2 真实拉取的 30 日 [low, high] |
| 30 日分位 | 当前价在 30 日区间中位置 |
| 0.382 回撤 | Fibonacci 0.382 回撤位（笔起点 → 笔末端的 0.382） |
| 笔起点 | v6.2 minimal 输出的 last_bi.start，但**不要写"笔"，叫"起涨点"或"区间起点"** |
| 突破带量 | 价 > 压力 + 量 > 1.5x 平均 |
| 缩量假突破 | 价 > 压力 但量 < 0.8x 平均 |

**典型段落**：
```html
<table>
    <tr><th>维度</th><th>数值</th><th>判断</th></tr>
    <tr><td>当前价</td><td>¥31.00</td><td>—</td></tr>
    <tr><td>30 日区间</td><td>¥17.13 — ¥32.99</td><td>极端波动</td></tr>
    <tr><td>当前位置（30 日分位）</td><td>94%</td><td><span class="tag tag-red">极顶部</span></td></tr>
    <tr><td>江恩支撑</td><td>¥23.23</td><td><strong>持仓底线</strong></td></tr>
    <tr><td>江恩压力</td><td>¥32.99</td><td>突破带量看 38-40</td></tr>
    <tr><td>0.382 回撤位</td><td>~¥26.9</td><td>右侧加仓位参考</td></tr>
</table>
```

---

## 七、估值情景标准（必备）

```html
<table>
    <tr><th>情景</th><th>概率</th><th>假设</th><th>目标价</th><th>vs 当前</th></tr>
    <tr><td>🔴 悲观</td><td>30%</td><td>...</td><td>¥14</td><td class="negative">-55%</td></tr>
    <tr style="background:rgba(108,159,255,0.05);">
        <td>⚪ <strong>中性</strong></td><td>50%</td><td>...</td><td>¥21</td><td class="negative">-32%</td>
    </tr>
    <tr><td>🟢 乐观</td><td>20%</td><td>...</td><td>¥33</td><td class="warning">+6.5%</td></tr>
</table>
<blockquote class="bear">
    <strong>概率加权目标价</strong> = 14×0.30 + 21×0.50 + 33×0.20 = <strong>¥21.3</strong>
</blockquote>
```

中性行**始终**用 `style="background:rgba(108,159,255,0.05);"` 高亮。

---

## 八、6 号秘书的 HTML 报告产出协议

### 8.1 起手必做
1. `cp templates/dark_report_template.html ~/Desktop/cc/{slug}-analysis-{date}.html`
2. 在文件头部注释保留模板生成时间戳
3. 检查所有 `{{...}}` 占位符已替换或显式删除（不允许 `{{xxx}}` 留在最终报告里）

### 8.2 内容自查清单（输出前过一遍）

| # | 检查项 | 通过条件 |
|---|------|---------|
| 1 | 主题色 | `:root` 包含 `--bg: #0f1117` |
| 2 | 不假装缠论 | grep `czsc|minimal|分型|背驰` = 0 处 |
| 3 | 技术面用江恩位 | `江恩支撑/压力` 至少出现一次 |
| 4 | 估值情景 3 档全 | 🔴⚪🟢 都有 |
| 5 | 5 号 audit 状态徽章 | `status-{pass,warn,bad}` 至少一个 |
| 6 | action-box 动作明确 | `.action-option` 至少 3 个 |
| 7 | 信息来源 | `<a href>` 至少 2 个 |
| 8 | Footer 含数据采集命令 | `prepare_data.py` 路径 |
| 9 | 隐私铁律 | grep `万元|元/股 × .*股` = 0 处（除非是公开公告） |
| 10 | 占位符清理 | grep `{{` = 0 处 |

### 8.3 文件命名 + 落盘
```bash
# 唯一允许的输出位置
~/Desktop/cc/{slug}-analysis-{YYYY-MM-DD}.html
```

---

## 九、特殊报告类型

### 9.1 持仓体检（哈尔滨电气、中国同辐风格）
- 顶部 `verdict-box.good` "✅ PASS — 继续持有"
- 章节减少（去掉"信息验证"），直接基本面 + 同行 + 估值情景 + audit + action

### 9.2 协议转让 / 控制权变更（金海高科风格）
- 顶部 `verdict-box.warn` 或 `.bad`
- 必带"信息验证（多源核实）" + "关键事件时间线" + "受让方背景专项审计"
- audit 双状态：`status-bad` REJECT 建仓 + `status-pass` PASS 减仓

### 9.3 行业专题 / 主题报告（national-team-chip 风格）
- 顶部 verdict 写"主题观察"而非买卖建议
- 用 7 个 role-card 排开（每号一个色块）
- 适合多标的对比 / 板块讨论

### 9.4 单股深度（gds-analysis、futu-analysis 风格）
- 章节 1-15 全用，标准最完整
- 估值情景必带敏感性分析

---

## 十、违规处理（5 号 audit 红线）

报告产出后由 5 号 audit 跑：
```bash
python3 scripts/audit/report_style_check.py {report_path}
```
（v6.3 待实现）

违规自动 REJECT：
- 浅色主题（缺 `--bg: #0f1117`）→ FAIL
- 出现 czsc/缠论假装术语 → FAIL
- 缺估值情景 → FAIL
- 缺 5 号 audit 段 → FAIL

---

## 附录：从老报告中可学的优秀样本

| 报告 | 学习要点 |
|------|---------|
| `harbin-electric-analysis-2026-05-27.html` | 持仓体检顶 verdict + 5 大持有理由 |
| `china-isotope-analysis-2026-05-28.html` | 核弹级催化高亮卡 + 估值对比同业 |
| `huahong-tech-analysis-2026-05-28.html` | 技术 + 估值 + 行业三角分析 |
| `national-team-chip-analysis-2026-05-31.html` | 7 角色 role-card 排开 + 主题宽幅 1280px |
| `kaiwang-tech-analysis-2026-05-28.html` | 行业地图 + 增长引擎 stat-card |
| `gds-analysis-2026-05-27.html` | 单股深度全章节展开 |
| `jinhai-tech-analysis-2026-06-01.html` | 控制权变更专题（v6.2.1 重写后） |

**反例**（不要参考）：
- `huaqin-tech-analysis-2026-06-01.html` — 浅色简版 + 强行植入"缠论降级"= 错样本
- 旧版 `fii-analysis-2026-06-01.html`（已淘汰）= 同上
