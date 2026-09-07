---
name: research-data-verify
description: >
  Canonical evidence semantics and multi-source verification for financial research.
  Defines source level, claim type, verification status, retrieval status and legacy
  label mappings; use before writing or when auditing an existing research report.
version: "2.0.0"
updated: "2026-09-07"
---

# Research Data Verification Skill

## Canonical Evidence Semantics（Skill 层唯一口径）

外层 `AGENTS.md` 与《投资问题研究总规则》保留上位纪律；所有现行投研 Skill 的字段名、枚举和旧标签解释统一引用本节，不再各自定义一套。

| 维度 | 规范取值 | 含义 |
|---|---|---|
| `source_level` | `P0` / `P1` / `P2` / `P3` | 来源权威性：P0 一手披露、监管/官方资料、原始结构化行情财务数据；P1 可信事实报道、行业/政策/论文与可验证买方研究；P2 卖方研报、专家会、目标价和产业推演；P3 KOL、社群转述、匿名截图与小作文 |
| `claim_type` | `fact` / `third_party_view` / `guidance` / `model` / `scenario` | 主张是什么；管理层指引、第三方观点、模型结果和未来场景不得写成已发生事实 |
| `verification_status` | `original_checked` / `independent_cross_checked` / `single_source_unverified` / `conflicted` / `unverified` | 主张验证到哪一步；单份 P0 原文核验是 `original_checked`，不是独立双源 |
| `retrieval_status` | `ok` / `partial` / `empty` / `stale` / `error` | 本次获取是否成功；与证据等级、主张类型和验证状态正交 |

数值只有在**同一口径、至少两个信息链独立的来源、差异≤2%**时才可记 `independent_cross_checked`；超过 2% 记 `conflicted` 并并列数值，不取平均。非数值主张须由独立信息链支持同一命题。`as_of`、`checked_at` 与 T0/T1/T2 时效要求单列；`retrieval_status=ok` 不代表数据新鲜或主张已验证。

工具名只表示获取通道：`stock-data`、BRM、`web-harvest` 均可能返回不同等级和类型的材料，必须按底层来源与内容重新标注。可信媒体的事实报道可为 P1，不能把全部媒体机械降为 P3；卖方观点通常为 P2，其中转引的公告事实也只是一手原文定位线索，不能因经 BRM 获取就改变等级。

兼容旧稿时只映射、不批量改库：`[V]` 仅对应 `independent_cross_checked`；`[A]` 若明确为已核官方单源则对应 `original_checked`，否则按 `single_source_unverified`；`[S]` 对应 `single_source_unverified`；`[E]` 表示 `claim_type=model/scenario/guidance`，不是验证状态；`[X]` 若表示来源冲突则对应 `conflicted`，若表示“已否认”则应写 `fact + original_checked`；`[?]`/`[ ]` 按上下文映射为 `unverified`、`single_source_unverified` 或 `retrieval_status=empty`；`[N/A]` 只描述 `empty/error`，不充当验证状态。

**红线**：能从一手源获取的数据（营收、利润、EPS、毛利率、业务结构、股东信息），禁止仅从卖方研报转引并标为已核验。

**卖方优先级**：涉及全球供应链格局、份额、BOM 拆解、龙头辨识时，**海外大投行（Bernstein/UBS/BofA/Jefferies/MS/TD Cowen/GS）＞国内券商**。国内券商视角偏 A 股映射，易把边缘参与者误判为核心龙头、遗漏非 A 股全球真龙头。BRM 搜索时先 `searchForeignReports`，再 `searchDomesticReports` 补充。

---

## Phase 1: Identify Data Points

对报告中每个数字/事实进行分类：

### Category A: 财务KPI（必须有一手源）
- 营收（年度+季度，YoY）
- 净利润 / 归母净利润
- 毛利率、净利率、营业利润率
- EPS（基本/稀释）
- 经营现金流
- 资本开支
- 股息/分红
- 业务结构（各分部营收占比）

### Category B: 经营指标（优先一手源，可接受行业数据）
- 行业特有KPI（如：产能、出货量、份额、客户结构）
- 产品线/技术路线信息
- 管理层指引

### Category C: 时效性数据（按 T0/T1 分级处理，详见工作区 `AGENTS.md` 与《投资问题研究总规则》）

**T0 实时数据（日频变动）——必须实时工具取，严禁 BRM 照搬：**
- 当前股价（`pricePerformance` / `stock-data`，标查询日期）
- 市值（实时取）
- PE/PB/PS/EV（**自行计算**：实时股价 ÷ 预测 EPS，不照搬研报 PE）
- "现价 vs 目标价"隐含空间（**自行计算**，研报的"隐含空间"发布当天就过期）
- 汇率、大宗商品价格、利率/国债收益率、指数点位
- 52周高低（标日期）

**T1 季频数据——BRM 可用但必须核对时间戳：**
- 最新季度营收/利润/EPS（确认是最新季度，标"截至 YYYY-QX"）
- 管理层指引（确认是最新一次电话会）
- 产能数据（CoWoS 月产能等，标截止日期）
- 基金/机构持仓

### Category D: 卖方专属数据（允许仅用BRM）
- 机构目标价
- 盈利预测（EPS forecast）
- 产业链拆解数据（如CoWoS产能分配、HBM出货预测）
- 行业规模预测

> **Category A必须一手源**，Category D可以只用BRM，Category B/C视情况。

---

## Phase 2: Multi-Source Verification Protocol

### 工具链（按优先级使用）

| 工具 | 角色 | 覆盖市场 |
|------|------|---------|
| **web-harvest** | 一手源采集（公司IR页面、交易所公告、官网） | 全市场 |
| **stock-data** | 行情/财务数据（Yahoo Finance for 美股/日股/韩股，腾讯 for A/港股） | 全市场 |
| **BRM（进门）** | 卖方研报、机构观点、产业链数据 | 全市场 |

### 各市场一手源速查

| 市场 | 一手源 | URL模式 |
|------|--------|---------|
| **台股** | 台积电IR: investor.tsmc.com；台交所: mops.twse.com.tw | 季报/年报PDF |
| **美股/ADR** | SEC EDGAR (sec.gov)、公司IR页面 | 10-K/10-Q/8-K |
| **韩股** | DART (dart.fss.or.kr)、公司IR页面 | 事业报告书 |
| **日股** | EDINET、公司IR页面 | 有価証券報告書 |
| **港股** | 港交所 (hkexnews.hk)、公司IR页面 | 中期/年度报告 |
| **A股** | 巨潮 (cninfo.com.cn)、上交所/深交所 | 季报/年报 |

### 每个Category A数据点的验证流程

1. **先查一手源**：用web-harvest去公司IR页面或交易所拉财报原文
2. **stock-data交叉**：用stock-data获取财务数据对比
3. **BRM补充**：如果一手源获取困难（如非英语财报），可用BRM中的财报摘要，但需标注"经BRM转引，待一手源核实"
4. **记录来源**：每个数据点记录具体来源文件名/URL
5. **按实质标注**：工具名不进入 `source_level`；另记 `claim_type`、`verification_status`、`retrieval_status` 与 `as_of`

---

## Phase 3: Classification & Labeling

逐条填写本文件「Canonical Evidence Semantics」的四个字段。补到单份一手原文时，验证状态从 `unverified/single_source_unverified` 升为 `original_checked`；只有满足独立信息链与同口径≤2%门槛，才升为 `independent_cross_checked`。出现实质冲突即记 `conflicted`，不设 5%/10% 灰区。

---

## Phase 4: Verification Table

输出格式（嵌入报告末尾的"数据核查表"章节）：

```markdown
| 数据点 | 采用值 | `claim_type` | `source_level` | 原始/交叉来源 | `verification_status` | `retrieval_status` | `as_of` |
|---|---|---|---|---|---|---|---|
| 1Q26营收 | TWD 1,134,103mn | fact | P0 | 台积电季报 + 独立结构化源 | independent_cross_checked | ok | 2026-Q1 |
| CoWoS月产能2026E | 11.5-15万片 | third_party_view | P2 | JPM/中信建投/GS | single_source_unverified | ok | 2026E |
| 2026E EPS | TWD 97.64 | model | P2 | BofA | single_source_unverified | ok | 2026E |
```

关键检查：`fact` 类 Category A 必须有一手源；单份一手源只能标 `original_checked`。多个卖方若共享同一底稿，不构成独立双源。

---

## Phase 5: Post-Write Audit Mode

对已完成的报告进行复查时：

1. **读取报告的数据核查表**
2. **逐条检查**：
   - Category A数据是否有一手源？没有的标记为"待补一手源"
   - `independent_cross_checked` 是否真的有≥2个独立信息链，且同口径差异≤2%？
   - 一手源和卖方数据是否一致？
   - 预测、指引和场景是否分别标为 `model`、`guidance`、`scenario`？
   - `retrieval_status`、`as_of` 与 T0/T1 时效是否分开记录？
3. **执行一手源采集**：对缺少一手源的Category A数据，立即用web-harvest/stock-data补查
4. **输出审计结果**：列出需修正的数据点和建议
5. **更新报告**：修正数据核查表，补上一手源

---

## Phase 6: Hard Blocks

- ❌ Category A 数据不允许仅从卖方研报转引并标 `original_checked` 或 `independent_cross_checked`
- ❌ 不允许用AI记忆中的数据，必须实时查询
- ❌ 股价必须标日期
- ❌ **所有 T0 时效性数据（股价/市值/PE/汇率/指数/大宗/隐含空间）严禁从 BRM 照搬——必须从实时工具取，PE 必须自行计算。T1 数据（季度财务/产能/指引）可用 BRM 但必须确认是最新季度。违反 = 估值框架全错（TSMC $215→$408 事故根因，但不只股价——汇率、指数、商品价格都会出同样的问题）**
- ❌ 产品名/技术名必须有官方来源确认
- ❌ 预测数据不允许写成已报告事实
- ❌ 数据缺口不允许用"合理估计"静默填充——必须标 `retrieval_status=empty/error`；需要模型区间时另记 `claim_type=model/scenario`

---

## Quick Reference: 常用公司IR页面

| 公司 | IR页面 |
|------|--------|
| TSMC | investor.tsmc.com |
| NVIDIA | investor.nvidia.com |
| SK Hynix | skhynix.com/ir |
| Samsung | samsung.com/semiconductor/ir |
| Broadcom | investors.broadcom.com |
| AMD | ir.amd.com |
| Micron | investors.micron.com |
