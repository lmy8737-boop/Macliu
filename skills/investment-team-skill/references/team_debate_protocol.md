# 团队讨论与共识协议（v6.7.5 适用边界）

> 本文件仅供真实 `FULL_7_AGENT` 在**实际参与角色**对关键变量产生实质冲突时加载；不会因历史示例自动加入 1、4、7 号。非交易任务忽略进场、方向、仓位等交易维度，不生成交易动作；`LIGHT_COMMITTEE` 使用主 `SKILL.md` 的同模型多视角裁决，不得称独立对辩。角色以共用证据表为底稿，只提供职责增量；若争议需要独立第二意见，相关角色须另行取证并保留来源链。

## 背景

v6.4.x 之前，7 角色团队的产出被 6 号秘书简单聚合——若 1 号宏观说"超配"、4 号交易说"减仓"、7 号穿越者说"不进场"，**报告里只是把三个不同结论平铺并列**，老板要自己看出分歧。

v6.5.0 引入「分歧识别 → 讨论 → 共识形成」流程：当多个角色对同一标的得出**矛盾或显著不一致**结论时，必须显式触发「团队讨论」环节，把"为什么不一致"和"最后是怎么收敛的"完整记录到报告。

---

## 何时触发团队讨论（自动判定）

5 号 supervisor 在汇总本轮实际参与角色产出后，逐条比对适用的分歧维度；只有会实质改变结论、估值或交易动作的冲突才触发：

| # | 分歧维度 | 触发条件 |
|---|---------|---------|
| 1 | **进场 / 不进场** | 仅交易意图任务：≥ 2 角色对"是否现价进场"结论不一致 |
| 2 | **仓位百分比** | 仅交易意图任务：任两角色仓位上限差距 ≥ 50%（如 2 号 ≤2% vs 4 号 ≤5%）|
| 3 | **方向（多/空/观望）** | 仅交易意图任务：≥ 2 角色对趋势方向给出不同判定 |
| 4 | **时间维度优先** | 仅实际调用 4、7 号且存在交易意图时，短期信号与长期叙事冲突 |
| 5 | **数据等级矛盾** | 同一锚点在不同报告里数值不一致（5 号 audit 锚点对比触发）|
| 6 | **叙事阶段** | 仅实际调用 7 号时，历史类比或叙事阶段判断实质冲突 |

无分歧时跳过本环节，6 号秘书直接走聚合路径。

---

## 讨论流程（5 号主持）

### Step 1：分歧识别（5 号产出 `disagreement_matrix.json`）

```json
{
  "case_id": "wanwei-600063-2026-06-05",
  "disagreements": [
    {
      "dimension": "仓位百分比",
      "claims": [
        {"role": "2号行业", "value": "≤2%", "rationale": "KTV 41 真丑"},
        {"role": "4号交易", "value": "≤4%", "rationale": "Stop 5.90 风险可控"},
        {"role": "7号穿越者", "value": "≤3%", "rationale": "4法则 1.5-2.5/4 试探仓"}
      ],
      "severity": "中"
    },
    {
      "dimension": "短期 vs 长期方向",
      "claims": [
        {"role": "1号宏观", "value": "长期超配", "rationale": "PPI上行+v2资本运作链主级整合"},
        {"role": "4号交易", "value": "短期减仓", "rationale": "KDJ 103.6 严重超买"},
        {"role": "7号穿越者", "value": "现价不进场", "rationale": "亢奋未消化"}
      ],
      "severity": "高"
    }
  ]
}
```

### Step 2：讨论触发（5 号给每个 disagreement 启动一轮"对辩"）

5 号挑选**关键角色 2 人**（claim 距离最远的那两个），让他们各写一段 **≤200 字的 rebuttal**：

> 用：「@2号 vs @4号 — 你们对仓位上限分歧 2% vs 4%，请各自再写 1 段反驳对方的最有力理由 + 给出妥协方案」

Agent 调用：
```
Agent tool 启动 2 个并行 subagent：
  Agent A: prompt = 02_industry_researcher.md + disagreement_context + 「请反驳 4 号的 ≤4% 仓位」
  Agent B: prompt = 04_trader.md + disagreement_context + 「请反驳 2 号的 ≤2% 仓位」
  run_in_background: true
```

每方产出：
- **claim**: 我的最终立场（可能微调）
- **rebuttal**: 反驳对方的最强论点 1-2 条
- **compromise**: 我能接受的折中方案
- **redline**: 我绝不让步的底线

### Step 3：共识形成（5 号根据三段论裁定）

5 号读完 2 段反驳后输出 `consensus.json`：

```json
{
  "dimension": "仓位百分比",
  "final_consensus": {
    "value": "短期 ≤2% / 中期回踩 ≤3% / 长期链主级兑现 ≤5%",
    "confidence": "高",
    "reasoning": "短期取 2 号严格上限（KTV 41 + 估值高位是真实风险），中长期采纳 4/7 号梯度上调（链主级叙事支撑放宽空间）。三方均接受的折中：用时间维度切分仓位上限。",
    "dissenting_view": null
  },
  "key_argument_winner": "时间维度切分（双方都支持）"
}
```

如分歧无法收敛（罕见）→ `final_consensus.value` 标记为 `"未收敛 - 取保守值"`，并在报告里保留 dissenting_view。

### Step 4：6 号秘书必须把讨论过程写进报告

6 号在 HTML 报告里**新增独立章节**「🤝 团队讨论与共识形成」，包含：
1. 分歧矩阵表（哪几条维度有分歧）
2. 每条分歧的 2 段对辩原文（互相反驳的强论点）
3. 最终共识 + 取舍逻辑
4. 未收敛的部分（如有）

---

## 报告呈现（黑金主题新组件）

### `.debate-card`（分歧卡片，紫金边）

```html
<div class="debate-card">
  <h2>🤝 团队讨论与共识形成（5 号主持）</h2>
  <div class="debate-summary">
    本次发现 N 个分歧维度，已通过对辩收敛 M 个，未收敛 K 个。
  </div>

  <div class="disagreement">
    <h3>分歧 #1：仓位百分比（2 号 ≤2% vs 4 号 ≤4%）</h3>
    <div class="rebuttal-grid">
      <div class="rebuttal rebuttal-a">
        <div class="role-tag">@2号 行业</div>
        <p>反驳：KTV 41 真丑硬过滤 + 营收双年负 = 系统性瑕疵，不能因为 stop 5.90 风险可控就放宽到 4%...</p>
      </div>
      <div class="rebuttal rebuttal-b">
        <div class="role-tag">@4号 交易</div>
        <p>反驳：KTV 41 是静态打分，不反映 v2/v3 链主级整合的拐点...</p>
      </div>
    </div>
    <div class="consensus-box">
      <strong>最终共识</strong>：短期 ≤2% / 中期回踩 ≤3% / 长期链主级兑现 ≤5%（时间维度切分）
    </div>
  </div>
</div>
```

### `.consensus-card`（共识卡片，金色高亮）

放在报告 Action Box 之前，让老板一眼看到团队 7 角色的最终汇聚结论。

---

## 与 v6.4.7 反偷懒协议的关系

| v6.4.7 行为 | v6.5.0 升级 |
|-----------|-----------|
| 5 号检测到角色 A 的产出与 B 的产出"事实矛盾" → REJECT 回炉 | **不变**（这是事实级幻觉，仍 REJECT）|
| 5 号检测到 A 与 B "结论不一致但都基于真实数据" → 老版本默默放过 | **新增触发讨论**：让 A、B 各自反驳，5 号裁定共识 |
| 6 号默默聚合所有结论 | **必须独立成章节呈现讨论过程** |

简单说：**v6.5 区分"幻觉" vs "立场分歧"**——前者打回，后者公开辩论。

---

## 触发-收敛-写入 完整时序图

```
Phase 4：1/2/3/4/7 号产出完毕
        ↓
Phase 4.5（v4.7 已有）：跑 4 个 audit 脚本
        ↓
Phase 5：5 号 supervisor 输出 STATUS
        ↓
        ├─ 检测 6 个分歧维度
        ├─ 任一命中 → 进入 Phase 5.5（v6.5 新增）
        └─ 全无分歧 → 直接 Phase 6
        ↓
🆕 Phase 5.5：团队讨论
        ├─ 5 号识别分歧 → disagreement_matrix.json
        ├─ 每条 disagreement 启动 2 个对辩 subagent（并行）
        ├─ 5 号根据 rebuttal 裁定 consensus
        └─ 输出 outputs/05_supervisor/05_team_debate.md
        ↓
Phase 6：6 号秘书必须把 05_team_debate.md 完整写入报告
        ├─ HTML：新增 .debate-card 章节
        └─ MD：新增「## 🤝 团队讨论」段
        ↓
Phase 7（最终）：老板看到的是
        ├─ 各角色独立观点
        ├─ 分歧矩阵 + 对辩原文 + 共识形成逻辑
        └─ 行动建议（基于共识）
```

---

## 实施清单（v6.5.0）

| 文件 | 改动 |
|------|------|
| `references/team_debate_protocol.md` | 🆕 本文档（协议规范）|
| `orchestrator.md` | 🆕 加 Phase 5.5 团队讨论段 |
| `roles/05_supervisor.md` | 🆕 加分歧识别 + 主持讨论职责 |
| `roles/06_secretary.md` | 🆕 强制必须写「团队讨论」章节 |
| `templates/dark_report_template.html` | 🆕 加 `.debate-card` / `.rebuttal-grid` / `.consensus-box` 黑金组件 |
| `references/report_style_guide.md` | 🆕 新组件章节 + 6 号自查清单加第 13 项「团队讨论是否独立成章节」|

---

## 何时**不**走团队讨论

- 单机简单查询（如 `czsc_check.py SH600063`）
- 老板明确说"快速分析"或"≤500 字摘要"
- 标的太冷门（无足够 Watchlist 池可对照）

这些情况 6 号可以跳过讨论卡片，直接写聚合报告。
