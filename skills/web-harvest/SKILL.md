---
name: web-harvest
description: 全局联网搜索与网络采集的唯一总路由。凡是搜索互联网、查最新信息、事实核验、找原文、读取URL、平台内容检索、浏览器登录态、网页交互、批量抓取、反爬处理、RSS/视频/社交/GitHub搜索或外部文章采集，都先使用本 skill 决定具体通道。它统一编排 AnySearch、Agent Reach/Exa、内置web、web-access、Scrapling、stock-data及外部文章采集 skill；其他总规则只应指向本 skill，不应复制分流规则。
version: 3.3.0
updated: 2026-09-07
---

# Web Harvest

> [!note] 关于本文提到的外部技能
> 本文档里提到的 `AnySearch`、`Agent Reach`、`web-access`、`Scrapling`、`pdf`、`wechat-article-to-markdown`、`Firecrawl` 都是**独立的搜索/采集子技能或第三方服务，本包不包含它们的实现**——本包只含 `web-harvest` 这一层"路由决策逻辑"本身。你可以：①自己实现/接入等价能力（比如换成你自己顺手的搜索 API、浏览器自动化工具），②只保留内置联网工具作为兜底，暂时跳过路由表里指向这些外部技能的分支。核心方法论（先判断任务形态、按"便宜可靠优先、失败再升级"分配通道、证据必须闭环到原文）不依赖这些具体工具名。

## 唯一入口契约

- 所有**联网搜索、网页读取和网络采集**先进入本 skill；本地文件搜索（如 `rg`）不属于本路由。
- 本 skill 只负责判断目标、选通道、组织降级和审计来源；窄领域 skill 负责实际执行。
- `stock-data`、BRM、外部文章保存等拥有自己的领域规则，但是否需要补充互联网搜索仍由本 skill 判断。
- 其他工作区总规则只保留“联网统一由 web-harvest 路由”这一指针，不复制工具树、错误码或平台命令。
- 先查看 [能力矩阵](references/capability-matrix.md)；不确定环境状态时运行 `python3 scripts/doctor.py`，不要把“已安装”当成“当前可用”。路由规则变更后必须运行 `python3 scripts/route_regression.py`。

这是网络采集总路由 skill。目标是先判断任务类型，再选择最合适的通道：

- `AnySearch MCP`: 首选搜索/提取通道。若当前 Codex 线程暴露 `mcp__anysearch__*` 工具，优先用 MCP 的 `search`、`batch_search`、`extract`、`get_sub_domains`。
- `AnySearch`: 实时搜索发现、垂直领域搜索、批量并行搜索、URL 正文提取。
- `web-access`: 真实浏览器/CDP/登录态/内网页面/需要交互的平台。
- `Scrapling`: 工程化爬虫/批量采集/动态页面/反机器人/代理轮换/可恢复 Spider。
- `Agent Reach`: 平台型内容能力与健康诊断。用于 YouTube、B站、RSS、V2EX、GitHub，以及按需配置的 X/Reddit/小红书等；其 Exa 后端作为英文技术、代码和语义搜索补充。
- `wechat-article-to-markdown`: 用户只要求保存微信、知乎、雪球公开文章时的原文归档通道；保存不自动升级成完整投研。
- `stock-data`: 金融行情、股票数据、财报、资金流、研报等结构化金融数据的优先工具。
- `pdf`: URL 直接是 PDF，或页面上挂着财报/白皮书 PDF 链接时，下载后交给它提取/OCR/读表格，不要只读页面 HTML 漏掉 PDF 正文。
- `scripts/firecrawl_client.py`（Firecrawl 云 API，需 `FIRECRAWL_API_KEY`）: 仅用于本 skill 现有通道覆盖不到的两件事——**Schema 结构化提取**（给字段定义直接拿 JSON，比手写选择器更抗页面改版）和 **`map` 全站 URL 发现**（摸清一个站有多大、按关键词找定价页）。不是通用抓取通道，Scrape/Crawl/Search 这类常规需求仍走 AnySearch/Scrapling，避免和已装工具重复。
- 内置联网工具: 轻量搜索、官方文档核实、单页读取。

始终优先合规采集公开或用户已授权访问的数据。不要帮助绕过付费墙、账号权限、明确访问控制或网站条款中禁止的用途。遇到登录、验证码、风控、封号风险时，先说明风险并让用户确认。

## 默认分配

按“便宜可靠优先，失败再升级”执行。除非用户指定工具，否则默认这样分配：

1. `web-harvest` 负责路由，不和具体工具抢活；它先判断任务属于搜索、读取、浏览器、批量爬虫还是金融结构化数据。
2. 搜索发现、实时信息、事实核查、批量搜索、URL 正文提取，首选 `AnySearch MCP`。如果当前线程没有暴露 MCP 工具、MCP 报错或限流，再降级到 `<your-skills-root>/anysearch` 的 CLI。
3. 已知 URL 且只是读普通公开正文，优先用内置网页读取、AnySearch `extract` 或 Jina；不启动浏览器和爬虫。
4. YouTube、B站、RSS、V2EX、GitHub等平台内容，加载 `agent-reach` skill，先跑 `agent-reach doctor --json`，按 `active_backend` 调用平台工具。
5. 英文技术、代码上下文或语义相似搜索，AnySearch召回不足时补充 Agent Reach 的 Exa；Exa不是通用搜索的默认替代品。
6. 需要登录态、点击、滚动、截图、上传、真实页面状态时，先看 Agent Reach 是否已有健康的平台后端；没有时使用 `web-access`。
7. 需要批量抓取、多页翻页、导出 JSON/CSV、可恢复长任务、动态页面工程化采集，使用 `Scrapling`；先小样本验证，再扩大。
8. 股票行情、K 线、财报、资金流、估值、公告、研报、指数/ETF 等金融结构化数据，优先使用 `stock-data`；雪球社区内容才考虑 Agent Reach，不能用雪球页面替代结构化行情。
9. 内置联网工具只做轻量补充、官方文档核验或当外部工具不可用时的兜底。
10. 用户只要求保存微信、知乎、雪球文章时，直接路由到 `wechat-article-to-markdown`；若同时要求核验、分析或并入研究框架，再叠加 `investment-search` 与投研流程。

AnySearch 当前允许匿名免费访问。失败时必须按状态区分，不能笼统告诉用户“免费版失效、重新申请”：

- `402 daily_free_quota_exhausted`：匿名IP当天免费额度用完；改用Agent Reach Exa或内置搜索，次日再试。只有用户希望提高稳定性时才建议创建免费Key。
- `401/403`：仅在实际发送了Key时才判断Key无效、过期或禁用；无Key的匿名请求不能归因于Key失效。
- `429`：短期限流，按 `retry_after` 退避后重试，仍失败再切换通道。
- `5xx`、DNS、TLS、超时：服务或网络故障，直接走备用搜索，不要求用户重新申请Key。

不得自动保存AnySearch返回的新Key。确需持久化时先征得用户明确同意。

冲突处理：`AnySearch MCP` 与 `AnySearch CLI` 功能重叠时，MCP 是首选，CLI 是备份；`web-access` 与 `Scrapling` 都能打开动态页时，少量交互/登录用 `web-access`，批量生产用 `Scrapling`；`stock-data` 与搜索结果冲突时，结构化金融数据以 `stock-data` 或交易所/监管原始来源为准。

## 快速路由

| 场景 | 首选 |
| --- | --- |
| 一般联网搜索、实时信息查询、网页调研、事实核查 | `AnySearch MCP`；不可用时 `AnySearch CLI`，必要时升级到页面读取 |
| 股票行情、财务报表、资金流、研报、股东结构、A/H/美股数据 | `stock-data`；`web-harvest` 仅补公告、新闻、网页来源 |
| 已知 URL，普通文章/文档/公告 | 内置网页读取或 Jina |
| 不知道入口 URL，需要找源头、新闻、文档、公司/项目页面 | `AnySearch MCP search`；降级到 CLI |
| 多个独立查询、竞品/来源并行发现 | `AnySearch MCP batch_search`；降级到 CLI |
| 股票/CVE/DOI/IATA/专利/行业等垂直领域搜索 | `AnySearch MCP get_sub_domains` 后垂直搜索；降级到 CLI |
| 已知 URL，只需要正文 Markdown | `AnySearch MCP extract`、CLI `extract` 或 Jina |
| 需要一手来源核实 | 搜索定位后访问官方/原始来源 |
| 用户浏览器已登录、公司内网、微信/小红书/微博等静态层无效页面 | `web-access` |
| 需要点击、滚动、上传、截图、视频取帧 | `web-access` |
| 批量页面、列表翻页、导出 JSON/CSV、可恢复长任务 | `Scrapling Spider` |
| 轻量 HTML 请求、需要浏览器 TLS/UA 指纹 | `Scrapling Fetcher` |
| JS 动态页面但不依赖用户登录态 | `Scrapling DynamicFetcher` |
| Cloudflare/Turnstile/明显反机器人页面 | 先评估合规性，再用 `Scrapling StealthyFetcher` 或 `web-access` 真实浏览器 |
| 网站结构经常变化，选择器易失效 | `Scrapling` adaptive selectors |
| URL 是 PDF，或页面挂着财报/白皮书 PDF 链接 | 下载后交给 `pdf` skill，不要只读页面 HTML |
| 给字段定义要结构化 JSON（标题/价格/日期等），页面结构可能常变 | `firecrawl_client.py scrape --schema` |
| 想知道一个站有多大、找定价页/文档页这类特定路径 | `firecrawl_client.py map --search <关键词>` |
| 多个独立目标并行调研 | 子任务并行，结果汇总 |
| 英文技术/代码语义搜索 | AnySearch先行；不足时 Agent Reach Exa 补充 |
| GitHub仓库/Issue/代码 | Agent Reach + `gh`；登录验证后完整可用；如果出现"未认证"，记住一个反直觉的教训——`gh` 未认证时会完全拒绝执行，连公开仓库都读不了，不是"只读公开资源"式的优雅降级，此时应改走 WebFetch 兜底，而不是以为公开仓库不需要认证 |
| YouTube视频信息/字幕 | Agent Reach + `yt-dlp` |
| B站搜索/视频信息 | Agent Reach 的健康后端；不要默认用 `yt-dlp` |
| RSS/Atom订阅源 | Agent Reach + `feedparser` |
| V2EX主题与回复 | Agent Reach + V2EX公开API |
| 雪球行情/搜索/热帖/热股 | Agent Reach `XueqiuChannel`（2026-09-07已配登录态并验证：`get_stock_quote`/`search_stock`/`get_hot_posts`/`get_hot_stocks`）；仅用于社区情绪和热度，不替代 `stock-data` 的结构化行情 |

## 工作流

1. **定义成功标准**：要回答什么、需要原文还是摘要、时间范围、来源等级、输出格式、是否需要登录态。
2. **判断任务形态**：区分 `search`（找入口）、`fetch`（读已知URL）、`interact`（登录/点击）、`crawl`（批量生产）、`structured`（金融/专业结构化数据）、`archive`（仅保存原文）。
3. **检查缓存**：非敏感、非登录态任务先用 `scripts/cache.py lookup-query` 或 `lookup-url` 检查已有结果；T0或用户明确要求最新时按时效纪律刷新。
4. **拆查询与来源**：复杂问题拆成官方、一手事实、行业背景、反方/否定词和本地语言查询；多个独立查询优先批量并行。
5. **先做搜索发现**：入口未知时用 AnySearch MCP 找候选来源；当前线程没有 MCP或失败时用CLI；英文技术/代码召回不足时补Exa。
6. **轻量探测**：访问1-2个样本页，判断静态/动态/登录/反爬/分页模式，不在错误通道上机械重试。
7. **选择通道**：
   - 金融结构化数据优先加载 `stock-data`；需要找网页来源、公告、新闻、登录页或批量页面时再回到本 skill。
   - 搜索、批量发现、URL 正文提取优先用 AnySearch MCP；MCP 不可用再读 `references/anysearch.md` 并走 CLI。
   - 投研搜索、传闻核验、小作文源头追踪、产业链受益映射、订单/客户线索核验时，读 `references/investment-search.md` 并按证据矩阵输出。
   - YouTube/B站/RSS/V2EX/GitHub/社交平台内容，先读 `<your-skills-root>/agent-reach/SKILL.md`，再按其分类读取对应 reference；不得凭印象拼平台命令。
   - 真实登录态或交互优先读 `web-access` skill 并执行它的前置检查。
   - 批量或工程化任务优先读 `references/scrapling-patterns.md`。
   - 不确定时读 `references/router.md`。
8. **证据闭环**：搜索结果只用于定位；重要事实回到官网、公告、论文或原始页面。按 `references/source-quality.md` 保留P0-P3等级并评分，评分不得提升证据等级。
9. **小样本验证**：批量任务先抓少量数据，检查字段质量、重复、缺失、分页和限速。
10. **扩大执行**：加入节流、checkpoint、去重、导出和错误重试；公开页面成功后用缓存记录URL、正文指纹和归档去向。
11. **交付与审计**：说明搜索通道、来源URL、时间、证据等级、覆盖范围、缓存命中、失败项、降级路径与残余风险。

## 健康检查

```bash
python3 scripts/doctor.py
python3 scripts/doctor.py --json
python3 scripts/doctor.py --live
```

- 默认模式只检查安装、路径与本地配置，不消耗搜索额度，也不启动浏览器。
- `--live` 对 AnySearch 和 Agent Reach 做轻量联网探测；长任务或报错后再使用。
- 登录态平台仍需按各自skill确认用户授权，doctor不会自动读取Cookie。

## 质量控制

```bash
# 查看复杂或有歧义的请求应走哪条路线
python3 scripts/route.py "用户请求"

# 修改路由后运行20条确定性回归用例
python3 scripts/route_regression.py

# 给单条证据评分，P0-P3等级不会被分数提升
python3 scripts/source_quality.py --url "URL" --source-type reliable_media --directness direct

# 检查跨任务缓存
python3 scripts/cache.py stats
```

- `references/route-policy.json` 是机器可读的路由基线；主文和能力矩阵描述原则，二者变更时同步更新测试。
- 缓存默认位于 `~/.cache/web-harvest/harvest.sqlite3`，默认不保存正文；登录态内容默认不写入。
- 行为测试提示词位于 `evals/evals.json`，用于后续新旧版本对照；确定性回归用例位于 `evals/routing_cases.json`。

## 使用 AnySearch

当任务需要实时搜索、找入口、批量搜索、垂直领域搜索或 URL 正文提取时，优先使用已注册的 `AnySearch MCP`：

- `search`: 普通搜索、实时信息、源头发现。
- `batch_search`: 多个独立查询并行搜索。
- `get_sub_domains`: finance、academic、health、security、social_media 等垂直领域搜索前置发现。
- `extract`: 已知 URL 的正文 Markdown 提取。

如果当前线程没有暴露 `mcp__anysearch__*` 工具、MCP 报错、网络失败或限流，再加载 `<your-skills-root>/anysearch/SKILL.md`，并使用其 `runtime.conf` 中的命令：

```bash
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py search "query" --max_results 5
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py batch_search --query "q1" --query "q2"
python3 <your-skills-root>/anysearch/scripts/anysearch_cli.py extract "https://example.com/page"
```

对于 finance、academic、travel、health、code、legal、security、business、social_media 等领域，先调用 `get_sub_domains`，再用返回的 `sub_domain` 和必填参数搜索。AnySearch 查询和 URL 会发送到 `https://api.anysearch.com`；不要把密码、个人隐私、未公开商业秘密等敏感内容放进查询。

## 金融数据例外

当用户要的是股票行情、K 线、财报、资金流、股东结构、分红、ETF、研报、指数或 A/H/美股结构化数据时，优先使用 `stock-data` skill。`web-harvest` 在这些任务中承担补充角色：

- 找公司公告、新闻、官网页面、交易所页面、监管文件入口。
- 抓取 `stock-data` 覆盖不到的网页表格或 PDF/HTML 来源。
- 需要登录态、动态页面、反爬或批量页面采集时，用 `web-access`/Scrapling 执行。
- 对金融结论做来源核验时，用 AnySearch 找一手来源，再用网页读取或 Scrapling 提取。

## 使用 web-access

当任务需要用户真实浏览器时，加载并遵循 `<your-skills-root>/web-access/SKILL.md`。如果该路径不可用，先查找 `web-access` skill。

运行前置检查：

```bash
node <your-skills-root>/web-access/scripts/check-deps.mjs
```

如果提示未连接远程调试，让用户在 Chrome 打开 `chrome://inspect/#remote-debugging`，或在 Edge 打开 `edge://inspect/#remote-debugging`，勾选 `Allow remote debugging for this browser instance`。

## 使用 Agent Reach

Agent Reach 是平台能力安装器和诊断层，不替代 `web-harvest` 的总路由，也不替代 AnySearch、stock-data、web-access 或 Scrapling。调用平台工具前：

```bash
agent-reach doctor --json
```

按返回的 `active_backend` 选择命令。当前基础渠道包括 Exa、Jina、YouTube、B站搜索、RSS、V2EX和GitHub CLI；涉及Cookie或登录态的平台不得自动导入浏览器凭证，必须由用户明确授权。

默认分工：

- AnySearch：中文/通用实时发现、批量搜索、垂直搜索和URL提取。
- Exa：英文技术、代码上下文和语义相似内容的补充召回。
- Agent Reach平台后端：视频、社区、RSS、GitHub等平台原生结构。
- web-access：真实浏览器交互与用户已登录页面。
- Scrapling：规模化、可恢复的网页采集。

## 使用 Scrapling

先检查环境：

```bash
python3 skills/web-harvest/scripts/check_stack.py
```

如未安装 Scrapling，在用户允许联网安装后执行：

```bash
python3 -m pip install --user "scrapling[all]"
scrapling install
```

单页验证示例：

```python
from scrapling.fetchers import Fetcher

page = Fetcher.get("https://example.com", impersonate="chrome")
print(page.css("title::text").get())
```

批量任务不要直接上大规模。先抓样本，再写 Spider，加并发、延迟、checkpoint 和导出。

## 组合策略

- 用 `web-access` 发现真实页面行为、登录态 URL、接口参数、站点内自然链接。
- 把已验证的公开 URL 模式、选择器、分页规则迁移到 Scrapling Spider 批量执行。
- 对必须使用登录态的资源，不要把 cookie/token 硬编码到脚本；优先在浏览器中完成读取或让用户提供授权方式。
- 对反机器人页面，不要无脑重试；记录状态码、页面提示、挑战类型、IP/账号风险，再决定是否继续。

## 输出规范

默认输出：

- 摘要：抓取到了什么、多少条、覆盖范围。
- 数据文件：JSONL/CSV/Markdown，按用户需求选择。
- 来源说明：URL、采集时间、使用通道。
- 证据质量：P0-P3、直接性、时效、独立来源和核验状态。
- 缓存说明：是否命中旧结果、是否刷新、是否识别到重复正文。
- 失败项：哪些 URL/字段失败，原因和可重试建议。
- 合规提醒：若涉及登录态、社交平台或反机器人页面，说明风险。

## References

- `references/capability-matrix.md`: 能力所有权、当前执行器、降级链和边界；维护本skill时先读。
- `references/route-policy.json`: 机器可读的路由优先级与触发规则。
- `references/source-quality.md`: P0-P3证据等级、评分和使用边界。
- `references/cache-and-dedup.md`: 缓存时效、隐私边界和去重命令。
- `references/router.md`: 通道选择、风险分级和组合打法。
- `references/anysearch.md`: AnySearch 搜索发现、垂直搜索、批量搜索和正文提取。
- `references/investment-search.md`: 投研搜索、小作文/传闻核验、订单/客户线索、产业链受益映射和证据矩阵。
- `references/scrapling-patterns.md`: Scrapling Fetcher、DynamicFetcher、StealthyFetcher、Spider 模板。
- `<your-skills-root>/agent-reach/SKILL.md`: 平台能力路由、健康检查及各平台命令参考。
- `scripts/firecrawl_client.py`: Firecrawl 云 API 薄封装（仅 scrape schema 提取 + map），需 `FIRECRAWL_API_KEY`。

## 一条重要的调试经验：不要相信"status: ok"

这条经验来自一次真实的全链路体检，值得沉淀成一般方法论：**诊断脚本的"已安装"检查，不等于"当前真的能用"**。

实测中发现过几类典型问题，模式都类似：

- 某个搜索通道的健康检查只确认了"账号已注册/配置文件存在"，从未真正验证过一次搜索请求确实返回了结果——直到真的执行一次端到端调用，才发现它其实从来没跑通过。
- 一个平台的登录态健康检查，测的是"公开接口是否可访问"，而公开接口不需要登录也能通过；这不能证明真正需要登录态的接口（比如查看需要登录才能看到的内容）也是通的——两者必须分开验证。
- 一个第三方浏览器自动化组件"已安装 Python 包"不等于它依赖的浏览器内核也已经下载好，直到实际渲染一个 JS 页面才会暴露出来。

**这次体检的方法论，建议作为通用习惯保留**：不轻信任何一处"status: ok"，逐条拿真实请求跑一遍，且要挑真正依赖该能力的调用去测（公开接口和需登录接口必须分开验证，健康检查脚本自带的探测项，很可能只测了最弱的那条路径，不能代表全部）。诊断脚本的静态检查只能证明"文件/配置存在"，不能证明"链路真的通"。
