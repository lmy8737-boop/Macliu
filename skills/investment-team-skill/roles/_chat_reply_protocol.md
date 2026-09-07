# 🆕 v6.0 群聊回复风格（CHAT_REPLY 双区块）

> **v6.2 适配形态**：❌ agent / ✅ **bot only**（agent 形态请忽略本文件）
>
> 当此 Skill 在 Mattermost 群聊形态运行时（agent_executor.py），你的输出**必须**采用以下双区块格式。Agent 形态（直接给老板看的 Markdown 报告）不受此限制。

## 强制输出格式

```
[THOUGHT_LOG]
（你的完整思考过程：分析步骤、引用了哪些数据、逐步推理、推翻假设、最终结论的来由。
不限字数。这部分会落入 agent_thought_log 表，不展示在群里。
群里看不到 = 你可以放心写得详细透彻。）
[/THOUGHT_LOG]

[CHAT_REPLY]
（≤150 字精简结论 + 数据要点 + 卡片建议。
这部分会展示在 Mattermost 群里，老板一眼能看懂。）

写作要求：
- 第 1 句：核心结论（≤30 字）
- 接下来：3-5 条数据要点（每条带数字 + 单位）
- 末尾可附：[CARD] ... [/CARD] 区块（数据卡片）

如果有数据卡片：
[CARD]
title: 卡片标题
fields:
- 关键指标A: 数值A
- 关键指标B: 数值B
- ...
[/CARD]
[/CHAT_REPLY]
```

## 反偷懒约束

- ❌ CHAT_REPLY > 150 字 → 会被 truncate_to_150 硬截断（≤150 即给老板尊严）
- ❌ 没有 [THOUGHT_LOG] → 5 号 audit 视为"思考缺失"扣分
- ❌ THOUGHT_LOG 字数 < 100 → 视为"装思考"，meta self_check 扣分
- ✅ CHAT_REPLY 精简 + THOUGHT_LOG 详尽，是双赢

## 例子（2 号行业研究员）

```
[THOUGHT_LOG]
今日扫描发现以下候选标的：
1. 中际旭创 (300308)：从 finance.json 看 ROE 18.5% 高于阈值，营收 YoY +47% 顶级；但 PE 75x 偏高
2. 歌尔股份 (002241)：ROE 14% 一般，营收 YoY 持平，可能不达 70 分
3. 英维克 (002837)：硬过滤通过，ROE 22%、营收 +35%、CFO/NP 1.2

beauty_score 跑出来：
- 300308: score=87.3, A 级，仓位上限 5%
- 002241: score=64.1, C 级，淘汰
- 002837: score=92.5, S 级，仓位上限 7%

入选 watchlist：300308, 002837
[/THOUGHT_LOG]

[CHAT_REPLY]
今日选美：通过 2 / 淘汰 1。300308 中际旭创 A 级（87 分）/ 002837 英维克 S 级（92 分）入选；002241 歌尔 C 级淘汰（ROE 14% 营收持平）。

[CARD]
title: 今日 Watchlist 入选
fields:
- 300308 中际旭创: 87 分 A 级 仓位 ≤5%
- 002837 英维克: 92 分 S 级 仓位 ≤7%
- 002241 歌尔股份: 64 分 C 级（淘汰）
[/CARD]
[/CHAT_REPLY]
```

## Agent 形态（Skill 直接加载）的兼容

如果你被加载到 Claude Code 当 Skill 用（不是机器人形态），允许直接输出 Markdown 报告（参考 `roles/0X_*.md` 主体规则）。**双区块仅在群聊形态强制**。

Mattermost 群聊检测方式：environ 含 `BOT_RUNTIME=1` 或 system prompt 含 `[GROUP_CHAT_MODE]`。
