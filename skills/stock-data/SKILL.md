---
name: stock-data
description: 全市场结构化股票数据 Skill（A股+港股+美股）。用于行情、K线、估值历史(PE/PB/PS/PCF)、财报、研报、公告全文、资金流(分钟级)、龙虎榜、解禁/大宗交易/分红/股东户数、板块排名(行业/概念/地域)、题材归因、实时快讯、机构持仓、上市退市日期、筹码分布(获利比例/成本区间)、全A两融余额、个股融资融券、指数/ETF、技术指标、SEC EDGAR/XBRL、期权链、股票代码搜索、申万行业变迁史（避免回测前视偏差）和投研数据健康检查；另含量化研究的**批量数据湖**能力（baostock 5分钟线/日线+复权因子批量下载、同花顺 fuyao 全市场日K/复权事件 dump 与财务估值指数板块 REST 透传、数据湖盘点），是量化模型研究的数据总入口。结构化金融数据优先用本 skill；未知网页搜索、网页正文抓取、登录态页面和复杂爬虫交给 web-harvest。
origin: custom
version: 5.8.1
updated: 2026-11-05
---

# Stock Data

Use this skill as the first choice for structured market and financial data across A股、港股、美股. It is a data router plus executable tooling, not a generic web-search skill.

## Quick Start

Prefer the bundled runtime entry for repeatable queries. On first use it creates the
skill-local `.venv` from `requirements-runtime.txt`; later calls reuse it:

```bash
python3 scripts/run_stock_data.py quote 600519 00700 AAPL
python3 scripts/run_stock_data.py kline AAPL --period 6mo --interval 1d
python3 scripts/run_stock_data.py akline 600519 --count 250      # 腾讯 fqkline 前复权日K (A股/港股)
python3 scripts/run_stock_data.py longhubang --date 2026-09-03   # 全市场龙虎榜 (东财 datacenter)
python3 scripts/run_stock_data.py longhubang --code 002475 --days 30  # 个股上榜记录+席位
python3 scripts/run_stock_data.py margin 600519 --days 30        # 个股融资融券日级明细
python3 scripts/run_stock_data.py marketmargin --days 20         # 全A两融余额历史(沪深北合计)
python3 scripts/run_stock_data.py chip 600519 --start 2025-01-01 # 筹码分布(获利比例/成本区间/峰值价)
python3 scripts/run_stock_data.py search "英伟达"                 # 腾讯 smartbox 全球代码搜索
python3 scripts/run_stock_data.py swindustry --code 000001 --asof 2016-01-01  # 当时申万行业(消除前视偏差)
python3 scripts/run_stock_data.py valuation 600519 --start 2016-01-01  # PE/PB/PS/PCF历史(baostock,不支持北交所)
python3 scripts/run_stock_data.py basic 600519                    # 上市/退市日期与状态
python3 scripts/run_stock_data.py newsflash --count 20           # 全市场实时快讯(东财)
python3 scripts/run_stock_data.py corpaction 600519 --type lockup
python3 scripts/run_stock_data.py announcements 600519 --count 20
python3 scripts/run_stock_data.py holders AAPL                   # 机构持仓(仅美股/港股)
python3 scripts/run_stock_data.py fundflow 600519
python3 scripts/run_stock_data.py boardrank --kind concept
python3 scripts/run_stock_data.py hotstocks
python3 scripts/run_stock_data.py indicator 600519 --type macd
python3 scripts/run_stock_data.py options AAPL
python3 scripts/run_stock_data.py reports 600519
python3 scripts/run_stock_data.py sec AAPL --metrics Revenues NetIncomeLoss EarningsPerShareDiluted
python3 scripts/run_stock_data.py healthcheck
# —— v5.8 量化数据湖（详见「⑩」一节）——
python3 scripts/run_stock_data.py lake                            # 数据湖盘点：已下载/缺口/日期范围
python3 scripts/run_stock_data.py bulk --kind 5m --workers 4      # baostock 批量 5分钟线(不复权, 可断点续传)
python3 scripts/run_stock_data.py bulk --kind daily --workers 4   # 日线 + 复权因子
python3 scripts/run_stock_data.py thsdump daily-k                 # 同花顺全市场10年日K：默认只查大小不下载
python3 scripts/run_stock_data.py thsdump daily-k --confirm-download
python3 scripts/run_stock_data.py ths /api/meta/tickers/search --param q=600519 --param limit=1
```

Use inline snippets from references only when the CLI does not cover the request.

## Routing

- **Realtime quotes / valuation snapshot**: use `scripts/run_stock_data.py quote`. `status` / `acquisition_status` only means a quote was acquired; use `freshness_status` and `t0_eligible` separately for timeliness.
- **K-line / technical indicator input**: use `scripts/run_stock_data.py kline`; `--count N` means at most the latest N valid, date-sorted bars after invalid-row removal and date de-duplication. For advanced indicators read `references/a-stock-data-v5-full.md` section `Layer 10.1`.
- **A股 research data**: use Tencent, Eastmoney datacenter/reportapi, 同花顺, 巨潮, mootdx patterns in `references/a-stock-data-v5-full.md`.
- **A股/港股 K线（前复权）**: use `scripts/run_stock_data.py akline <code>`（腾讯 fqkline）; 美股/指数仍走 `kline`（Yahoo）。`akline` 与 `kline` 对 A股/港股等价，`kline` 内部已自动路由到 fqkline。
- **龙虎榜（全市场 / 个股）**: use `scripts/run_stock_data.py longhubang`（东财 datacenter-web `RPT_DAILYBILLBOARD_DETAILSNEW` + 席位 `RPT_BILLBOARD_DAILYDETAILSBUY/SELL`）。
- **个股融资融券日级明细**: use `scripts/run_stock_data.py margin`（东财 datacenter-web `RPTA_WEB_RZRQ_GGMX`）。
- **A股市资金流 / 多股指标对比 / 个股资讯聚合**: TDX MCP 可用时优先补位（见下方优先级第 6 条），不可用回退东财/Tencent。
- **港股 / 美股 deep data**: use Yahoo, Eastmoney GMAININDICATOR, SEC, options and institutional holder patterns in `references/global-stock-data.md` or `references/a-stock-data-v5-full.md`.
- **SEC official data**: use `scripts/run_stock_data.py sec` first; read `references/a-stock-data-v5-full.md` section `10.8` if more fields are needed.
- **Options chain**: use Yahoo options reference; applies to US stocks only.
- **量化研究批量数据 / 数据湖 / 5分钟线 / 复权因子 / 同花顺全市场日K / 历史成分 / 数据源分工**: read section `⑩` below; use `bulk` / `thsdump` / `ths` / `lake`. 历史时点指数成分本 CLI 不提供，需自备数据源（见 ⑩）。
- **Unknown source discovery, news article extraction, login pages, dynamic crawling**: route to `web-harvest`, then return here for structured market/financial data.

## Market Normalization Rules

The CLI normalizes common inputs:

- A股: `600519`, `600519.SH`, `SH600519`, `000001.SZ`
- 港股: `00700`, `700`, `0700.HK`, `HK00700`
- 美股: `AAPL`, `NVDA`, `BRK.B`
- Indices: Yahoo symbols such as `^GSPC`, `^HSI`

Important: pure numeric Hong Kong tickers are ambiguous with A股 codes. The CLI treats 1-5 digit numeric inputs as 港股 only when they are not 6-digit A股 codes; `00700` and `700` therefore route to 港股 correctly.

## Quote And K-Line Contracts

- Quote keeps source `market_at` and collection `retrieved_at` distinct. Tencent's A/H wall-clock field is localized with the corresponding IANA timezone; Tencent US remains `unknown` because that field's timezone is not verified. Yahoo `regularMarketTime` is handled as a Unix epoch and retained separately as `market_time`.
- Freshness values are `fresh`, `latest_close`, `stale`, `future`, or `unknown`. Automatic T0 eligibility requires a verifiable timezone and an exact exchange mapping backed by the pinned `exchange_calendars` runtime. The requested date window must also fall inside that calendar instance's advertised `first_session`/`last_session` coverage; uncovered dates fail closed as `unknown` and never count as holidays. Shanghai (`XSHG`), Hong Kong (`XHKG`), NYSE (`XNYS`), and Nasdaq (`XNAS`) are mapped separately. Shenzhen, Beijing, unknown Yahoo exchange codes, and Tencent US wall-clock timestamps remain `unknown`; no weekday-only or synonymous-exchange fallback is allowed.
- Top-level quote `as_of` is emitted only when calendar-certified quotes belong to one market. Mixed markets remain separated in `as_of_by_market`; their timestamps are never compared as strings to manufacture one global time.
- K-line `count` must be a positive integer and limits output to at most N valid bars. Output includes `requested_count`, `source_returned_count`, `source_valid_count`, `available_valid_count`, `returned_count`, invalid/duplicate counts, and `source_order`; the Tencent request parameter and exact response key are preserved. A/H minute K-lines remain rejected before any request.

The standard quote route uses Tencent for A/H and Yahoo for US so a verified Yahoo epoch,
timezone, and exact US exchange can reach calendar certification. If Yahoo fails, Tencent US
remains an acquisition fallback but its freshness stays `unknown`. To temporarily roll back
to the prior interpreter behavior without removing the isolated runtime, set
`STOCK_DATA_USE_SYSTEM_PYTHON=1` when invoking `scripts/run_stock_data.py`; missing calendar
support then fails closed instead of certifying a quote.

## Data Source Priority

### A股

1. Tencent quote API: realtime price, PE/PB, market cap, turnover, limit up/down.
2. Eastmoney datacenter/push2/reportapi: reports, 龙虎榜, 解禁, 两融, 大宗交易, 股东户数, 分红, funds flow, sectors.
3. 巨潮 cninfo: official announcements.
4. 同花顺 / 百度股市通: thematic reason tags, northbound realtime cache, concepts, K-line with MA.
5. mootdx: K-line, L2-like quote, F10 and finance snapshot when TCP access is available.
6. 通达信 MCP（connector/专家会话暴露时可用，仅作为补充源）: `tdx_indicator_select`（估值/财务指标，支持多股对比）、`tdx_screener`（主力净流入/DDX 资金流）、`tdx_quotes`（盘口）、`tdx_kline`（K线）、`wenda_news_query` / `wenda_notice_query`（个股资讯与公告聚合）。定位：指标对比、资金流、资讯聚合上补 1-5 的缺口。未暴露或调用失败时按降级惯例走 1-5，如实记录不可用原因，不得声称"数据不存在"。

### 港股

1. Tencent `hk` quote API for realtime quote and valuation fields.
2. Yahoo Finance for K-line, financials, key stats and indices.
3. Eastmoney `116.xxxxx` as quote/fundamental fallback.

### 美股

1. Yahoo Finance for K-line, key stats, financials, analyst estimates, options and indices.
2. SEC EDGAR for official filings and XBRL.
3. Tencent/Eastmoney as quote fallbacks.

## v5.3 变更（2026-09-04，对照上游 a-stock-data V3.7.2 审计后的修复+新增）

**① 修复：A股北交所 920 号段路由 bug**
`normalize_ticker()` 原逻辑 `code.startswith(("6","9"))→sh` 判定在 `code.startswith(("8","4"))→bj` 之前，
会把 2023 年后启用的北交所新号段 `920xxx` 误吞进上证（`sh920001`，应为 `bj920001`）。已改为先判北交所
`("4","8","92")` 再判上证，900xxx（上证 B 股）不受影响。此 bug 与上游 v3.5.1/v3.6.0/v3.7.2 反复修的
号段判定问题同源，交叉审计时发现，非上游代码直接复用。

**② 修复：`search`（股票代码搜索）失效**
原东财 `searchapi.eastmoney.com/api/suggest/get?type=14` 端点已被后端改造为股吧用户/帖子搜索，
对任意输入返回同一份缓存结果，`resp.json()` 因 JSONP 包裹直接报错。改用腾讯 smartbox
（`smartbox.gtimg.cn/s3/`，与 A股/港股/美股行情同一数据源体系，零鉴权），已验证中/英文、
A/港/美股查询正常。上游项目本身也没有独立的股票名称搜索端点（只有需付费 key 的 iwencai 语义搜索），
此修复是本 skill 自建能力的自我修复，不是从上游同步。

**③ 新增：申万行业分类变迁史（CLI: `swindustry`）**
消除行业轮动回测/归因的前视偏差——查"某股票在某历史日期属于哪个申万行业"，而不是"现在属于哪个"。
零第三方 pip 新依赖（复用系统已装的 pandas/xlrd/openpyxl）。数据源 `swsresearch.com` 官方 xls，
服务端只发叶子证书、遗漏中间证书（`GeoTrust G2 TLS CN RSA4096 SHA256 2022 CA1`），已从叶子证书的
Authority Information Access 字段取官方补链地址修复验证（非 `verify=False` 关闭校验）。磁盘缓存 7 天，
避免每次拉 1.1MB。验证案例（与上游一致）：平安银行 2013/2016/2026 分属银行(440101)→银行(480101)→
银行-国有大型(480301)，反映历次行业重分类。

**④ 腾讯 fqkline — A股/港股 前复权 K线（CLI: `akline`）**
- 基址：`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get`，参数 `param=<sym>,<period>,<start>,<end>,<count>,<末位flag>`（6 字段）。
- 符号：A股 `sh600519` / `sz000001`；**港股 `hk00700`，不是 `r_hk00700`**（后者返回空）。
- 前复权日线：末位传 `qfq` → 返回键 `qfqday`；不复权日线末位传 `9` → 返回键 `day`。
- **行结构（实测）**：A股 `[date,open,close,high,low,vol]` 仅 6 字段，**无 amount**；港股 7 字段（第 7 为事件 dict）。代码不要取 `row[7]`。
- 失败模式：美股 / 指数调用返回空，必须走 `yahoo_kline`。

**⑤ 东财 datacenter-web — 龙虎榜 / 融资融券 / 解禁 / 大宗 / 分红 / 股东户数（CLI: `longhubang` / `margin`）**
- 基址：`https://datacenter-web.eastmoney.com/api/data/v1/get`，统一 `reportName` + `filter` + `sortColumns`/`sortTypes` + `pageSize` 模式。
- 已验证 reportName：`RPT_DAILYBILLBOARD_DETAILSNEW`(龙虎榜) / `RPTA_WEB_RZRQ_GGMX`(两融) / `RPT_LIFT_STAGE`(解禁) / `RPT_HOLDERNUMLATEST`(股东户数) / `RPT_SHAREBONUS_DET`(分红) / `RPT_DATA_BLOCKTRADE`(大宗) / 席位 `RPT_BILLBOARD_DAILYDETAILSBUY`/`SELL`。
- 通用 helper `eastmoney_datacenter(report_name, columns, filter_str, page_size, sort_columns, sort_types)` 已就位，后续新增同类端点直接复用即可（不要另起炉灶）。

## ⑥ 新增：baostock 估值历史 + 上市退市日期（CLI: `valuation` / `basic`）

作者 2026-09-04 已确认安装 `baostock`（装在系统 python3，非 `quant-check` 隔离 venv）。

- **踩过一次坑，记录下来避免重犯**：上游文档写的入口函数是 `query_estimate_detail`，实测
  `hasattr(bs, 'query_estimate_detail')` 为 `False`——**这是 WebFetch 对上游文档做 AI 摘要时的幻觉**，
  上游申万行业史的下载 URL 之前也被同一层摘要编造过一次（错成 `shenwan.com.cn/download/...`，
  真实地址是 `swsresearch.com/swindex/pdf/...`）。真实可用入口是 `query_history_k_data_plus`，
  传 `fields="date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn,tradestatus,isST"` +
  `adjustflag="3"`（不复权，估值比率要对真实收盘价而非复权价）。**教训：涉及第三方库的具体
  函数名/参数，装包后必须用 `hasattr`/`dir()` 实测确认，不能只信任何层级的文档转述。**
- `query_stock_basic` 字段名（`code_name`/`ipoDate`/`outDate`/`status`）文档转述是对的，已用真实
  退市样例核实（`sz.000003` PT金田A，1991-07-03 上市、2002-06-14 退市、status=0）。
- **不支持北交所**（baostock 服务端报错码 10004011），`_bs_code()` 提前拦截给出明确报错，不静默失败。
- baostock 登录/登出默认往 stdout 打横幅，`_bs_session` 已用 `contextlib.redirect_stdout` 吞掉，
  不会污染 CLI 的 JSON 输出。

## ⑦ 新增：公告 / 解禁大宗分红股东户数 / 资金流 / 板块排名 / 题材归因 / 机构持仓 / 快讯

2026-09-04 二次审计后按作者选定优先级接入（公告类 / 解禁类 / 板块热点类 / 资金流机构持仓类，
未选技术指标/期权链/研报，这三类 CLI 仍未接）：

- **`announcements`**（巨潮公告全文）：org_id 构造已应用 920 号段修复（同 `normalize_ticker` 教训）。
  已知边界：688 科创板部分标的（688017 验证）返回 0 条，主板 600519 同结构返回 1684 条，怀疑
  科创板 org_id 前缀或需额外 `plate` 参数，未查清——遇到 688 段查询为空不要断言"无公告"，改用
  `web-harvest` 核实官网。
- **`corpaction --type {lockup,block,dividend,holders}`**（解禁/大宗交易/分红/股东户数）：复用已有
  `eastmoney_datacenter` helper，四个 `reportName` 过滤字段实测统一是 `SECURITY_CODE="..."`。
- **`holders`**（机构持仓，仅美股/港股）：Yahoo quoteSummary + crumb session，`fc.yahoo.com` 首步
  404 不影响后续拿 crumb（只是种 cookie，非硬依赖）。
- **`newsflash`**（全市场快讯）：见下方"断点①已修复"。
- **`fundflow` / `boardrank` / `hotstocks`**：见下方"关键发现：push2delay"。

## 关键发现：`push2delay.eastmoney.com` 是 `push2`/`push2his` 的可用替身

`push2.eastmoney.com` 和 `push2his.eastmoney.com`（裸域名）从本沙箱网络当前**连接级不可达**
（`Remote end closed`，非签名/参数问题，换 UA/Referer/间隔重试均无效），但**同一 API 家族的延迟行情
域名 `push2delay.eastmoney.com` 实测连通**，且 `clist/get`（板块排名）与 `stock/fflow/kline/get`
（分钟级资金流）两个端点在该域名下返回的数据结构和裸 `push2` 完全一致。已验证：

- **`boardrank --kind industry`**：行业板块通过 `push2delay` 可用（`m:90 t:2`，示例：畜禽饲料
  8.46%、生猪养殖 6.23%）。**此前审计报告说"行业板块缺可靠替代"、"概念/地域能通只有行业不通"，
  实测证伪——问题从来不是行业板块本身，是裸 `push2` 域名连接不通，换 `push2delay` 三种 `fs`
  （行业/概念/地域）全部可用。**
- **`fundflow`**（个股分钟级资金流）：`push2delay` 同样可用，主力/超大单/大单/中单/小单净流入
  字段（f51-f57）与文档一致。
- **日级（120日）资金流暂无法接入**：对应端点在 `push2his.eastmoney.com/api/qt/stock/fflow/
  daykline/get`，`push2hisdelay.eastmoney.com` 不是真实 API 域名（返回东财官网 HTML 跳转页，
  不是 JSON），没找到日级的可用替身域名。只接了分钟级，晚点想再查日级路由。

## 已修复 / 已确认的断点（2026-09-04 二次审计交叉验证）

- **① 财联社电报 404 → 已修复**：换东财 `np-weblist.eastmoney.com/comm/web/getFastNewsList`
  （`newsflash` 命令），实测返回真实快讯含关联股票代码，与个股新闻同一服务簇。
- **② 东财 push2 行业板块「缺可靠替代」→ 已修复**：见上方 push2delay 发现，`boardrank` 三种
  `kind` 全部可用。
- **③ 同花顺 basic/worth**：HTTP 200 但响应体为空，功能性等同不可用，估值数据已被
  腾讯/东财/baostock（`valuation`）完全覆盖，不需要单独修。
- **④ Yahoo v7 query1 quote**：401 需要 cookie。CLI 一直用的是 `v8/finance/chart`，已验证正常，
  从未受影响。

## ⑧ 新增：技术指标 / 期权链 / 东财研报（2026-09-04，原「暂不接入」清单已收口）

- **`indicator --type {ma,macd,rsi,kdj,boll}`**：纯本地计算，不调用新数据源，内部复用已有 `kline`
  路由（A股/港股走腾讯 fqkline、美股/指数走 Yahoo）自动取 K 线再算，不用先拉数据再传参。三个市场
  （A股600519/美股AAPL/港股00700）均实测验证。
- **`options`**（期权链，仅美股）：复用 `holders` 已建的 Yahoo crumb session，`v7/finance/options`
  端点带 crumb 认证可用（注意：与之前判定「已断」的 `v7/finance/quote` 是不同端点，那个没有
  crumb 认证会 401，这个有 crumb 认证就正常）。
- **`reports`**（东财研报列表）：卖方观点 **P2**，含评级/EPS预测（今年/明年/后年）/PE预测/目标价，
  引用时必须标机构+日期，不得把评级或预测写成既定结论。未接 PDF 下载（写文件产生副作用，不适合
  JSON-输出的 CLI；需要原文时用 `pdf_url` 字段单独取）。

## ⑨ 新增：筹码分布 / 全A两融余额（2026-09-04）

- **`chip`**（筹码分布，不支持北交所）：**自己按公开通用算法实现，不是转述第三方代码**——本会话
  用 WebFetch 查上游筹码分布实现时，摘要给的代码调用了一个未定义的 `_triangular_weights` 辅助函数，
  无法验证正确性（本会话已两次抓到 WebFetch 对第三方文档摘要时编造细节：申万行业史下载 URL、
  baostock 函数名），这次直接不采信，自己写。算法：每日成交按换手率对现有筹码分布做"以新换旧"
  混合，新增部分在当日 `[low, high]` 区间按三角分布（峰值在 `(high+low+close)/3`）撒开，数据源
  用已验证的 baostock 一次性拿 `date/high/low/close/turn`。茅台样例验证：现价低于筹码峰值价时
  获利比例走低（14.63%），逻辑自洽。
- **`marketmargin`**（全A两融余额历史，沪深北合计）：真实 `reportName`（`RPTA_RZRQ_LSHJ`）**没有
  出现在任何公开文档里**，是这次现场反查东财两融页面 `/newstatic/js/rzrq/default.js` 里的字符串
  找到的（猜测报表名试了 9 个变体全部失败后改的这个方法）；同一页面还暴露了 `RPTA_RZRQ_LSDB`
  （沪深北分市场对比，含 `H_/S_/B_/TOTAL_` 前缀分组字段，需要更细颗粒度时可用）。
- **个股融资融券余额**已被 v5.2 的 `margin` 命令覆盖（`rz_balance_yuan` 字段），不是这轮新增。

## ⑩ 新增：量化数据湖（v5.8.0，2026-09-29，CLI: `bulk` / `thsdump` / `ths` / `lake`）

面向量化模型研究的**批量、可复现、落盘**数据入口。实现在 `scripts/bulk_data.py`，离线测试 `scripts/test_bulk_data.py`。
与上面「查一下」类命令不同：这里的产物是本地 parquet 数据湖，供因子研究与回测反复读取。

**数据湖**：环境变量 `STOCK_DATA_LAKE`，默认 `~/quant_data`（不放 iCloud）。

| 路径 | 内容 |
|---|---|
| `raw/bs_5m/<code>.parquet` | baostock 5 分钟线，**不复权**，字段 `date,code,open,high,low,close,volume,amount,dt` |
| `raw/bs_daily/<code>.parquet` | baostock 日线，**不复权**，含 `turn,tradestatus,isST,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM` |
| `raw/bs_daily/<code>_adj.parquet` | baostock 复权因子（分红事件日） |
| `raw/ths/<kind>_<yyyymmdd>.parquet` | 同花顺 dump：`daily-k`(全市场10年日K,未复权,约1031万行,起自2016-09-28,181MB) / `daily-k-10d`(近10日增量) / `adjustment-factors`(分红送股配股事件,约5.7万行) |
| `meta/universe_union_2020_2026.csv` | 下载名单 `code,name,indices,first_in,last_out,current`（见下） |
| `logs/bs_<kind>_progress.csv` | 下载日志 `ts,code,status,rows,secs,note`，`status∈ok/skip/empty/error` |

**硬约定（回测正确性）**：价格一律存**不复权**原价，复权因子另存，回测自行复权，不用 baostock 前复权价（会随新分红事件漂移）。

**bulk（baostock 批量）**
- 断点续传：目标 parquet 已存在则跳过；写入先 `.tmp` 再原子改名；失败自动重试并断线重登。
- 下载窗口：现成分 `[first_in-365d, 今天]`；已剔除 `[first_in-365d, last_out+90d]`；下限 5m=**2020-01-02**、daily=2018-01-01。
- 实测数据：5 分钟线单只全历史约 90 秒/7.8 万根，每天 48 根；并行 4 进程约 3.5 倍吞吐，偶发 `10001001` 已由重试吸收。日线约 5–7 秒/只。
- **1 分钟线不支持**（baostock 错误码 10004012）；5 分钟线**最早只到 2020-01-02**（文档称 2015 起，实测不成立）。更早或更细的分钟数据需券商 miniQMT `xtquant`（开通后再接）。
- 北交所不支持（同 `_bs_code`）。
- **限流/黑名单（2026-09-29 踩坑，必读）**：同时开 3 个 `bulk`（5m×4 + daily_pre×2 + daily_gap×1，共 7 个 baostock 会话，约 70 任务/分钟）运行约 10 分钟后，本机 IP 被 baostock 列入黑名单（`10001011:黑名单用户，请与管理员联系`，按 IP 而非账号——匿名登录无账号）。旧版遇错重试并继续，3 个进程连续重试约 1.7 小时（约 1190 次失败登录/查询），可能加重封禁。现已改：`--workers` 默认 2（勿超 4）；**同一时间只跑一个 `bulk`**；每只股票前停顿 0.5 秒；遇 10001011 立即熔断全部进程（状态 `blacklisted`，不重试）；连续 5 次出错也熔断。解除时长官方未公开，第三方工具的做法是等 6–12 小时（P3，未核实）。**恢复前先只做一次登录探测，失败就继续等，不要循环重试。**
- **探测请用 `bulk --probe`**（一次登录 + 一次极小查询，全程带超时，返回 `healthy`）。不要在 shell 里手写 `bs.login()`：baostock 0.9.x 自带的 `send_msg` 无超时，对端关闭连接时 `recv` 返回空字节、循环条件永不满足，**进程 100% CPU 空转看起来像「挂起」**（2026-09-29 在家宽/香港/手机热点三个出口都遇到，实为服务端立即断连，加固后 3.6 秒返回 `10002007 网络接收错误`）。`bulk_data.install_baostock_guards()` 已替换 `send_msg`：每次 recv 30 秒超时、空字节视为断连、单次请求 300 秒总时限，并新增熔断状态 `service_down`。三个出口表现一致，说明**当前不是单纯换 IP 能解决**（可能是服务端故障，第三方 issue HKUDS/Vibe-Trading#1492 记录过 2026-09-18/19 的类似服务端异常，今天是否同一问题未证实）。

**thsdump / ths（同花顺 fuyao，官方数据服务）**
- key：环境变量 `HITHINK_FINANCE_API_KEY`，或文件 `~/.config/quant/fuyao.env`（权限 600）。**永不回显、不写日志、不进对话**；`ths` 只允许 `/api/` 路径且固定 host。
- `thsdump` **默认只签出并查询文件大小**，加 `--confirm-download` 才真正下载（预签名 URL 约 5 分钟有效，仅进程内使用）。下载后校验为合法 parquet。
- dump 字段：日K `thscode,currency,interval,adjusted,date_ms,open_price,high_price,low_price,close_price,volume,turnover`（**没有换手率/停牌/ST**，这三项仍要靠 baostock 日线）；复权事件 `thscode,ticker,ex_date_ms,dividend_per_share,per_share_bonus,allotment_ratio,allotment_price,currency`。
- `ths` 透传 REST（信封 `{code,message,request_id,data}`，`code==0` 成功；1xxx/2xxx/3xxx 不重试，4001/5xxx 指数退避）。业务域：基础数据 `/api/meta/*`、A股（价格/财务/估值/竞价/涨跌停炸板龙虎榜热榜）、指数与板块、公募基金、期货期权。具体路径以官方文档 `https://github.com/HiThink-Tech/Financial-API/tree/main/docs/api` 为准，**大结果用 `--out` 落盘**。
- **边界**：同花顺公开接口**不提供分钟K/tick/Level-2**、港美股、新闻研报原文。

**lake**：盘点各目录文件数、行数（读 parquet 元数据）、体积、相对下载名单的缺口、抽样日期范围。

**数据源分工（量化研究）**

| 需求 | 首选 | 备注 |
|---|---|---|
| 日线（含换手率/停牌/ST/估值） | baostock `bulk --kind daily` | 同花顺日K dump 做**交叉验证**，不替代 |
| 5 分钟线 | baostock `bulk --kind 5m` | 仅 2020-01-02 起；更早或更细的数据需自备 |
| 复权 | 原价 + `_adj.parquet`，用同花顺 `adjustment-factors` 二次核对 | |
| **历史时点指数成分（防幸存者偏差）** | 需自备（例如付费数据库的历史成分接口） | 本 CLI 不提供；中证A500 仅自 2024-09-23 起有真实成分，更早的回测不能用它 |
| 历史行业分类 | `swindustry --asof` | 防前视 |
| 分钟级/逐笔 | 券商 miniQMT（待开通） | 未接入 |

**下载名单（需自备）**：`bulk` 读取 `meta/universe_union_2020_2026.csv`，本包不附带这份名单。建议对目标指数按半年取时点快照，再并上当前成分；不要依赖一次性的"历史成员"查询，这类接口常有单次条数上限，排在末尾的现成分可能被截断，导致纳入日缺失。`download_window` 已对非法或未来的纳入日退回下限，并有回归测试。


## 仍未接入（评估后确认不接，非遗漏）

| 能力 | 为什么没接 |
|---|---|
| 人民银行社融、国家统计局 PMI | 上游示例 URL 本身是按年份猜文件名 / 某月公告页面，非稳定端点，每次都要重新发现当期地址；更适合交给 `web-harvest` 动态查，不适合固化进 CLI |
| 复权因子 qfq/hfq（新浪，独立于K线） | 查询类场景用 `akline`（腾讯 fqkline，直接返回前复权价）已够；**回测场景改用「不复权原价 + 复权因子」**，见 ⑩ 数据湖（baostock `_adj` 与同花顺 `adjustment-factors`） |
| 涨停/炸板池、ETF期权希腊字母、互动易问答 | 纯本地计算或新数据源，技术上可加；偏日内交易/游资信号，与当前研究工作流（行业/公司/宏观深研为主）关联度低，需要时再评估 |
| 个股资金流日级(120日) | 见 push2delay 小节，无可用替身域名 |

## References

- `references/a-stock-data-v5-full.md`: full original endpoint cookbook and known pitfalls.
- `references/global-stock-data.md`: imported 美股/港股 deep-data cookbook.

Load only the relevant reference section for the user request. Do not load both large references unless the task explicitly spans A股 and 美/港 deep data.

## Reliability Rules

- Always report source and timestamp/market-delay assumptions for price-sensitive answers.
- For investment conclusions, separate official filings/announcements, market data, sell-side research, and model estimates.
- If one source fails, try the next source in the priority list before saying data is unavailable.
- For stale or high-stakes data, run `healthcheck` or a minimal live query before relying on the endpoint.
- Do not expose API keys. 同花顺 fuyao（`ths`/`thsdump`）与 iwencai 需要 key；key 只从环境变量或 `~/.config/quant/fuyao.env` 读取，不得在对话、日志、代码中出现；其余内置端点为零鉴权公开 API。
- 批量下载（`bulk`）与大文件下载（`thsdump --confirm-download`）属于长耗时/写盘动作：先向用户说明来源、体积与耗时再执行；下载数据一律进数据湖，不进知识库目录。
