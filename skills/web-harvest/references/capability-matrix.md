# Web Harvest Capability Matrix

本文件是联网能力登记表。它描述“谁负责什么”和降级顺序；实际可用状态以 `scripts/doctor.py` 及目标skill自己的doctor为准。

## 能力所有权

| 任务形态 | 主执行器 | 第二通道 | 最终兜底 | 边界 |
|---|---|---|---|---|
| 通用实时搜索 | AnySearch MCP | AnySearch CLI | Agent Reach Exa / 内置web | Exa偏英文技术语义，不替代中文通用搜索 |
| 垂直领域发现 | AnySearch `get_sub_domains` + search | 通用搜索定位官方源 | 领域专用skill | 金融结构化数据不要由搜索结果充当真值 |
| 英文技术/代码语义 | Agent Reach Exa | AnySearch code/tech | GitHub/官方文档 | 代码事实最终回到仓库、release或官方文档 |
| 已知静态URL | 内置web / AnySearch extract | Jina Reader | curl / Scrapling Fetcher | 提取失败先判断内容类型与登录要求 |
| 官方原文核验 | 内置web直读官方页 | Jina/curl | web-access | 搜索摘要只定位，不直接证明 |
| 登录态/交互页面 | web-access | Agent Reach健康登录后端 | 用户浏览器人工协助 | 不自动导出或持久化Cookie |
| 动态公开页面 | Scrapling DynamicFetcher | web-access | 站点公开API | 少量交互优先浏览器，批量优先Scrapling；**2026-09-07 修复**：Playwright浏览器内核此前从未下载，`doctor.py`旧版只查包能否import就报ok，实际调用直接抛异常——已跑`playwright install chromium`修复，`doctor.py`已加浏览器缓存目录检查，不再误报 |
| 批量/分页采集 | Scrapling Spider | 公开API/定制脚本 | 小批量浏览器 | 先样本验证，必须节流与checkpoint |
| 网页挂的PDF/DOCX | 下载后交给 `pdf` skill | Scrapling/web-access取到下载链接 | 手动下载 | 已有功能完整的pdf skill（提取/OCR/表格），此前只是没接进本路由——遇到URL直接是PDF或页面上的财报PDF链接时，下载后调用`<your-skills-root>/pdf/SKILL.md`，不要只读页面HTML漏掉PDF内容 |
| 网页Schema结构化提取 | Firecrawl云API `scrape` | 手写选择器+模型摘要 | — | `scripts/firecrawl_client.py scrape`，需`FIRECRAWL_API_KEY`；给字段定义直接拿JSON，比CSS选择器更抗页面结构变化；无key时走手写选择器兜底 |
| 全站URL发现/竞品页面盘点 | Firecrawl云API `map` | AnySearch site:搜索 | Scrapling Spider先浅抓 | `scripts/firecrawl_client.py map`，需`FIRECRAWL_API_KEY`；`--search`关键词按相关度排序，适合"这个站有多少定价页"这类问题，抓正文前先用它摸清规模 |
| YouTube | Agent Reach `yt-dlp` | web-access | 内置web找文字稿 | 优先字幕；无字幕转录需额外模型/Key |
| B站 | Agent Reach健康后端 | web-access | B站公开搜索API | 默认不用yt-dlp读取B站 |
| RSS/Atom | Agent Reach `feedparser` | curl/XML解析 | 内置web | 保存发布时间和原始链接 |
| V2EX | Agent Reach公开API | 内置web | web-access | 公开API只读 |
| GitHub | Agent Reach `gh` | git/curl GitHub API | 内置web | 私有仓库与写操作需要明确认证授权 |
| X/Reddit/小红书等 | Agent Reach健康后端 | web-access | AnySearch公开发现 | 登录态、高频访问存在账号风控 |
| A/H/美股结构化数据 | stock-data | 交易所/监管官网 | web-harvest补网页来源 | T0/T1以结构化源为准 |
| 卖方研报/纪要 | BRM | 官方公告/公司材料 | web-harvest找公开来源 | BRM不是T0行情源，观点按P2处理 |
| 微信/知乎/雪球仅归档 | wechat-article-to-markdown | web-access | 明确失败 | 默认进入Inbox，不自动研究化 |
| 投研小作文核验 | web-harvest investment-search | BRM线索 + stock-data | 登录浏览器/本地语言搜索 | 必须输出原子主张、证据矩阵和反证 |

## 错误降级

| 错误 | 处理 |
|---|---|
| 参数/schema错误 | 读取对应skill文档或子命令help，修正一次 |
| 401/403 | 区分未登录、Key无效和权限不足；不把匿名失败误报成Key过期 |
| 402配额 | 切备用搜索；免费日额度通常等待重置，不强迫用户重建Key |
| 429限流 | 按retry-after退避，降低并发；仍失败换通道 |
| DNS/TLS/超时/5xx | 记录真实错误，换独立后端；不要连续轰炸同一服务 |
| WAF/验证码 | 少量用户授权访问转web-access；批量任务暂停并评估合规性 |
| 空结果 | 改写查询、换本地语言、加否定词/实体名；仍为空则报告未找到 |
| 内容不完整 | 回原始页面、附件、PDF或平台原生后端，不用搜索摘要补写缺失事实 |

## 质量控制层

| 能力 | 文件/命令 | 作用 |
|---|---|---|
| 确定性路由 | `references/route-policy.json`、`scripts/route.py` | 给复杂请求提供可审计的主路由与补充通道 |
| 路由回归 | `scripts/route_regression.py` | 每次修改路由后检查20个核心场景 |
| 行为评测 | `evals/evals.json` | 对照新旧skill是否真的按规则选择工具 |
| 来源评分 | `scripts/source_quality.py` | 记录P0-P3、直接性、时效和独立验证，不提升证据等级 |
| 缓存去重 | `scripts/cache.py` | 规范化URL、缓存查询元数据、识别重复正文和Obsidian归档去向 |

## 维护原则

1. 新工具先确定所有权和替代关系，再加入矩阵；不要只在主skill追加一段广告式说明。
2. 工具安装不等于可用，必须有doctor或实际样本验证。
3. 主skill保持路由和不变量，具体命令放reference或窄skill。
4. 总规则、投资规则和项目文档只保留指向 `web-harvest` 的单一入口。
5. 路由策略变更必须通过回归用例；新增平台或工具时至少增加一个正例和一个冲突例。
