---
name: stock-data
description: 全市场股票数据工具包（A股+港股+美股）— A股：行情(mootdx+腾讯+百度K线)、研报(东财+同花顺+iwencai)、信号(热点题材+北向+龙虎榜+解禁+行业)、资金面(融资融券+大宗交易+股东户数+分红+资金流)、新闻(东财+财联社)、基础数据(mootdx财务/F10+东财+新浪三表)、公告(巨潮)；港股：实时行情(腾讯hk+东财push2)、K线+财报(Yahoo Finance)、研报(东财)、恒生指数；美股：实时行情(腾讯us+东财push2)、K线+财报+关键指标(Yahoo Finance)、三大指数+VIX；美股/港股深度(V5.0新增)：技术指标(MA/MACD/RSI/KDJ/布林带纯Python)、东财GMAININDICATOR关键指标(美49/港75字段)、Yahoo分析师预期/评级/机构持仓、期权链、SEC EDGAR(Filing+XBRL财务+CIK)、Yahoo新闻、东财全球搜索、新浪美股超长K线；通用：Yahoo Finance支持A/港/美统一K线查询。十层架构，50+端点，内嵌全部调用代码，自包含零外部文件依赖。
origin: custom
version: 5.0
---

> 📦 项目主页：https://github.com/simonlin1212/a-stock-data — 更新、反馈、支持作者
> 
> 作者：Simon 林 · 抖音「Simon林」· 公众号「硅基世纪」

# 全市场股票数据工具包 V5.0

十层数据架构，50+ 端点，覆盖 A股/港股/美股，全部实测可用（A股层 2026-05-21 验证，V5.0 深度层 2026-06-04 验证）。

> **V5.0 新增（Layer 10 美股/港股深度层，蒸馏自 global-stock-data）：** 技术指标（MA/EMA/MACD/RSI/KDJ/布林带，纯Python，适用全市场）+ 东财 GMAININDICATOR 关键指标（美股49字段/港股75字段）+ Yahoo quoteSummary 深度（关键指标/分析师预期/评级趋势/机构持仓）+ 期权链（Yahoo，仅美股）+ SEC EDGAR（Filing列表/XBRL结构化财务503指标/Ticker→CIK，仅美股）+ Yahoo新闻 + 东财全球搜索 + 新浪美股超长K线（回溯1984年）+ Yahoo crumb 自动管理器。2026-06-04 实测 11 个联网端点全部通过。
>
> **V4.0 新增：** 港股层（腾讯hk+东财push2+Yahoo Finance K线/财报+恒生指数）+ 美股层（腾讯us+东财push2+Yahoo Finance K线/财报/三大指数+VIX）+ Yahoo Finance 通用K线（A/港/美统一接口）。
>
> **V3.1 修复：** 替换 4 个失效接口（百度 PAE 资金流→东财 push2、大宗交易 RPT 报表名更新、机构席位改用 BUY/SELL 明细筛选）+ 修复东财全球资讯 req_trace 参数 + 修复巨潮公告 orgId 格式。
>
> **V3.0 Breaking Change**：彻底移除 akshare 依赖，所有数据源改为直连 HTTP API（零第三方数据依赖，仅 mootdx 保留 TCP）。

**使用方式：** 将本文件放入 `~/.claude/skills/a-stock-data/SKILL.md`，Claude Code 会自动识别并在股票相关对话中激活（A股/港股/美股均触发）。

```
行情层（A股实时，不封IP）
├── mootdx        → K线 + 五档盘口 + 逐笔成交 (TCP 7709)
├── 腾讯财经 API   → PE/PB/市值/换手率/涨跌停/指数/ETF (HTTP, 同时支持hk/us前缀)
├── 百度股市通     → K线带MA5/10/20 (HTTP)
└── Yahoo Finance  → 通用K线，支持A股(600519.SS)/港股(0700.HK)/美股(AAPL)/指数(^GSPC) ★新增

研报层
├── 东财 reportapi → 研报列表 + PDF下载 + 评级 + 三年EPS
├── 同花顺 THS     → 一致预期EPS (直连 basic.10jqka.com.cn)
└── iwencai        → NL语义搜索研报 (唯一能力，需X-Claw)

信号层（A股）
├── 同花顺热点     → 当日强势股 + 题材归因 reason tags (零鉴权 73ms)
├── 同花顺北向     → hgt/sgt 分钟资金流向 + 本地自缓存历史
├── 百度股市通     → 概念板块归属 (HTTP)
├── 东财 push2     → 个股资金流向 分钟级
├── 龙虎榜席位     → 上榜记录 + 买卖席位 TOP5 + 机构动向 (datacenter-web)
├── 全市场龙虎榜   → 每日全市场上榜股票 + 净买额排名 (datacenter-web)
├── 限售解禁日历   → 历史解禁 + 未来90天待解禁 (datacenter-web)
└── 行业板块排名   → 东财行业涨跌/上涨下跌家数

资金面 / 筹码层（A股）
├── 融资融券明细   → 日级融资余额/买入/偿还 + 融券 (datacenter-web)
├── 大宗交易       → 成交价/量 + 买卖方营业部 (datacenter-web)
├── 股东户数变化   → 季度股东户数 + 环比变化 (datacenter-web)
├── 分红送转       → 历史每股派息/送股/转增 (datacenter-web)
└── 个股资金流120日 → 主力/大单/中单/小单 日级净流入 (push2his)

新闻层
├── 东财个股新闻   → 个股相关新闻 (search-api-web JSONP)
├── 财联社快讯     → 全市场实时电报 (cls.cn)
└── 东财全球资讯   → 7×24 财经快讯 (np-weblist)

基础数据层（A股）
├── mootdx finance → 季报快照 (37字段, EPS/ROE/净利)
├── mootdx F10     → 公司资料 (9大类文本)
├── 东财个股信息   → 行业/总股本/流通股/市值/上市日期 (push2)
└── 新浪财报三表   → 资产负债表/利润表/现金流量表 (quotes.sina.cn)

公告层（A股）
├── 巨潮 cninfo    → 公告全文检索+下载 (cninfo.com.cn)
└── mootdx F10     → 最新公告摘要

港股数据层 ★新增
├── 腾讯财经 hk前缀 → 实时行情 PE/PB/市值/涨跌幅 (hk00700格式)
├── 东财 push2      → 实时行情 (secid 116.XXXXX格式)
├── Yahoo Finance   → K线 + 财务关键指标 + 分析师目标价 (0700.HK格式)
├── 东财 reportapi  → 港股研报列表 (同A股接口)
└── Yahoo Finance   → 恒生指数/恒生科技/恒生国企 (^HSI/^HSTECH/^HSCE)

美股数据层 ★新增
├── 腾讯财经 us前缀 → 实时行情 (usAAPL格式)
├── 东财 push2      → 实时行情 (secid 105/106.TICKER格式)
├── Yahoo Finance   → K线 + 利润表/现金流/资产负债表 + 关键指标
├── Yahoo Finance   → S&P500/道琼斯/纳斯达克/VIX/10Y美债 (^GSPC/^DJI/^IXIC/^VIX/^TNX)
└── 东财 reportapi  → 美股研报 (主要标的)

美股/港股深度层 ★V5.0新增（Layer 10，蒸馏自 global-stock-data）
├── 技术指标       → MA/EMA/MACD/RSI/KDJ/布林带 (纯Python，吃任意市场K线)
├── 东财 GMAININDICATOR → 中文关键指标 ROE/毛利率/资产负债率 (美49/港75字段)
├── 东财 datacenter → 美股/港股财报三表 (中文科目，按行展开)
├── Yahoo quoteSummary → 关键指标(英文) + 分析师EPS预测/评级/升降级 + 机构持仓
├── Yahoo options  → 期权链 calls+puts (仅美股)
├── SEC EDGAR      → Filing列表 + XBRL结构化财务(503指标) + Ticker→CIK (仅美股)
├── Yahoo search   → 美股/港股新闻
├── 东财 search    → 全球股票搜索 + secid映射
└── 新浪财经       → 美股超长K线 (回溯1984年)
```

## When to Activate

**A股触发场景：**
- 用户要查 A 股个股估值（一致预期 / PE / PEG / PE消化）
- 用户要拉实时行情（价格 / 五档盘口 / K线 / 涨跌停价）
- 用户要搜研报（按主题 / 按标的 / 按行业 / 下载PDF）
- 用户要看**当日强势股 / 题材归因 / 概念热点**
- 用户要看**北向资金动向**（沪股通/深股通分钟流向）
- 用户要看**概念板块归属**（行业/概念/地域）
- 用户要看**个股资金流向**（主力/散户/超大单/大单分钟级）
- 用户要看**龙虎榜席位**（营业部 + 机构买卖）
- 用户要看**全市场龙虎榜**（当日所有上榜股票 + 净买额排名）
- 用户要看**限售解禁日历**（历史解禁 + 未来待解禁）
- 用户要做**行业横向对比**（涨跌排名 / 资金流入 / 领涨股）
- 用户要看**融资融券 / 两融数据**（融资余额 + 融券余额）
- 用户要看**大宗交易**（成交价/量 + 买卖方营业部）
- 用户要看**股东户数变化**（筹码集中度）
- 用户要看**分红送转历史**（每股派息 + 送股 + 转增）
- 用户要看**指数/ETF行情**（上证指数 / 沪深300 / 创业板指 / ETF）
- 用户要看新闻资讯（个股新闻 / 财联社快讯 / 全球资讯）
- 用户要查公告（巨潮公告全文）
- 用户要做产业链调研 / 批量横向对比

**港股触发场景（★新增）：**
- 用户查港股行情（腾讯/阿里/美团/小米/比亚迪港股 / 恒生指数）
- 用户查港股估值（PE/PB/股息率/市值）
- 用户查港股K线 / 历史价格数据
- 用户查港股财报 / 财务指标
- 用户查港股研报
- 用户查恒生指数 / 恒生科技 / 恒生国企

**美股触发场景（★新增）：**
- 用户查美股行情（苹果/英伟达/特斯拉/微软 等）
- 用户查美股估值（PE/PB/EPS/股息率/Beta）
- 用户查美股K线 / 历史价格数据
- 用户查美股财报（利润表/资产负债表/现金流量表）
- 用户查三大指数（S&P500/道琼斯/纳斯达克）
- 用户查 VIX / 美债收益率 / 市场情绪指标
- 用户查分析师目标价 / 机构评级

**美股/港股深度场景（★V5.0新增 Layer 10）：**
- 用户要算**技术指标**（MA/MACD/RSI/KDJ/布林带 / 金叉死叉 / 超买超卖）— 任意市场
- 用户查美股/港股**关键财务指标**中文版（ROE/毛利率/净利率/资产负债率/流动比率，东财GMAININDICATOR）
- 用户查**分析师预期**（EPS预测 / 评级趋势 / 机构升降级历史）
- 用户查**机构持仓**（前十大机构 / 内部人持股 / 机构占比）
- 用户查**期权链**（calls/puts / 隐含波动率 / 未平仓量，仅美股）
- 用户查 **SEC 文件**（10-K/10-Q/8-K Filing / XBRL官方财务 / CIK查询）
- 用户查美股/港股**新闻**
- 用户要**搜索全球股票代码**（中英文 → secid/市场映射）

**关键词（A股）：** 估值、一致预期、机构预测、市盈率、PEG、市值、研报、产业链、行业研究、K线、盘口、公告、新闻、强势股、题材、热点、概念归因、北向资金、沪股通、深股通、概念板块、资金流向、主力、龙虎榜、席位、营业部、全市场龙虎榜、净买入、解禁、限售、行业对比、行业轮动、融资融券、两融、大宗交易、股东户数、筹码集中、分红、派息、送股、指数、ETF

**关键词（港股）：** 港股、恒生、HK、.HK、港元、00700、腾讯港股、港交所

**关键词（美股）：** 美股、纳斯达克、标普、道琼斯、AAPL、NVDA、TSLA、MSFT、S&P500、VIX、美债、美元、NYSE

---

## Prerequisites

```bash
pip install mootdx requests pandas stockstats
```

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| mootdx | >= 0.10 | TCP行情+财务+F10（唯一非HTTP依赖） |
| requests | any | 所有HTTP API直连 |
| pandas | any | 数据处理+HTML表格解析 |
| stockstats | any | 技术指标计算（RSI/MACD/BOLL等） |

> **V3.0 架构：** 除 mootdx（TCP 二进制协议）外，所有数据源均为直连 HTTP API，零第三方数据封装依赖。每个端点的底层 URL/参数完全暴露，方便调试和定制。

### iwencai API Key（仅语义搜索需要）

```bash
# 环境变量方式
export IWENCAI_API_KEY="your_key_here"
export IWENCAI_BASE_URL="https://openapi.iwencai.com"

# 申请地址: https://www.iwencai.com/skillhub
# 注册后安装 SkillHub CLI，再安装 report-search 技能即可获得 Key
```

其他数据源（mootdx / 腾讯 / 东财 / 同花顺 / 百度股市通 / 新浪 / 巨潮）全部免费，无需 key。

### 市场前缀规则（全局通用）

```python
def get_prefix(code: str) -> str:
    """6位代码 → 市场前缀"""
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    else:
        return "sz"
```

### Ticker 格式归一化（全市场）

```python
import re

def normalize_ticker(code: str) -> dict:
    """
    统一归一化 Ticker，自动识别市场。
    返回: {market, code, tencent_prefix, yahoo_ticker, eastmoney_secid}
    """
    code = code.strip()
    upper = code.upper()

    # === 港股识别 ===
    # 支持: 00700, 700, 0700.HK, HK00700, hk00700
    hk_match = re.match(r'^(?:HK|hk)?0*(\d{1,5})(?:\.HK)?$', upper)
    if code.endswith('.HK') or code.upper().startswith('HK') or (
        hk_match and not upper.startswith(('6','0','3','8','4','9')) and len(re.sub(r'\D','',code)) <= 5
    ):
        num = re.sub(r'[^0-9]', '', code).zfill(5)
        return {
            "market": "hk",
            "code": num,
            "tencent_prefix": f"hk{num}",
            "yahoo_ticker": f"{int(num)}.HK",
            "eastmoney_secid": f"116.{num}",
        }

    # === 美股识别 ===
    # 支持: AAPL, aapl, AAPL.O, AAPL.N
    us_match = re.match(r'^([A-Za-z]{1,6})(?:\.[ON])?$', code)
    if us_match and not re.match(r'^\d', code):
        ticker = us_match.group(1).upper()
        return {
            "market": "us",
            "code": ticker,
            "tencent_prefix": f"us{ticker}",
            "yahoo_ticker": ticker,
            "eastmoney_secid": f"105.{ticker}",  # NASDAQ 默认; NYSE 用 106.xxx
        }

    # === A股（默认）===
    num = re.sub(r'[^0-9]', '', code)
    if num.startswith(('6', '9')):
        prefix = 'sh'
    elif num.startswith('8') or num.startswith('4'):
        prefix = 'bj'
    else:
        prefix = 'sz'
    return {
        "market": "cn",
        "code": num,
        "tencent_prefix": f"{prefix}{num}",
        "yahoo_ticker": f"{num}.{'SS' if prefix=='sh' else 'SZ'}",
        "eastmoney_secid": f"{'1' if prefix=='sh' else '0'}.{num}",
    }

# A股输入格式兼容表（归一化为纯6位）:
# 688017 / SH688017 / 688017.SH / SZ000001 / BJ832000
# 港股格式: 00700 / 700 / 0700.HK / HK00700
# 美股格式: AAPL / aapl / AAPL.O / AAPL.N
```

### 东财数据中心统一查询（共用 helper）

龙虎榜/解禁/融资融券/大宗交易/股东户数/分红 共用同一 base URL：

```python
import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

def eastmoney_datacenter(report_name: str, columns: str = "ALL",
                          filter_str: str = "", page_size: int = 50,
                          sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    """东财数据中心统一查询 — 龙虎榜/解禁/融资融券/大宗交易/股东户数/分红 共用"""
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = requests.get(DATACENTER_URL, params=params, headers={"User-Agent": UA}, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []
```

---

## Layer 1: 行情层（实时，不封IP）

### 1.1 mootdx — K线 + 五档盘口 + 逐笔成交

TCP 二进制协议，连通达信服务器(7709)，无需注册，不封IP。

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')

# === K线数据 ===
# market: 0=深圳, 1=上海
# category: 4=日线, 5=周线, 6=月线, 7=1分钟, 8=5分钟, 9=15分钟, 10=30分钟, 11=60分钟
klines = client.bars(symbol='688017', category=4, offset=10)
# 返回: open, close, high, low, vol, amount, datetime

# === 实时报价 ===
quotes = client.quotes(symbol=['688017', '300476'])
# 返回 46 个字段:
#   price(现价), open, high, low, last_close(昨收)
#   bid1~bid5, ask1~ask5, bid_vol1~bid_vol5, ask_vol1~ask_vol5
#   vol(成交量), amount(成交额), servertime

# === 逐笔成交（非交易时间返回空）===
trades = client.transaction(symbol='688017', date='20260502')
# 返回: time, price, vol, num, buyorsell(0买/1卖/2中性)
```

**mootdx 不提供 PE / PB / 市值 / 换手率 / 涨跌停价** — 这些走腾讯财经。

### 1.2 腾讯财经 API — PE/PB/市值/换手率/涨跌停/指数/ETF

HTTP GET，GBK 编码，`~` 分隔 88 个字段，不封IP。

```python
import urllib.request

def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """
    批量拉取腾讯财经实时行情。
    codes: ["688017", "300476", "002463"]
    也支持指数: ["000001", "000300", "399006"]
    也支持ETF: ["510050", "510300"]
    返回: {code: {name, price, pe_ttm, pb, mcap, ...}}
    """
    prefixed = []
    for c in codes:
        if c.startswith(("6", "9")):
            prefixed.append(f"sh{c}")
        elif c.startswith("8"):
            prefixed.append(f"bj{c}")
        else:
            prefixed.append(f"sz{c}")

    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")

    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]
        result[code] = {
            "name":         vals[1],
            "price":        float(vals[3]) if vals[3] else 0,
            "last_close":   float(vals[4]) if vals[4] else 0,
            "open":         float(vals[5]) if vals[5] else 0,
            "change_amt":   float(vals[31]) if vals[31] else 0,
            "change_pct":   float(vals[32]) if vals[32] else 0,
            "high":         float(vals[33]) if vals[33] else 0,
            "low":          float(vals[34]) if vals[34] else 0,
            "amount_wan":   float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm":       float(vals[39]) if vals[39] else 0,
            "amplitude_pct":float(vals[43]) if vals[43] else 0,
            "mcap_yi":      float(vals[44]) if vals[44] else 0,
            "float_mcap_yi":float(vals[45]) if vals[45] else 0,
            "pb":           float(vals[46]) if vals[46] else 0,
            "limit_up":     float(vals[47]) if vals[47] else 0,
            "limit_down":   float(vals[48]) if vals[48] else 0,
            "vol_ratio":    float(vals[49]) if vals[49] else 0,
            "pe_static":    float(vals[52]) if vals[52] else 0,
        }
    return result

# 用法: 个股
quotes = tencent_quote(["688017", "300476", "002463"])
for code, q in quotes.items():
    print(f"{q['name']}({code}): {q['price']}元 PE={q['pe_ttm']} PB={q['pb']} 市值={q['mcap_yi']}亿")

# 用法: 指数 — sh000001=上证指数, sh000300=沪深300, sz399006=创业板指
index_quotes = tencent_quote(["000001", "000300", "399006"])

# 用法: ETF — sh510050=上证50ETF, sh510300=沪深300ETF
etf_quotes = tencent_quote(["510050", "510300"])
```

#### 腾讯财经字段索引速查（实测校准 2026-05-03）

| 索引 | 含义 | 示例 |
|------|------|------|
| 1 | 名称 | 绿的谐波 |
| 3 | 当前价 | 224.12 |
| 4 | 昨收 | 215.01 |
| 5 | 今开 | 214.10 |
| 9-18 | 买一~买五(价+量) | |
| 19-28 | 卖一~卖五(价+量) | |
| 31 | 涨跌额 | 9.11 |
| 32 | 涨跌幅% | 4.24 |
| 33 | 最高 | 229.62 |
| 34 | 最低 | 214.10 |
| 37 | 成交额(万) | 187040 |
| 38 | 换手率% | 4.55 |
| **39** | **PE(TTM)** | 300.45 |
| **43** | **振幅%（不是PB！）** | 7.22 |
| **44** | **总市值(亿)** | 410.88 |
| **45** | **流通市值(亿)** | 410.88 |
| **46** | **PB(市净率)** | 11.51 |
| **47** | **涨停价** | 258.01 |
| **48** | **跌停价** | 172.01 |
| 49 | 量比 | 1.20 |
| **52** | **PE(静)** | 314.76 |

> **踩坑提醒：** 网上很多教程把索引 43 写成 PB，实测是振幅%。PB 在索引 46。

### 1.3 百度股市通 K线 — 带MA5/MA10/MA20（V3.0 新增）

**核心价值：** 返回时自带均线数据，无需本地计算。

```python
import requests

def baidu_kline_with_ma(code: str, start_time: str = "") -> dict:
    """百度股市通K线 — 独有能力: 返回时自带 ma5/ma10/ma20 均价"""
    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
    params = {
        "all": "1", "isIndex": "false", "isBk": "false", "isBlock": "false",
        "isFutures": "false", "isStock": "true", "newFormat": "1",
        "group": "quotation_kline_ab", "finClientType": "pc",
        "code": code, "start_time": start_time, "ktype": "1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    r = requests.get(url, params=params, headers=headers, timeout=10)
    d = r.json()
    result = d.get("Result", {})
    md = result.get("newMarketData", {})
    keys = md.get("keys", [])  # includes: ma5avgprice, ma10avgprice, ma20avgprice
    rows = md.get("marketData", "").split(";")
    return {"keys": keys, "rows": rows}

# 用法
data = baidu_kline_with_ma("600519")
print("字段:", data["keys"][:10])
print("最近5根K线:", data["rows"][-5:])
# keys 包含: time, open, close, high, low, volume, amount, ma5avgprice, ma10avgprice, ma20avgprice 等
```

---

## Layer 2: 研报层

### 2.1 东财研报 API — 研报列表 + PDF下载（主力）

A级接口（公开JSON API），reportapi.eastmoney.com，免费无key。

```python
import requests
import re
import time
from pathlib import Path

REPORT_API = "https://reportapi.eastmoney.com/report/list"
PDF_TPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def eastmoney_reports(code: str, max_pages: int = 5) -> list[dict]:
    """拉取指定股票的研报列表"""
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Referer": "https://data.eastmoney.com/"})
    all_records = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "100", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2000-01-01", "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": str(page), "pageNum": str(page), "pageNumber": str(page),
        }
        r = session.get(REPORT_API, params=params, timeout=30)
        d = r.json()
        rows = d.get("data") or []
        if not rows:
            break
        all_records.extend(rows)
        if page >= (d.get("TotalPage", 1) or 1):
            break
        time.sleep(0.3)
    return all_records

def download_pdf(record: dict, target_dir: str = "./reports") -> str | None:
    """下载单份研报PDF，返回保存路径或None"""
    info_code = record.get("infoCode", "")
    if not info_code:
        return None
    date = (record.get("publishDate") or "")[:10]
    org = record.get("orgSName") or "未知"
    title = re.sub(r'[\\/:*?"<>|]', "_", record.get("title", ""))[:80]
    fname = f"{date}_{org}_{title}.pdf"
    target = Path(target_dir) / fname
    if target.exists():
        return str(target)
    url = PDF_TPL.format(info_code=info_code)
    r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"}, timeout=60)
    if r.status_code == 200 and len(r.content) >= 1024:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(r.content)
        return str(target)
    return None

# 用法
reports = eastmoney_reports("688017")
print(f"共 {len(reports)} 篇研报")
for r in reports[:5]:
    print(f"  {r.get('publishDate','')[:10]} | {r.get('orgSName')} | {r.get('title','')[:60]}")
```

#### 研报 record 关键字段

| 字段 | 含义 |
|------|------|
| title | 研报标题 |
| publishDate | 发布日期 |
| orgSName | 机构简称 |
| infoCode | 用于拼 PDF URL |
| predictThisYearEps | 今年EPS预测 |
| predictNextYearEps | 明年EPS预测 |
| predictNextTwoYearEps | 后年EPS预测 |
| emRatingName | 评级(买入/增持/...) |
| indvInduName | 行业分类 |

### 2.2 同花顺一致预期EPS（直连 basic.10jqka.com.cn）

```python
import requests
import pandas as pd

def ths_eps_forecast(code: str) -> pd.DataFrame:
    """
    同花顺机构一致预期EPS。
    直连 basic.10jqka.com.cn，解析HTML表格。
    返回 DataFrame: 年度, 预测机构数, 最小值, 均值, 最大值
    "均值" = 机构一致预期EPS
    """
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://basic.10jqka.com.cn/",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = "gbk"
    dfs = pd.read_html(r.text)
    # 找含"每股收益"的表格
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            return df
    # fallback: 返回第一个表
    return dfs[0] if dfs else pd.DataFrame()

# 用法
df = ths_eps_forecast("688017")
print(df)
# "预测机构数" < 3 的要谨慎
```

### 2.3 iwencai — NL语义搜索研报（唯一能力）

需要 API Key + X-Claw Headers（SkillHub 2.0 强制要求）。

```python
import os
import json
import secrets
import requests

IWENCAI_BASE = os.environ.get("IWENCAI_BASE_URL", "https://openapi.iwencai.com")
IWENCAI_KEY = os.environ.get("IWENCAI_API_KEY", "")

def _claw_headers(call_type: str = "normal") -> dict:
    """SkillHub 2.0 必须的 X-Claw 鉴权头"""
    return {
        "X-Claw-Call-Type": call_type,
        "X-Claw-Skill-Id": "report-search",
        "X-Claw-Skill-Version": "2.0.0",
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": secrets.token_hex(32),
    }

def iwencai_search(query: str, channel: str = "report", size: int = 50) -> list[dict]:
    """
    iwencai 语义搜索。
    channel: "report"(研报) / "announcement"(公告) / "news"(新闻)
    size: 默认10, 实测可调到50（隐藏参数）
    """
    headers = {
        "Authorization": f"Bearer {IWENCAI_KEY}",
        "Content-Type": "application/json",
        **_claw_headers(),
    }
    payload = {
        "channels": [channel],
        "app_id": "AIME_SKILL",
        "query": query,
        "size": size,
    }
    r = requests.post(
        f"{IWENCAI_BASE}/v1/comprehensive/search",
        json=payload, headers=headers, timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"iwencai HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    if data.get("status_code", 0) != 0:
        raise RuntimeError(f"iwencai error: {data.get('status_msg', '')}")
    return data.get("data") or []

def iwencai_query(query: str, page: int = 1, limit: int = 50) -> list[dict]:
    """
    iwencai NL数据查询（结构化字段）。
    例: "贵州茅台 ROE" → DataFrame-like rows
    """
    headers = {
        "Authorization": f"Bearer {IWENCAI_KEY}",
        "Content-Type": "application/json",
        **_claw_headers(),
    }
    payload = {
        "query": query,
        "page": str(page),
        "limit": str(limit),
        "is_cache": "1",
        "expand_index": "true",
    }
    r = requests.post(
        f"{IWENCAI_BASE}/v1/query2data",
        json=payload, headers=headers, timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"iwencai HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    if data.get("status_code", 0) != 0:
        raise RuntimeError(f"iwencai error: {data.get('status_msg', '')}")
    return data.get("datas") or []

def dedup_articles(articles: list[dict]) -> list[dict]:
    """同一uid仅保留score最高的段落"""
    best = {}
    for a in articles:
        uid = a.get("uid", "") or f"{a.get('title','')}|{a.get('publish_date','')}"
        score = float(a.get("score", 0))
        if uid not in best or score > float(best[uid].get("score", 0)):
            best[uid] = a
    return sorted(best.values(), key=lambda x: x.get("publish_date", ""), reverse=True)

# 用法: NL语义搜索研报
articles = iwencai_search("人形机器人 行星滚柱丝杠 2026", channel="report", size=50)
articles = dedup_articles(articles)
for a in articles[:5]:
    extra = a.get("extra") or {}
    if isinstance(extra, str):
        extra = json.loads(extra)
    print(f"{a.get('publish_date','')[:10]} | {extra.get('organization','')} | {a.get('title','')[:60]}")
```

**iwencai 的唯一价值：** NL 主题搜索。"人形机器人 行星滚柱丝杠" 这种跨主题检索只有 iwencai 能做。按标的搜研报走东财 reportapi 更稳定。

---

## Layer 3: 信号层

### 3.1 同花顺热点 — 当日强势股 + 题材归因 reason tags（独家）

**核心价值：** 不只告诉你"哪些走强"，还告诉你**"为什么走强"** —— 同花顺编辑部人工运营的题材标签。

```python
import requests
import pandas as pd

def ths_hot_reason(date: str = None) -> pd.DataFrame:
    """
    同花顺当日强势股归因。
    date: 'YYYY-MM-DD' 格式，None=今天
    返回 DataFrame，含每只股票的题材标签 (reason)。

    实测: 73ms 拿到 ~125 只 + 完整字段
    """
    from datetime import date as _date
    if date is None:
        date = _date.today().strftime("%Y-%m-%d")

    url = (
        f"http://zx.10jqka.com.cn/event/api/getharden/"
        f"date/{date}/orderby/date/orderway/desc/charset/GBK/"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "Chrome/117.0.0.0 Safari/537.36"
        )
    }
    r = requests.get(url, headers=headers, timeout=10)
    data = r.json()
    if data.get("errocode", 0) != 0:
        raise RuntimeError(f"同花顺热点错误: {data.get('errormsg', '')}")

    rows = data.get("data") or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # 字段重命名（中文友好）
    rename_map = {
        "name": "名称", "code": "代码", "reason": "题材归因",
        "close": "收盘价", "zhangdie": "涨跌额", "zhangfu": "涨幅%",
        "huanshou": "换手率%", "chengjiaoe": "成交额",
        "chengjiaoliang": "成交量", "ddejingliang": "大单净量",
        "market": "市场",
    }
    df = df.rename(columns=rename_map)
    return df

# 用法
df = ths_hot_reason("2026-05-09")
print(f"当日强势股: {len(df)} 只")
print(df[["代码", "名称", "涨幅%", "题材归因"]].head(10))
```

#### 同花顺热点字段速查

| 原字段 | 中文 | 说明 |
|---|---|---|
| code | 代码 | 6 位股票代码 |
| name | 名称 | 简称 |
| **reason** | **题材归因** | **核心字段，人工运营 tags，如"算力租赁+Token工厂+AI政务"** |
| zhangfu | 涨幅% | 当日涨幅 |
| huanshou | 换手率% | 当日换手 |
| chengjiaoe | 成交额 | 元 |
| chengjiaoliang | 成交量 | 股 |
| ddejingliang | 大单净量 | 主力净流入指标 |
| close | 收盘价 | 元 |
| zhangdie | 涨跌额 | 元 |
| market | 市场 | 沪/深/北 |

### 3.2 同花顺北向资金 — hsgtApi 实时分钟流向 + 本地自缓存历史

> **已知行业性问题：** eastmoney 全系北向数据自 2024-08 后净买额字段返回 NaN/0，属上游断供。已改为**本地 CSV 自缓存模式**——每次拉实时数据后自动写入本地 CSV，历史越跑越丰富。

```python
import requests
import pandas as pd
from pathlib import Path

HSGT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "Chrome/117.0.0.0 Safari/537.36"
    ),
    "Host": "data.hexin.cn",
    "Referer": "https://data.hexin.cn/",
}

def hsgt_realtime() -> pd.DataFrame:
    """
    沪深股通当日实时分钟流向（含集合竞价 09:10–15:00，262 个时间点）。
    返回字段: time, hgt(沪股通累计净买入), sgt(深股通累计净买入)
    单位: 亿元
    """
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    r = requests.get(url, headers=HSGT_HEADERS, timeout=10)
    d = r.json()
    times = d.get("time", [])
    hgt = d.get("hgt", [])
    sgt = d.get("sgt", [])

    n = len(times)
    return pd.DataFrame({
        "time": times,
        "hgt_yi": hgt[:n] + [None] * (n - len(hgt)),
        "sgt_yi": sgt[:n] + [None] * (n - len(sgt)),
    })

# === 自缓存辅助函数 ===

def _northbound_cache_path() -> Path:
    """北向资金本地 CSV 缓存路径"""
    p = Path.home() / ".tradingagents" / "cache" / "northbound_daily.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def _save_northbound_snapshot(date: str, hgt: float, sgt: float):
    """写入/更新当天北向收盘数据到 CSV"""
    path = _northbound_cache_path()
    rows = {}
    if path.exists():
        for line in path.read_text().strip().split("\n")[1:]:
            parts = line.split(",")
            if len(parts) == 3:
                rows[parts[0]] = line
    rows[date] = f"{date},{hgt},{sgt}"
    with open(path, "w") as f:
        f.write("date,hgt,sgt\n")
        for d in sorted(rows.keys()):
            f.write(rows[d] + "\n")

def _load_northbound_history(n: int = 20) -> pd.DataFrame:
    """读取最近 N 天北向历史"""
    path = _northbound_cache_path()
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df.tail(n)

# 用法 1: 实时分钟流向
df = hsgt_realtime()
print(f"分钟点数: {len(df)}")
print(df.tail(5))

# 用法 2: 自动缓存今日收盘数据
if not df.empty:
    last = df.dropna().iloc[-1]
    _save_northbound_snapshot("2026-05-17", last["hgt_yi"], last["sgt_yi"])

# 用法 3: 读取历史
hist = _load_northbound_history(20)
print(hist)
```

### 3.3 百度股市通 — 概念板块归属

**核心价值：** 一次调用拿到个股所属的行业（申万一级/二级）、概念（多个）、地域三维分类，含当日涨跌幅。

```python
import requests

_BAIDU_PAE_HEADERS = {
    "Host": "finance.pae.baidu.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0",
    "Accept": "application/vnd.finance-web.v1+json",
    "Origin": "https://gushitong.baidu.com",
    "Referer": "https://gushitong.baidu.com/",
}

def baidu_concept_blocks(code: str) -> dict:
    """
    百度股市通概念板块归属。
    返回: {industry: [...], concept: [...], region: [...], concept_tags: [...]}
    """
    url = (
        f"https://finance.pae.baidu.com/api/getrelatedblock"
        f"?code={code}&market=ab"
        f"&typeCode=all&finClientType=pc"
    )
    r = requests.get(url, headers=_BAIDU_PAE_HEADERS, timeout=10)
    d = r.json()
    if str(d.get("ResultCode", -1)) != "0":
        raise RuntimeError(f"百度PAE错误: {d}")

    result = {"industry": [], "concept": [], "region": [], "concept_tags": []}
    for block in d.get("Result", []):
        block_type = block.get("type", "")
        for item in block.get("list", []):
            entry = {
                "name": item.get("name", ""),
                "change_pct": item.get("increase", ""),
                "desc": item.get("desc", ""),
            }
            if "行业" in block_type:
                result["industry"].append(entry)
            elif "概念" in block_type:
                result["concept"].append(entry)
                result["concept_tags"].append(entry["name"])
            elif "地域" in block_type:
                result["region"].append(entry)
    return result

# 用法
blocks = baidu_concept_blocks("688017")
print("行业:", [b["name"] for b in blocks["industry"]])
print("概念:", blocks["concept_tags"])
print("地域:", [b["name"] for b in blocks["region"]])
```

> **踩坑：** `ResultCode` 返回类型不稳定——有时 int `0`，有时 string `"0"`。必须用 `str()` 统一比较。

### 3.4 东财 push2 — 个股资金流向（分钟级）

盘中实时分钟级资金流（主力/大单/中单/小单/超大单净流入）。

> **V3.1 替换说明：** 百度 PAE `fundflow` 和 `fundsortlist` 接口已于 2026-05 下线（返回 null），改用东财 push2 资金流 API。日级资金流见 Layer 4.5 `stock_fund_flow_120d()`。

```python
import requests

def eastmoney_fund_flow_minute(code: str) -> list[dict]:
    """
    个股资金流向（分钟级，当日盘中）。
    code: 6位股票代码
    返回: [{time, main_net, small_net, mid_net, large_net, super_net}, ...]
    单位: 元
    """
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": secid, "klt": 1,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    r = requests.get(url, params=params, timeout=10)
    d = r.json()

    rows = []
    for line in d.get("data", {}).get("klines", []):
        parts = line.split(",")
        if len(parts) >= 6:
            rows.append({
                "time": parts[0],
                "main_net": float(parts[1]),
                "small_net": float(parts[2]),
                "mid_net": float(parts[3]),
                "large_net": float(parts[4]),
                "super_net": float(parts[5]),
            })
    return rows

# 用法: 分钟级实时资金流
realtime = eastmoney_fund_flow_minute("000858")
if realtime:
    last = realtime[-1]
    signal = "bullish" if last["main_net"] > 0 else "bearish"
    print(f"主力净流入: {last['main_net']:.0f}元 → {signal}")
    # 统计全天主力净流入
    total = sum(r["main_net"] for r in realtime)
    print(f"全天主力累计: {total/1e4:.0f}万元")
```

> **注意：** push2 资金流金额单位是**元**（非万元），使用时注意换算。`klt=1` 分钟级，`klt=101` 日级。

### 3.5 龙虎榜席位 — 个股上榜记录 + 买卖席位 TOP5 + 机构动向

直连东财 datacenter API，不依赖第三方封装。

```python
import requests
from datetime import datetime, timedelta

def dragon_tiger_board(code: str, trade_date: str, look_back: int = 30) -> dict:
    """
    龙虎榜数据聚合。
    trade_date: YYYY-MM-DD
    look_back: 回看天数
    返回: {records: [...], seats: {buy: [...], sell: [...]}, institution: {...}}
    """
    start = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=look_back)
    start_str = start.strftime("%Y-%m-%d")

    # 1. 上榜记录
    records = []
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{start_str}')(TRADE_DATE<='{trade_date}')(SECURITY_CODE=\"{code}\")",
        page_size=50,
        sort_columns="TRADE_DATE", sort_types="-1",
    )
    for row in data:
        records.append({
            "date": str(row.get("TRADE_DATE", ""))[:10],
            "reason": row.get("EXPLANATION", ""),
            "net_buy": round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 1),
            "turnover": round(float(row.get("TURNOVERRATE") or 0), 2),
        })

    # 2. 最近上榜的买卖席位
    seats = {"buy": [], "sell": []}
    if records:
        latest_date = records[0]["date"]
        # 买入席位
        buy_data = eastmoney_datacenter(
            "RPT_BILLBOARD_DAILYDETAILSBUY",
            filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
            page_size=10,
            sort_columns="BUY", sort_types="-1",
        )
        for row in buy_data[:5]:
            seats["buy"].append({
                "name": row.get("OPERATEDEPT_NAME", ""),
                "buy_amt": round((row.get("BUY") or 0) / 10000, 1),
                "sell_amt": round((row.get("SELL") or 0) / 10000, 1),
                "net": round((row.get("NET") or 0) / 10000, 1),
            })
        # 卖出席位
        sell_data = eastmoney_datacenter(
            "RPT_BILLBOARD_DAILYDETAILSSELL",
            filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
            page_size=10,
            sort_columns="SELL", sort_types="-1",
        )
        for row in sell_data[:5]:
            seats["sell"].append({
                "name": row.get("OPERATEDEPT_NAME", ""),
                "buy_amt": round((row.get("BUY") or 0) / 10000, 1),
                "sell_amt": round((row.get("SELL") or 0) / 10000, 1),
                "net": round((row.get("NET") or 0) / 10000, 1),
            })

    # 3. 机构买卖统计（从买卖席位明细中筛选 OPERATEDEPT_CODE="0" 即机构专用席位）
    institution = {"buy_amt": 0, "sell_amt": 0, "net_amt": 0}
    for detail_data, side in [(buy_data, "buy"), (sell_data, "sell")]:
        for row in detail_data:
            if str(row.get("OPERATEDEPT_CODE", "")) == "0":
                amt = (row.get("BUY") or 0) if side == "buy" else (row.get("SELL") or 0)
                if side == "buy":
                    institution["buy_amt"] += amt
                else:
                    institution["sell_amt"] += amt
    institution["buy_amt"] = round(institution["buy_amt"] / 10000, 1)
    institution["sell_amt"] = round(institution["sell_amt"] / 10000, 1)
    institution["net_amt"] = round(institution["buy_amt"] - institution["sell_amt"], 1)

    return {"records": records, "seats": seats, "institution": institution}

# 用法
data = dragon_tiger_board("002475", "2026-05-17")
print(f"近30日上榜 {len(data['records'])} 次")
for r in data["records"]:
    print(f"  {r['date']}: {r['reason']}")
if data["seats"]["buy"]:
    print("买入席位 TOP5:")
    for s in data["seats"]["buy"]:
        print(f"  {s['name']}: 买{s['buy_amt']}万 卖{s['sell_amt']}万 净{s['net']}万")
```

> **ST 股注意：** 5% 涨跌停更容易触发龙虎榜（"连续三日偏离值累计达12%"），科创板 20% 涨跌停则较少触发。

### 3.6 限售解禁日历 — 历史解禁 + 未来 90 天待解禁

```python
from datetime import datetime, timedelta

def lockup_expiry(code: str, trade_date: str, forward_days: int = 90) -> dict:
    """
    限售解禁日历。
    返回: {history: [...], upcoming: [...]}
    """
    # 1. 历史解禁记录
    history_data = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f"(SECURITY_CODE=\"{code}\")",
        page_size=15,
        sort_columns="FREE_DATE", sort_types="-1",
    )
    history = []
    for row in history_data:
        history.append({
            "date": str(row.get("FREE_DATE", ""))[:10],
            "type": row.get("LIMITED_STOCK_TYPE", ""),
            "shares": row.get("FREE_SHARES_NUM", 0),
            "ratio": row.get("FREE_RATIO", 0),
        })

    # 2. 未来待解禁
    end_date = datetime.strptime(trade_date, "%Y-%m-%d") + timedelta(days=forward_days)
    end_str = end_date.strftime("%Y-%m-%d")
    upcoming_data = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f"(SECURITY_CODE=\"{code}\")(FREE_DATE>='{trade_date}')(FREE_DATE<='{end_str}')",
        page_size=20,
        sort_columns="FREE_DATE", sort_types="1",
    )
    upcoming = []
    for row in upcoming_data:
        upcoming.append({
            "date": str(row.get("FREE_DATE", ""))[:10],
            "type": row.get("LIMITED_STOCK_TYPE", ""),
            "shares": row.get("FREE_SHARES_NUM", 0),
            "ratio": row.get("FREE_RATIO", 0),
        })

    return {"history": history, "upcoming": upcoming}

# 用法
data = lockup_expiry("002475", "2026-05-17")
print(f"历史解禁 {len(data['history'])} 批")
for h in data["history"][:5]:
    print(f"  {h['date']}: {h['type']} 数量={h['shares']}")
if data["upcoming"]:
    print(f"未来90天待解禁 {len(data['upcoming'])} 批")
else:
    print("未来90天无待解禁")
```

**限售股类型参考：**
- 首发原股东限售股份（IPO 后 1-3 年）
- 首发机构配售股份（IPO 战略配售）
- 定向增发机构配售股份（6-18 个月）
- 股权激励限售股份

### 3.7 行业板块排名（V3.0 改用东财 — 同花顺加了反爬401）

东财行业板块涨跌幅排名，一次调用看全市场行业轮动。

```python
import requests

def industry_comparison(top_n: int = 20) -> dict:
    """
    全行业涨跌幅排名（东财行业板块，~100 个行业）。
    返回: {top: [...], bottom: [...], total: int}
    """
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "100", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": "m:90+t:2",
        "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
    }
    headers = {"User-Agent": UA}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    d = r.json()
    items = d.get("data", {}).get("diff", [])
    if not items:
        return {"top": [], "bottom": [], "total": 0}

    rows = []
    for i, item in enumerate(items):
        rows.append({
            "rank": i + 1,
            "name": item.get("f14", ""),
            "change_pct": item.get("f3", 0),
            "code": item.get("f12", ""),
            "up_count": item.get("f104", 0),
            "down_count": item.get("f105", 0),
            "leader": item.get("f140", ""),
            "leader_change": item.get("f136", 0),
        })

    return {
        "top": rows[:top_n],
        "bottom": rows[-top_n:],
        "total": len(rows),
    }

# 用法
data = industry_comparison(20)
print(f"共 {data['total']} 个行业")
print("\nTOP 10 涨幅:")
for r in data["top"][:10]:
    print(f"  {r['rank']}. {r['name']}: {r['change_pct']}% 涨{r['up_count']}跌{r['down_count']} 领涨{r['leader']}")
print("\nBOTTOM 5 跌幅:")
for r in data["bottom"][-5:]:
    print(f"  {r['rank']}. {r['name']}: {r['change_pct']}%")
```

### 3.8 全市场龙虎榜

每日全市场龙虎榜汇总——当日所有触发龙虎榜的股票 + 上榜原因 + 买卖净额 + 换手率。

```python
from datetime import datetime

def daily_dragon_tiger(trade_date: str = None, min_net_buy: float = None) -> dict:
    """
    全市场龙虎榜。
    trade_date: YYYY-MM-DD（默认当日）
    min_net_buy: 净买入下限（万元），None 不过滤
    返回: {date, total_records, stocks: [{code, name, reason, close, change_pct,
           net_buy_wan, buy_wan, sell_wan, turnover_pct}]}
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
        page_size=500,
        sort_columns="BILLBOARD_NET_AMT", sort_types="-1",
    )
    if not data:
        return {"date": trade_date, "total_records": 0, "stocks": [],
                "note": "无数据（非交易日或盘后未更新）"}

    actual_date = str(data[0].get("TRADE_DATE", ""))[:10] if data else trade_date
    stocks = []
    for row in data:
        net_buy = (row.get("BILLBOARD_NET_AMT") or 0) / 10000
        if min_net_buy is not None and net_buy < min_net_buy:
            continue
        stocks.append({
            "code": row.get("SECURITY_CODE", ""),
            "name": row.get("SECURITY_NAME_ABBR", ""),
            "reason": row.get("EXPLANATION", ""),
            "close": row.get("CLOSE_PRICE") or 0,
            "change_pct": round(float(row.get("CHANGE_RATE") or 0), 2),
            "net_buy_wan": round(net_buy, 1),
            "buy_wan": round((row.get("BILLBOARD_BUY_AMT") or 0) / 10000, 1),
            "sell_wan": round((row.get("BILLBOARD_SELL_AMT") or 0) / 10000, 1),
            "turnover_pct": round(float(row.get("TURNOVERRATE") or 0), 2),
        })
    return {"date": actual_date, "total_records": len(stocks), "stocks": stocks}

# 用法
data = daily_dragon_tiger("2026-05-16")
print(f"{data['date']} 龙虎榜共 {data['total_records']} 条记录")
for s in data["stocks"][:10]:
    print(f"  {s['code']} {s['name']}: {s['reason']} | 净买{s['net_buy_wan']}万 涨跌{s['change_pct']}%")

# 只看净买入 > 5000 万的
data = daily_dragon_tiger("2026-05-16", min_net_buy=5000)
print(f"\n净买入 > 5000万: {data['total_records']} 条")
```

### 3.9 信号层组合用法：题材热度 + 资金验证

```python
# 拉当日强势股 reason
df_hot = ths_hot_reason()

# 词频统计 reason 列里的题材关键词
from collections import Counter
all_tags = []
for r in df_hot["题材归因"].dropna():
    tags = [t.strip() for t in str(r).split("+") if t.strip()]
    all_tags.extend(tags)

cnt = Counter(all_tags)
print("当日 TOP 10 题材热度:")
for tag, n in cnt.most_common(10):
    print(f"  {tag}: {n} 只")

# 同时拉北向当日流向，看资金流方向是否对应题材
df_north = hsgt_realtime()
hgt_close = df_north["hgt_yi"].dropna().iloc[-1] if not df_north.empty else 0
sgt_close = df_north["sgt_yi"].dropna().iloc[-1] if not df_north.empty else 0
print(f"\n北向收盘累计: 沪股通 {hgt_close} 亿 / 深股通 {sgt_close} 亿")

# V3.0: 叠加行业对比，看哪些行业资金在流入
comp = industry_comparison(10)
print("\n行业涨幅 TOP 5:")
for r in comp["top"][:5]:
    print(f"  {r['name']}: {r['change_pct']}% 涨{r['up_count']}跌{r['down_count']}")
```

---

## Layer 4: 资金面 / 筹码层（V3.0 新增）

### 4.1 融资融券明细

```python
def margin_trading(code: str, page_size: int = 30) -> list[dict]:
    """
    融资融券明细（日级）。
    返回: [{date, rzye(融资余额), rzmre(融资买入), rqye(融券余额), ...}]
    """
    data = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        filter_str=f'(SCODE="{code}")',
        page_size=page_size,
        sort_columns="DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("DATE", ""))[:10],
            "rzye": row.get("RZYE", 0),       # 融资余额(元)
            "rzmre": row.get("RZMRE", 0),      # 融资买入额
            "rzche": row.get("RZCHE", 0),      # 融资偿还额
            "rqye": row.get("RQYE", 0),        # 融券余额(元)
            "rqmcl": row.get("RQMCL", 0),      # 融券卖出量
            "rqchl": row.get("RQCHL", 0),      # 融券偿还量
            "rzrqye": row.get("RZRQYE", 0),    # 融资融券余额合计
        })
    return rows

# 用法
data = margin_trading("600519")
for d in data[:5]:
    print(f"{d['date']}: 融资余额={d['rzye']/1e8:.2f}亿 融券余额={d['rqye']/1e8:.2f}亿")
```

### 4.2 大宗交易

```python
def block_trade(code: str, page_size: int = 20) -> list[dict]:
    """
    大宗交易记录。
    返回: [{date, price, vol, amount, buyer, seller, premium_pct}]
    """
    data = eastmoney_datacenter(
        "RPT_DATA_BLOCKTRADE",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="TRADE_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        close = row.get("CLOSE_PRICE") or 0
        deal_price = row.get("DEAL_PRICE") or 0
        premium = ((deal_price / close - 1) * 100) if close else 0
        rows.append({
            "date": str(row.get("TRADE_DATE", ""))[:10],
            "price": deal_price,
            "close": close,
            "premium_pct": round(premium, 2),
            "vol": row.get("DEAL_VOLUME", 0),
            "amount": row.get("DEAL_AMT", 0),
            "buyer": row.get("BUYER_NAME", ""),
            "seller": row.get("SELLER_NAME", ""),
        })
    return rows

# 用法
data = block_trade("600519")
for d in data[:5]:
    print(f"{d['date']}: 价格={d['price']} 溢价={d['premium_pct']}% 买方={d['buyer']}")
```

### 4.3 股东户数变化

```python
def holder_num_change(code: str, page_size: int = 10) -> list[dict]:
    """
    股东户数变化（季度级）。
    返回: [{date, holder_num, change_num, change_ratio, avg_shares}]
    """
    data = eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="END_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("END_DATE", ""))[:10],
            "holder_num": row.get("HOLDER_NUM", 0),
            "change_num": row.get("HOLDER_NUM_CHANGE", 0),
            "change_ratio": row.get("HOLDER_NUM_RATIO", 0),  # 环比%
            "avg_shares": row.get("AVG_FREE_SHARES", 0),     # 户均持股
        })
    return rows

# 用法
data = holder_num_change("600519")
for d in data[:5]:
    print(f"{d['date']}: 股东数={d['holder_num']} 变化={d['change_ratio']}% 户均={d['avg_shares']}")
# 股东户数持续减少 = 筹码集中 = 主力吸筹信号
```

### 4.4 分红送转历史

```python
def dividend_history(code: str, page_size: int = 20) -> list[dict]:
    """
    分红送转历史。
    返回: [{date, bonus_rmb(每股派息), transfer_ratio(转增比例), bonus_ratio(送股比例)}]
    """
    data = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="EX_DIVIDEND_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("EX_DIVIDEND_DATE", ""))[:10],
            "bonus_rmb": row.get("PRETAX_BONUS_RMB", 0),    # 每股派息(税前)
            "transfer_ratio": row.get("TRANSFER_RATIO", 0),  # 每10股转增
            "bonus_ratio": row.get("BONUS_RATIO", 0),        # 每10股送股
            "plan": row.get("ASSIGN_PROGRESS", ""),           # 进度
        })
    return rows

# 用法
data = dividend_history("600519")
for d in data[:5]:
    print(f"{d['date']}: 每股派息={d['bonus_rmb']}元 转增={d['transfer_ratio']} 送={d['bonus_ratio']}")
```

### 4.5 个股资金流（120日，日级）

```python
import requests

def stock_fund_flow_120d(code: str) -> list[dict]:
    """
    个股资金流（日级，最近120个交易日）。
    返回: [{date, main_net(主力净流入), small_net, mid_net, large_net, super_net}]
    单位: 元
    """
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{market_code}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": "120",
    }
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
    d = r.json()
    klines = d.get("data", {}).get("klines", [])

    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 7:
            rows.append({
                "date": parts[0],
                "main_net": float(parts[1]) if parts[1] != "-" else 0,
                "small_net": float(parts[2]) if parts[2] != "-" else 0,
                "mid_net": float(parts[3]) if parts[3] != "-" else 0,
                "large_net": float(parts[4]) if parts[4] != "-" else 0,
                "super_net": float(parts[5]) if parts[5] != "-" else 0,
            })
    return rows

# 用法
data = stock_fund_flow_120d("600519")
for d in data[-5:]:
    print(f"{d['date']}: 主力净流入={d['main_net']/1e4:.0f}万 超大单={d['super_net']/1e4:.0f}万")

# 统计近20日主力净流入
recent_20 = data[-20:]
total_main = sum(d["main_net"] for d in recent_20)
print(f"\n近20日主力累计净流入: {total_main/1e8:.2f}亿")
```

---

## Layer 5: 新闻层

### 5.1 东财个股新闻（直连 search-api-web）

```python
import requests
import re
import json

def eastmoney_stock_news(code: str, page_size: int = 20) -> list[dict]:
    """
    东财个股新闻（JSONP 接口）。
    返回: [{title, content, time, source, url}]
    """
    # 构造 JSONP 参数
    cb = "jQuery_news"
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner_params = json.dumps({
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default",
                  "pageIndex": 1, "pageSize": page_size, "preTag": "", "postTag": ""}},
    }, separators=(',', ':'))
    params = {"cb": cb, "param": inner_params}
    headers = {"User-Agent": UA, "Referer": "https://so.eastmoney.com/"}
    r = requests.get(url, params=params, headers=headers, timeout=15)

    # 解析 JSONP
    text = r.text
    json_str = text[text.index("(") + 1 : text.rindex(")")]
    d = json.loads(json_str)

    rows = []
    articles = d.get("result", {}).get("cmsArticleWebOld", {}).get("list", [])
    for a in articles:
        rows.append({
            "title": re.sub(r'<[^>]+>', '', a.get("title", "")),
            "content": re.sub(r'<[^>]+>', '', a.get("content", ""))[:200],
            "time": a.get("date", ""),
            "source": a.get("mediaName", ""),
            "url": a.get("url", ""),
        })
    return rows

# 用法
news = eastmoney_stock_news("688017")
for n in news[:5]:
    print(f"  {n['time']} | {n['source']} | {n['title']}")
```

### 5.2 财联社快讯（直连 cls.cn）

```python
import requests

def cls_telegraph(page_size: int = 50) -> list[dict]:
    """
    财联社电报（全市场实时快讯）。
    返回: [{title, content, time}]
    """
    url = "https://www.cls.cn/nodeapi/telegraphList"
    params = {"rn": str(page_size), "page": "1"}
    headers = {"User-Agent": UA, "Referer": "https://www.cls.cn/"}
    r = requests.get(url, params=params, headers=headers, timeout=10)
    d = r.json()

    rows = []
    for item in d.get("data", {}).get("roll_data", []):
        rows.append({
            "title": item.get("title", "") or item.get("brief", ""),
            "content": item.get("content", "") or item.get("brief", ""),
            "time": item.get("ctime", ""),
        })
    return rows

# 用法
news = cls_telegraph()
for n in news[:10]:
    print(f"  {n['time']} | {n['title'][:60]}")
```

### 5.3 东财全球资讯（7x24）

```python
import requests

import uuid

def eastmoney_global_news(page_size: int = 50) -> list[dict]:
    """
    东方财富全球财经资讯（7x24 滚动）。
    返回: [{title, summary, time}]
    """
    url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
    params = {
        "client": "web", "biz": "web_724",
        "fastColumn": "102", "sortEnd": "",
        "pageSize": str(page_size),
        "req_trace": str(uuid.uuid4()),
    }
    headers = {"User-Agent": UA, "Referer": "https://kuaixun.eastmoney.com/"}
    r = requests.get(url, params=params, headers=headers, timeout=10)
    d = r.json()

    rows = []
    for item in d.get("data", {}).get("fastNewsList", []):
        rows.append({
            "title": item.get("title", ""),
            "summary": item.get("summary", "")[:200],
            "time": item.get("showTime", ""),
        })
    return rows

# 用法
news = eastmoney_global_news()
for n in news[:10]:
    print(f"  {n['time']} | {n['title']}")
```

---

## Layer 6: 基础数据层

### 6.1 mootdx 财务快照（37字段季报数据）

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')

# market: 0=深圳, 1=上海
fin = client.finance(symbol='688017')
# 返回 37 个字段的季报快照:
#   liutongguben(流通股本), zongguben(总股本)
#   eps(每股收益), bvps(每股净资产), roe(净资产收益率%)
#   profit(净利润), income(主营收入)
#   meigujingzichan(每股净资产), meigugongjijin(每股公积金)
#   meiguweifeipeili(每股未分配利润)
#   等37个季报财务字段
```

### 6.2 mootdx F10（公司文本资料）

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')

# 9 大类文本数据:
categories = [
    "最新提示", "公司概况", "财务分析",
    "股东研究", "股本结构", "资本运作",
    "业内点评", "行业分析", "公司大事",
]
for cat in categories:
    text = client.F10(symbol='688017', name=cat)
    print(f"=== {cat} ===")
    print(text[:200] if text else "(空)")
```

> **优化提示：** "股东研究" 中的【4.股东变化】章节含大量历史十大股东列表，实测 16000+ chars。建议只保留最新一期（-70% token）。

### 6.3 东财个股基本面（直连 push2 API）

```python
import requests

def eastmoney_stock_info(code: str) -> dict:
    """
    东财个股基本面信息。
    返回: {code, name, industry, total_shares, float_shares, mcap, float_mcap, list_date}
    """
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
        "secid": f"{market_code}.{code}",
    }
    headers = {"User-Agent": UA}
    r = requests.get(url, params=params, headers=headers, timeout=10)
    d = r.json().get("data", {})
    return {
        "code": d.get("f57", ""),
        "name": d.get("f58", ""),
        "industry": d.get("f127", ""),
        "total_shares": d.get("f84", 0),     # 总股本(股)
        "float_shares": d.get("f85", 0),     # 流通股(股)
        "mcap": d.get("f116", 0),            # 总市值(元)
        "float_mcap": d.get("f117", 0),      # 流通市值(元)
        "list_date": str(d.get("f189", "")), # 上市日期 YYYYMMDD
        "price": d.get("f43", 0),
    }

# 用法
info = eastmoney_stock_info("688017")
print(f"{info['name']}({info['code']}): 行业={info['industry']} 总市值={info['mcap']/1e8:.0f}亿 上市={info['list_date']}")
```

### 6.4 新浪财报三表（资产负债表/利润表/现金流量表）

```python
import requests

def sina_financial_report(code: str, report_type: str = "lrb") -> list[dict]:
    """
    新浪财报三表。
    code: 6位代码
    report_type: "fzb"(资产负债表) / "lrb"(利润表) / "llb"(现金流量表)
    返回: 按报告期排序的财务数据列表
    """
    prefix = "sh" if code.startswith("6") else "sz"
    paper_code = f"{prefix}{code}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code,
        "source": report_type,
        "type": "0",
        "page": "1",
        "num": "20",  # 最近20期
    }
    headers = {"User-Agent": UA}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    d = r.json()

    rows = []
    result = d.get("result", {}).get("data", {})
    # 结构: {report_type: [{...}, ...]}
    items = result.get(report_type, [])
    if isinstance(items, list):
        rows = items
    return rows

# 用法: 利润表
lrb = sina_financial_report("600519", "lrb")
for item in lrb[:3]:
    print(f"报告期: {item.get('报告日', '')} 净利润: {item.get('净利润', '')}")

# 用法: 资产负债表
fzb = sina_financial_report("600519", "fzb")

# 用法: 现金流量表
llb = sina_financial_report("600519", "llb")
```

---

## Layer 7: 公告层

### 7.1 巨潮公告（直连 cninfo.com.cn）

```python
import requests

def cninfo_announcements(code: str, page_size: int = 30) -> list[dict]:
    """
    巨潮公告全文检索。
    返回: [{title, type, date, url}]
    """
    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    # 构造 orgId（巨潮 2026 新格式）
    if code.startswith("6"):
        org_id = f"gssh0{code}"
    elif code.startswith("8") or code.startswith("4"):
        org_id = f"gsbj0{code}"
    else:
        org_id = f"gssz0{code}"

    payload = {
        "stock": f"{code},{org_id}",
        "tabName": "fulltext",
        "pageSize": str(page_size),
        "pageNum": "1",
        "column": "",
        "category": "",
        "plate": "",
        "seDate": "",
        "searchkey": "",
        "secid": "",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://www.cninfo.com.cn/new/disclosure",
        "Origin": "https://www.cninfo.com.cn",
    }
    r = requests.post(url, data=payload, headers=headers, timeout=15)
    d = r.json()

    rows = []
    for item in d.get("announcements", []) or []:
        rows.append({
            "title": item.get("announcementTitle", ""),
            "type": item.get("announcementTypeName", ""),
            "date": item.get("announcementTime", ""),
            "url": f"https://www.cninfo.com.cn/new/disclosure/detail?annoId={item.get('announcementId', '')}",
        })
    return rows

# 用法
anns = cninfo_announcements("688017")
for a in anns[:10]:
    print(f"  {a['date']} | {a['type']} | {a['title']}")
```

### 7.2 mootdx F10 公告摘要

```python
from mootdx.quotes import Quotes
client = Quotes.factory(market='std')
text = client.F10(symbol='688017', name='最新提示')
# 包含最近的公告/分红/股东大会决议等摘要
```

---

## Layer 8: 港股数据层（★V4.0 新增）

> **数据源优先级（港股）：** 腾讯财经 hk前缀（实时行情）> 东财 push2（实时行情备用）> Yahoo Finance（K线/财报/指数）> 东财 reportapi（研报）

### 8.1 腾讯财经 港股实时行情

与 A股 `tencent_quote()` 同源，传入 `hk` 前缀五位代码即可。

```python
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def tencent_hk_quote(hk_codes: list[str]) -> dict[str, dict]:
    """
    腾讯财经港股实时行情。
    hk_codes: ["00700", "09988", "03690"] — 五位港股代码（不含hk前缀）
    返回: {code: {name, price, change_pct, change_amt, high, low, volume, mcap_yi_hkd}}
    注: 港股字段位置与A股有所不同，用独立解析
    """
    prefixed = [f"hk{c.zfill(5)}" for c in hk_codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")

    result = {}
    for line in raw.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]   # e.g. "hk00700"
        vals = line.split('"')[1].split("~")
        if len(vals) < 50:
            continue
        code = key[2:]  # strip "hk"
        try:
            result[code] = {
                "name":       vals[1],
                "price":      float(vals[3]) if vals[3] else 0,
                "last_close": float(vals[4]) if vals[4] else 0,
                "open":       float(vals[5]) if vals[5] else 0,
                "change_amt": float(vals[31]) if vals[31] else 0,
                "change_pct": float(vals[32]) if vals[32] else 0,
                "high":       float(vals[33]) if vals[33] else 0,
                "low":        float(vals[34]) if vals[34] else 0,
                "volume":     float(vals[36]) if vals[36] else 0,   # 成交量(股)
                "amount_wan": float(vals[37]) if vals[37] else 0,   # 成交额(万HKD)
                "mcap_yi":    float(vals[44]) if vals[44] else 0,   # 总市值(亿HKD)
                "pe_ttm":     float(vals[39]) if vals[39] else 0,
                "pb":         float(vals[46]) if vals[46] else 0,
            }
        except (ValueError, IndexError):
            continue
    return result

# 用法: 腾讯/阿里/美团
quotes = tencent_hk_quote(["00700", "09988", "03690"])
for code, q in quotes.items():
    print(f"{q['name']}({code}): {q['price']}HKD 涨{q['change_pct']}% 市值{q['mcap_yi']}亿HKD")
```

### 8.2 东财 push2 港股实时行情

secid 格式：`116.XXXXX`（港股市场代码为116）。

```python
import requests

def eastmoney_hk_quote(hk_code: str) -> dict:
    """
    东财港股实时行情（备用，腾讯不可用时使用）。
    hk_code: "00700" / "700" / "0700.HK" 均可
    返回: {code, name, price, change_pct, pe_ttm, pb, mcap, volume}
    """
    import re
    code = re.sub(r'[^0-9]', '', hk_code).zfill(5)
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f57,f58,f43,f44,f45,f46,f47,f48,f116,f117,f162,f163,f169,f170",
        "secid": f"116.{code}",
    }
    headers = {"User-Agent": UA}
    r = requests.get(url, params=params, headers=headers, timeout=10)
    d = r.json().get("data", {}) or {}
    return {
        "code":       d.get("f57", ""),
        "name":       d.get("f58", ""),
        "price":      (d.get("f43") or 0) / 100,   # 东财港股价格单位为分→港元
        "high":       (d.get("f44") or 0) / 100,
        "low":        (d.get("f45") or 0) / 100,
        "last_close": (d.get("f46") or 0) / 100,
        "volume":     d.get("f47", 0),
        "amount":     d.get("f48", 0),
        "mcap":       d.get("f116", 0),
        "float_mcap": d.get("f117", 0),
        "pe_ttm":     d.get("f162", 0),
        "pb":         d.get("f163", 0),
        "change_amt": (d.get("f169") or 0) / 100,
        "change_pct": d.get("f170", 0),
    }

# 用法
q = eastmoney_hk_quote("00700")
print(f"{q['name']}: {q['price']}HKD 涨{q['change_pct']}% PE={q['pe_ttm']}")
```

> **注意：** 东财港股价格单位为分（fen），需 ÷100 换算为港元。腾讯财经 hk 接口返回的是直接港元价格，无需换算。

### 8.3 Yahoo Finance 港股 K线

Yahoo Finance 免费，无需 key，港股格式为 `XXXXX.HK`（如 `0700.HK`）。

```python
import requests
from datetime import datetime

def yahoo_kline(ticker: str, period: str = "1y", interval: str = "1d") -> list[dict]:
    """
    Yahoo Finance K线，支持 A股(600519.SS)/港股(0700.HK)/美股(AAPL)/指数(^GSPC)。
    period: "5d"/"1mo"/"3mo"/"6mo"/"1y"/"2y"/"5y"/"max"
    interval: "1d"/"1wk"/"1mo"/"60m"/"30m"/"15m"/"5m"/"1m"
    港股延迟15分钟。
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": period, "interval": interval, "includePrePost": "false"}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    d = r.json()
    chart = d.get("chart", {}).get("result", [{}])[0]
    timestamps = chart.get("timestamp", [])
    ohlcv = chart.get("indicators", {}).get("quote", [{}])[0]

    rows = []
    for i, ts in enumerate(timestamps):
        o = (ohlcv.get("open",  []) or [])[i] if i < len(ohlcv.get("open",  [])) else None
        h = (ohlcv.get("high",  []) or [])[i] if i < len(ohlcv.get("high",  [])) else None
        l = (ohlcv.get("low",   []) or [])[i] if i < len(ohlcv.get("low",   [])) else None
        c = (ohlcv.get("close", []) or [])[i] if i < len(ohlcv.get("close", [])) else None
        v = (ohlcv.get("volume",[]) or [])[i] if i < len(ohlcv.get("volume",[])) else None
        if c is None:
            continue
        rows.append({
            "date":   datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"),
            "open":   round(o, 4) if o else 0,
            "high":   round(h, 4) if h else 0,
            "low":    round(l, 4) if l else 0,
            "close":  round(c, 4),
            "volume": int(v) if v else 0,
        })
    return rows

# 用法: 港股
klines = yahoo_kline("0700.HK", period="1y", interval="1d")
print(f"腾讯港股K线: {len(klines)} 根")
print(klines[-5:])

# 用法: 港股周线
weekly = yahoo_kline("9988.HK", period="2y", interval="1wk")

# 用法: A股（Yahoo 也支持，SS=上海 SZ=深圳）
a_kline = yahoo_kline("600519.SS", period="1y")

# 用法: 美股
us_kline = yahoo_kline("NVDA", period="1y")
```

### 8.4 Yahoo Finance 港股/美股 实时报价与关键指标

```python
def yahoo_quote(tickers: list[str]) -> dict[str, dict]:
    """
    Yahoo Finance 实时/延迟报价，支持 港股(0700.HK)/美股(AAPL)/指数(^GSPC)。
    港股延迟15分钟，美股盘中准实时。
    """
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    params = {
        "symbols": ",".join(tickers),
        "fields": (
            "shortName,regularMarketPrice,regularMarketChange,"
            "regularMarketChangePercent,regularMarketVolume,"
            "marketCap,trailingPE,priceToBook,dividendYield,"
            "fiftyTwoWeekHigh,fiftyTwoWeekLow,currency,"
            "regularMarketDayHigh,regularMarketDayLow"
        ),
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    d = r.json()
    result = {}
    for item in d.get("quoteResponse", {}).get("result", []):
        sym = item.get("symbol", "")
        result[sym] = {
            "name":         item.get("shortName", ""),
            "price":        item.get("regularMarketPrice", 0),
            "change":       item.get("regularMarketChange", 0),
            "change_pct":   item.get("regularMarketChangePercent", 0),
            "high":         item.get("regularMarketDayHigh", 0),
            "low":          item.get("regularMarketDayLow", 0),
            "volume":       item.get("regularMarketVolume", 0),
            "mcap":         item.get("marketCap", 0),
            "pe_ttm":       item.get("trailingPE", None),
            "pb":           item.get("priceToBook", None),
            "dividend_yield": item.get("dividendYield", None),
            "52w_high":     item.get("fiftyTwoWeekHigh", 0),
            "52w_low":      item.get("fiftyTwoWeekLow", 0),
            "currency":     item.get("currency", ""),
        }
    return result

def yahoo_key_stats(ticker: str) -> dict:
    """
    Yahoo Finance 财务关键指标（适合港股/美股深度分析）。
    返回: PE/PB/EPS/ROE/ROA/收入/净利润/现金流/股息率/Beta/分析师目标价
    """
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
    params = {"modules": "summaryDetail,defaultKeyStatistics,financialData"}
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    d = r.json().get("quoteSummary", {}).get("result", [{}])[0]

    sd = d.get("summaryDetail", {})
    ks = d.get("defaultKeyStatistics", {})
    fd = d.get("financialData", {})

    def v(obj, key):
        val = obj.get(key, {})
        return val.get("raw") if isinstance(val, dict) else val

    return {
        "pe_ttm":           v(sd, "trailingPE"),
        "pe_fwd":           v(sd, "forwardPE"),
        "pb":               v(sd, "priceToBook"),
        "dividend_yield":   v(sd, "dividendYield"),
        "beta":             v(sd, "beta"),
        "eps_ttm":          v(ks, "trailingEps"),
        "eps_fwd":          v(ks, "forwardEps"),
        "shares_outstanding": v(ks, "sharesOutstanding"),
        "roe":              v(fd, "returnOnEquity"),
        "roa":              v(fd, "returnOnAssets"),
        "profit_margin":    v(fd, "profitMargins"),
        "revenue":          v(fd, "totalRevenue"),
        "net_income":       v(fd, "netIncomeToCommon"),
        "free_cash_flow":   v(fd, "freeCashflow"),
        "total_debt":       v(fd, "totalDebt"),
        "current_ratio":    v(fd, "currentRatio"),
        "target_price":     v(fd, "targetMeanPrice"),
        "analyst_count":    v(fd, "numberOfAnalystOpinions"),
        "recommendation":   fd.get("recommendationKey", ""),
    }

# 用法: 港股批量报价
hk_quotes = yahoo_quote(["0700.HK", "9988.HK", "3690.HK", "1810.HK"])
for sym, q in hk_quotes.items():
    print(f"{q['name']}({sym}): {q['price']}{q['currency']} PE={q['pe_ttm']} 市值={q['mcap']/1e8:.0f}亿HKD")

# 用法: 港股深度指标
stats = yahoo_key_stats("0700.HK")
print(f"PE_fwd={stats['pe_fwd']} ROE={stats['roe']:.1%} 目标价={stats['target_price']} 分析师={stats['analyst_count']}家")
print(f"评级: {stats['recommendation']}")
```

### 8.5 港股财报三表（Yahoo Finance）

```python
def yahoo_financials(ticker: str) -> dict:
    """
    Yahoo Finance 港股/美股财务三表（年报，最近4期）。
    ticker: "0700.HK" / "AAPL"
    返回: {income: [...], balance: [...], cashflow: [...]}
    """
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
    params = {
        "modules": (
            "incomeStatementHistory,"
            "balanceSheetHistory,"
            "cashflowStatementHistory"
        )
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    d = r.json().get("quoteSummary", {}).get("result", [{}])[0]

    def parse_stmts(key, fields):
        stmts = d.get(key, {}).get(key[:-len("History")] + "History", [])
        rows = []
        for s in stmts:
            row = {"date": s.get("endDate", {}).get("fmt", "")}
            for f in fields:
                val = s.get(f, {})
                row[f] = val.get("raw") if isinstance(val, dict) else None
            rows.append(row)
        return rows

    income = parse_stmts("incomeStatementHistory", [
        "totalRevenue", "grossProfit", "operatingIncome",
        "netIncome", "ebitda", "dilutedEPS",
    ])
    balance = parse_stmts("balanceSheetHistory", [
        "totalAssets", "totalLiab", "totalStockholderEquity",
        "cash", "totalCurrentAssets", "totalCurrentLiabilities",
        "longTermDebt",
    ])
    cashflow = parse_stmts("cashflowStatementHistory", [
        "totalCashFromOperatingActivities",
        "capitalExpenditures",
        "freeCashflow",
        "totalCashFromFinancingActivities",
    ])
    return {"income": income, "balance": balance, "cashflow": cashflow}

# 用法: 腾讯港股财报
fin = yahoo_financials("0700.HK")
print("利润表近4年:")
for row in fin["income"]:
    print(f"  {row['date']}: 收入={row['totalRevenue']/1e8:.0f}亿 净利={row['netIncome']/1e8:.0f}亿 EPS={row['dilutedEPS']}")
```

### 8.6 港股大盘指数

```python
def hk_market_indices() -> dict:
    """
    港股主要指数实时行情（Yahoo Finance）。
    返回: {恒生指数: {price, change_pct}, 恒生科技: ..., 恒生国企: ...}
    """
    tickers = {
        "^HSI":    "恒生指数",
        "^HSTECH": "恒生科技",
        "^HSCE":   "恒生国企",
    }
    quotes = yahoo_quote(list(tickers.keys()))
    return {
        name: {
            "price":      quotes[sym]["price"],
            "change_pct": quotes[sym]["change_pct"],
        }
        for sym, name in tickers.items() if sym in quotes
    }

# 用法
indices = hk_market_indices()
for name, data in indices.items():
    direction = "▲" if data["change_pct"] >= 0 else "▼"
    print(f"{name}: {data['price']:.0f} {direction}{abs(data['change_pct']):.2f}%")
```

### 8.7 东财港股研报

```python
def eastmoney_hk_reports(hk_code: str, max_pages: int = 3) -> list[dict]:
    """
    东财港股研报（复用A股 reportapi 接口，传5位港股代码）。
    hk_code: "00700" / "700" / "0700.HK"
    """
    import re
    code = re.sub(r'[^0-9]', '', hk_code).zfill(5)
    return eastmoney_reports(code, max_pages=max_pages)

# 用法
reports = eastmoney_hk_reports("00700")
print(f"腾讯港股研报 {len(reports)} 篇")
for r in reports[:5]:
    print(f"  {r.get('publishDate','')[:10]} | {r.get('orgSName')} | {r.get('title','')[:60]}")
```

---

## Layer 9: 美股数据层（★V4.0 新增）

> **数据源优先级（美股）：** Yahoo Finance（K线/财报/指数，最全面）> 腾讯财经 us前缀（实时行情）> 东财 push2（实时行情备用）

### 9.1 腾讯财经 美股实时行情

```python
def tencent_us_quote(tickers: list[str]) -> dict[str, dict]:
    """
    腾讯财经美股实时行情（延迟约15分钟）。
    tickers: ["AAPL", "NVDA", "TSLA"]
    返回: {ticker: {name, price, change_pct, ...}}
    """
    prefixed = [f"us{t.upper()}" for t in tickers]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")

    result = {}
    for line in raw.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]   # e.g. "usAAPL"
        vals = line.split('"')[1].split("~")
        if len(vals) < 40:
            continue
        ticker = key[2:]  # strip "us"
        try:
            result[ticker] = {
                "name":       vals[1],
                "price":      float(vals[3]) if vals[3] else 0,
                "last_close": float(vals[4]) if vals[4] else 0,
                "open":       float(vals[5]) if vals[5] else 0,
                "change_amt": float(vals[31]) if vals[31] else 0,
                "change_pct": float(vals[32]) if vals[32] else 0,
                "high":       float(vals[33]) if vals[33] else 0,
                "low":        float(vals[34]) if vals[34] else 0,
                "volume":     float(vals[36]) if vals[36] else 0,
            }
        except (ValueError, IndexError):
            continue
    return result

# 用法
quotes = tencent_us_quote(["AAPL", "NVDA", "TSLA", "MSFT"])
for ticker, q in quotes.items():
    print(f"{q['name']}({ticker}): ${q['price']} 涨{q['change_pct']}%")
```

### 9.2 东财 push2 美股实时行情

NASDAQ 股票用 `105.TICKER`，NYSE 用 `106.TICKER`，自动回退探测。

```python
def eastmoney_us_quote(ticker: str) -> dict:
    """
    东财美股实时行情（延迟）。
    ticker: "AAPL" / "TSLA" / "NVDA"
    自动探测 NASDAQ(105) / NYSE(106)
    """
    for market_code in ["105", "106"]:
        secid = f"{market_code}.{ticker.upper()}"
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "fltt": "2", "invt": "2",
            "fields": "f57,f58,f43,f44,f45,f46,f47,f116,f162,f163,f169,f170",
            "secid": secid,
        }
        headers = {"User-Agent": UA}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        d = r.json().get("data", {}) or {}
        if d.get("f43"):
            return {
                "ticker":     d.get("f57", ""),
                "name":       d.get("f58", ""),
                "price":      d.get("f43", 0),
                "high":       d.get("f44", 0),
                "low":        d.get("f45", 0),
                "last_close": d.get("f46", 0),
                "volume":     d.get("f47", 0),
                "mcap":       d.get("f116", 0),
                "pe_ttm":     d.get("f162", 0),
                "pb":         d.get("f163", 0),
                "change_amt": d.get("f169", 0),
                "change_pct": d.get("f170", 0),
                "exchange":   "NASDAQ" if market_code == "105" else "NYSE",
            }
    return {}

# 用法
q = eastmoney_us_quote("NVDA")
if q:
    print(f"{q['name']}({q['ticker']}): ${q['price']} 涨{q['change_pct']}% 交易所={q['exchange']}")
```

### 9.3 Yahoo Finance 美股 K线（同 8.3 通用函数）

```python
# 美股日K
aapl_kline = yahoo_kline("AAPL", period="1y", interval="1d")
print(f"苹果近1年日K: {len(aapl_kline)} 根, 最新收盘={aapl_kline[-1]['close']}")

# 美股1小时线
nvda_hourly = yahoo_kline("NVDA", period="5d", interval="60m")

# 美股周线
tsla_weekly = yahoo_kline("TSLA", period="2y", interval="1wk")
```

### 9.4 Yahoo Finance 美股财报三表（同 8.5 通用函数）

```python
# 苹果财务三表
fin = yahoo_financials("AAPL")
print("苹果利润表近4年:")
for row in fin["income"]:
    print(f"  {row['date']}: 收入={row['totalRevenue']/1e9:.0f}B 净利={row['netIncome']/1e9:.0f}B EPS={row['dilutedEPS']}")

print("\n现金流量表:")
for row in fin["cashflow"]:
    capex = abs(row['capitalExpenditures'] or 0)
    ocf = row['totalCashFromOperatingActivities'] or 0
    print(f"  {row['date']}: 经营现金流={ocf/1e9:.0f}B 资本支出={capex/1e9:.0f}B 自由现金流={row['freeCashflow']/1e9 if row['freeCashflow'] else 'N/A'}B")
```

### 9.5 美股关键指标（同 8.4 yahoo_key_stats）

```python
# 英伟达深度分析
stats = yahoo_key_stats("NVDA")
print(f"PE_ttm={stats['pe_ttm']} PE_fwd={stats['pe_fwd']}")
print(f"EPS_ttm={stats['eps_ttm']} EPS_fwd={stats['eps_fwd']}")
print(f"ROE={stats['roe']:.1%} 利润率={stats['profit_margin']:.1%}")
print(f"分析师目标价=${stats['target_price']} ({stats['analyst_count']}家) 评级={stats['recommendation']}")
print(f"Beta={stats['beta']} 股息率={stats['dividend_yield']}")
```

### 9.6 美股三大指数 + VIX + 美债

```python
def us_market_indices() -> dict:
    """
    美股主要指数/情绪指标实时行情（Yahoo Finance）。
    返回: S&P500/道琼斯/纳斯达克/VIX/10Y美债收益率
    """
    tickers = {
        "^GSPC": "S&P500",
        "^DJI":  "道琼斯",
        "^IXIC": "纳斯达克",
        "^VIX":  "VIX恐慌指数",
        "^TNX":  "10Y美债收益率(%)",
    }
    quotes = yahoo_quote(list(tickers.keys()))
    return {
        name: {
            "price":      quotes[sym]["price"],
            "change_pct": quotes[sym]["change_pct"],
        }
        for sym, name in tickers.items() if sym in quotes
    }

# 用法
indices = us_market_indices()
for name, data in indices.items():
    direction = "▲" if data["change_pct"] >= 0 else "▼"
    print(f"{name}: {data['price']:.2f} {direction}{abs(data['change_pct']):.2f}%")
```

### 9.7 跨市场比较流程

```python
def cross_market_snapshot() -> dict:
    """
    A/港/美三市场全景快照（适合早盘/收盘复盘）。
    """
    # A股指数
    a_indices = tencent_quote(["000001", "000300", "399006", "000688"])

    # 港股指数
    hk_indices = hk_market_indices()

    # 美股指数
    us_indices = us_market_indices()

    return {
        "A股": {
            "上证指数": a_indices.get("000001", {}),
            "沪深300":  a_indices.get("000300", {}),
            "创业板指":  a_indices.get("399006", {}),
            "科创50":   a_indices.get("000688", {}),
        },
        "港股": hk_indices,
        "美股": us_indices,
    }

# 用法
snap = cross_market_snapshot()
print("=== A股 ===")
for name, q in snap["A股"].items():
    if q:
        print(f"  {name}: {q.get('price',0)} 涨{q.get('change_pct',0)}%")
print("=== 港股 ===")
for name, q in snap["港股"].items():
    print(f"  {name}: {q['price']:.0f} 涨{q['change_pct']:.2f}%")
print("=== 美股 ===")
for name, q in snap["美股"].items():
    print(f"  {name}: {q['price']:.2f} 涨{q['change_pct']:.2f}%")
```

---

## Layer 10: 美股/港股深度数据层（★V5.0 蒸馏自 global-stock-data）

> **来源：** 蒸馏自 simonlin1212/global-stock-data（美股港股全栈工具包），保留本层全部实测通过的端点。
> **实测验证：** 2026-06-04 本层 11 个联网端点全部实测通过（技术指标为纯 Python 计算）。
> **与已有层的关系：** 本层补齐 A股层没有的能力——技术指标计算、美股/港股深度基本面、期权链、SEC EDGAR、分析师预期、机构持仓。Yahoo 相关函数统一走下面的 crumb 管理器，比 Layer 8/9 的裸 Yahoo 调用更抗 401。

### 10.0 Yahoo crumb 管理器（本层 Yahoo 函数共用）

Yahoo quoteSummary / options 等 v7/v10 接口需要 cookie+crumb，以下 helper 自动获取并缓存：

```python
import requests, re, json

_yahoo_session = None

def get_yahoo_session() -> requests.Session:
    """获取带 crumb 的 Yahoo Finance session（自动缓存）"""
    global _yahoo_session
    if _yahoo_session and hasattr(_yahoo_session, '_crumb'):
        return _yahoo_session
    s = requests.Session()
    s.headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    s.get('https://fc.yahoo.com', timeout=10)                                  # Step1 拿 cookie
    r = s.get('https://query2.finance.yahoo.com/v1/test/getcrumb', timeout=10)  # Step2 拿 crumb
    r.raise_for_status()
    s._crumb = r.text
    _yahoo_session = s
    return s

def yahoo_quote_summary(symbol: str, modules: list) -> dict:
    """Yahoo quoteSummary 统一查询。symbol: 美股 'AAPL' / 港股 '0700.HK'"""
    s = get_yahoo_session()
    r = s.get(f'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}',
              params={'modules': ','.join(modules), 'crumb': s._crumb}, timeout=15)
    r.raise_for_status()
    results = r.json().get('quoteSummary', {}).get('result', [{}])
    return results[0] if results else {}
```

> **东财 datacenter 统一查询** 复用 Layer 0 的 `eastmoney_datacenter()`（见“东财数据中心统一查询（共用 helper）”）。本层调用约定参数：`secucode` 美股用 `AAPL.O`(NASDAQ)/`BABA.N`(NYSE)，港股用 `00700.HK`。

### 10.1 技术指标层（纯 Python，基于 K线 OHLCV，适用全市场 A股/港股/美股）

**使用方式：** 先用任一 K 线函数取数据（如 Layer 8.3 `yahoo_kline` 或新浪美股K线 10.6），再传入技术指标函数。klines 需为 `[{date, open, high, low, close, volume}, ...]`。

```python
def _ema(values: list, period: int) -> list:
    """EMA 指数移动平均（内部辅助）"""
    result = [values[0]]
    k = 2 / (period + 1)
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def calc_ma(klines: list, periods: list = None) -> list:
    """移动平均线 MA + EMA12/26。periods 默认 [5,10,20,60]
    返回: [{date, close, ma5, ma10, ma20, ma60, ema12, ema26}, ...]"""
    if periods is None:
        periods = [5, 10, 20, 60]
    closes = [k["close"] for k in klines]
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    result = []
    for i, k in enumerate(klines):
        row = {"date": k["date"], "close": k["close"]}
        for p in periods:
            row[f"ma{p}"] = round(sum(closes[i - p + 1:i + 1]) / p, 4) if i >= p - 1 else None
        row["ema12"], row["ema26"] = round(ema12[i], 4), round(ema26[i], 4)
        result.append(row)
    return result


def calc_macd(klines: list, fast: int = 12, slow: int = 26, signal: int = 9) -> list:
    """MACD。dif=EMA(fast)-EMA(slow)，dea=EMA(signal) of dif，macd_hist=(dif-dea)*2
    金叉/死叉看 dif 穿越 dea；柱状图红涨绿跌
    返回: [{date, close, dif, dea, macd_hist}, ...]"""
    closes = [k["close"] for k in klines]
    ema_fast, ema_slow = _ema(closes, fast), _ema(closes, slow)
    dif = [round(f - s, 4) for f, s in zip(ema_fast, ema_slow)]
    dea = _ema(dif, signal)
    return [{"date": k["date"], "close": k["close"], "dif": round(dif[i], 4),
             "dea": round(dea[i], 4), "macd_hist": round((dif[i] - dea[i]) * 2, 4)}
            for i, k in enumerate(klines)]


def calc_rsi(klines: list, periods: list = None) -> list:
    """RSI。periods 默认 [6,12,24]。>70 超买，<30 超卖
    返回: [{date, close, rsi6, rsi12, rsi24}, ...]"""
    if periods is None:
        periods = [6, 12, 24]
    closes = [k["close"] for k in klines]
    changes = [0.0] + [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    result = []
    for i, k in enumerate(klines):
        row = {"date": k["date"], "close": k["close"]}
        for p in periods:
            if i < p:
                row[f"rsi{p}"] = None
                continue
            avg_gain = sum(gains[i - p + 1:i + 1]) / p
            avg_loss = sum(losses[i - p + 1:i + 1]) / p
            row[f"rsi{p}"] = 100.0 if avg_loss == 0 else round(100 - 100 / (1 + avg_gain / avg_loss), 2)
        result.append(row)
    return result


def calc_kdj(klines: list, n: int = 9, m1: int = 3, m2: int = 3) -> list:
    """KDJ 随机指标。K/D>80 超买，<20 超卖；J>100 或 J<0 极端；K上穿D金叉
    返回: [{date, close, k, d, j}, ...]"""
    k_val, d_val = 50.0, 50.0
    result = []
    for i, kline in enumerate(klines):
        if i < n - 1:
            result.append({"date": kline["date"], "close": kline["close"], "k": None, "d": None, "j": None})
            continue
        window = klines[i - n + 1:i + 1]
        high_n = max(w["high"] for w in window)
        low_n = min(w["low"] for w in window)
        rsv = (kline["close"] - low_n) / (high_n - low_n) * 100 if high_n != low_n else 50.0
        k_val = (1 / m1) * rsv + (1 - 1 / m1) * k_val
        d_val = (1 / m2) * k_val + (1 - 1 / m2) * d_val
        result.append({"date": kline["date"], "close": kline["close"],
                       "k": round(k_val, 2), "d": round(d_val, 2), "j": round(3 * k_val - 2 * d_val, 2)})
    return result


def calc_boll(klines: list, period: int = 20, num_std: float = 2.0) -> list:
    """布林带。触 upper 超买/触 lower 超卖；bandwidth 收窄→即将变盘
    返回: [{date, close, upper, middle, lower, bandwidth}, ...]"""
    closes = [k["close"] for k in klines]
    result = []
    for i, k in enumerate(klines):
        if i < period - 1:
            result.append({"date": k["date"], "close": k["close"],
                           "upper": None, "middle": None, "lower": None, "bandwidth": None})
            continue
        window = closes[i - period + 1:i + 1]
        ma = sum(window) / period
        std = (sum((x - ma) ** 2 for x in window) / period) ** 0.5
        upper, lower = ma + num_std * std, ma - num_std * std
        result.append({"date": k["date"], "close": k["close"], "upper": round(upper, 4),
                       "middle": round(ma, 4), "lower": round(lower, 4),
                       "bandwidth": round((upper - lower) / ma * 100, 2) if ma else None})
    return result
```

### 10.2 关键财务指标(中文) — 东财 GMAININDICATOR（美股49字段 / 港股75字段）

```python
def key_indicators_eastmoney(secucode: str, page_size: int = 4) -> list:
    """东财 GMAININDICATOR 中文关键财务指标。secucode: 'AAPL.O'/'BABA.N'/'00700.HK'
    page_size: 最近几期（默认4=一年）
    美股核心字段: OPERATE_INCOME(营收), GROSS_PROFIT_RATIO(毛利率%), PARENT_HOLDER_NETPROFIT(归母净利),
      NET_PROFIT_RATIO(净利率%), BASIC_EPS, ROE_AVG(平均ROE%), ROA, CURRENT_RATIO(流动比率),
      DEBT_ASSET_RATIO(资产负债率%), OPERATE_INCOME_YOY(营收同比%), BASIC_EPS_YOY(EPS同比%)
    港股额外字段: BPS(每股净资产), ROIC, HOLDER_PROFIT(股东应占溢利), DPS_HKD(每股股息),
      DIVI_RATIO(股息率%), PER_NETCASH_OPERATE(每股经营现金流)"""
    market = "HK" if secucode.endswith(".HK") else "US"
    return eastmoney_datacenter(
        report_name=f"RPT_{market}F10_FN_GMAININDICATOR",
        filter_str=f'(SECUCODE="{secucode}")',
        page_size=page_size, sort_columns="REPORT_DATE", sort_types="-1")
```

### 10.3 财报三表(中文) — 东财 datacenter（美股/港股，按科目行展开）

```python
def financial_statements_eastmoney(secucode: str, statement: str = "balance", page_size: int = 200) -> list:
    """东财 datacenter 财报三表。secucode: 'AAPL.O'/'BABA.N'/'00700.HK'
    statement: 'balance'/'income'/'cashflow'
    返回按科目行展开，用 REPORT_DATE 分组还原整张报表
    每行字段: ITEM_NAME(科目名), AMOUNT(金额), YOY_RATIO(同比%), REPORT(如'2026/Q2'),
      ACCOUNT_STANDARD(会计准则), CURRENCY(币种)
    注: balance/income 用 F10 报表名，cashflow 用 SK 报表名（命名不统一）"""
    report_map = {
        "balance": {"us": "RPT_USF10_FN_BALANCE", "hk": "RPT_HKF10_FN_BALANCE"},
        "income":  {"us": "RPT_USF10_FN_INCOME",  "hk": "RPT_HKF10_FN_INCOME"},
        "cashflow": {"us": "RPT_USSK_FN_CASHFLOW", "hk": "RPT_HKSK_FN_CASHFLOW"},
    }
    market = "hk" if secucode.endswith(".HK") else "us"
    return eastmoney_datacenter(
        report_name=report_map[statement][market],
        filter_str=f'(SECUCODE="{secucode}")',
        page_size=page_size, sort_columns="REPORT_DATE", sort_types="-1")
```

### 10.4 关键财务指标(英文) — Yahoo quoteSummary

```python
def key_statistics(symbol: str) -> dict:
    """Yahoo 关键财务指标。symbol: 'AAPL'(美股) 或 '0700.HK'(港股)
    返回 PE/PB/EV/EBITDA/利润率/目标价/ROE/Beta/股息 等"""
    data = yahoo_quote_summary(symbol, ["financialData", "defaultKeyStatistics", "summaryDetail"])
    fd, ks, sd = data.get("financialData", {}), data.get("defaultKeyStatistics", {}), data.get("summaryDetail", {})
    def _v(d, key):
        v = d.get(key, {})
        return v.get("raw") if isinstance(v, dict) else v
    return {
        "current_price": _v(fd, "currentPrice"), "target_mean": _v(fd, "targetMeanPrice"),
        "target_high": _v(fd, "targetHighPrice"), "target_low": _v(fd, "targetLowPrice"),
        "recommendation": fd.get("recommendationKey"),  # buy/hold/sell
        "trailing_pe": _v(sd, "trailingPE"), "forward_pe": _v(ks, "forwardPE"),
        "peg_ratio": _v(ks, "pegRatio"), "price_to_book": _v(ks, "priceToBook"),
        "enterprise_value": _v(ks, "enterpriseValue"), "ev_to_ebitda": _v(ks, "enterpriseToEbitda"),
        "ev_to_revenue": _v(ks, "enterpriseToRevenue"),
        "profit_margin": _v(ks, "profitMargins"), "operating_margin": _v(fd, "operatingMargins"),
        "gross_margin": _v(fd, "grossMargins"), "return_on_equity": _v(fd, "returnOnEquity"),
        "return_on_assets": _v(fd, "returnOnAssets"),
        "earnings_growth": _v(fd, "earningsGrowth"), "revenue_growth": _v(fd, "revenueGrowth"),
        "beta": _v(ks, "beta"), "short_ratio": _v(ks, "shortRatio"),
        "dividend_yield": _v(sd, "dividendYield"), "payout_ratio": _v(ks, "payoutRatio"),
        "market_cap": _v(sd, "marketCap"), "total_revenue": _v(fd, "totalRevenue"),
        "total_cash": _v(fd, "totalCash"), "total_debt": _v(fd, "totalDebt"),
    }
```

### 10.5 分析师预期 / 评级 / 升降级 — Yahoo quoteSummary

```python
def analyst_estimates(symbol: str) -> dict:
    """Yahoo 分析师预期 — EPS预测/评级趋势/升降级历史。symbol: 'AAPL' 或 '0700.HK'"""
    data = yahoo_quote_summary(symbol, ["earningsTrend", "recommendationTrend",
                                        "upgradeDowngradeHistory", "earnings", "earningsHistory"])
    eps_trend = [{
        "period": t.get("period"), "end_date": t.get("endDate"),
        "eps_estimate": t.get("earningsEstimate", {}).get("avg", {}).get("raw"),
        "eps_high": t.get("earningsEstimate", {}).get("high", {}).get("raw"),
        "eps_low": t.get("earningsEstimate", {}).get("low", {}).get("raw"),
        "revenue_estimate": t.get("revenueEstimate", {}).get("avg", {}).get("raw"),
        "num_analysts": t.get("earningsEstimate", {}).get("numberOfAnalysts", {}).get("raw"),
    } for t in data.get("earningsTrend", {}).get("trend", [])]
    rating_trend = [{"period": r.get("period"), "strong_buy": r.get("strongBuy"), "buy": r.get("buy"),
                     "hold": r.get("hold"), "sell": r.get("sell"), "strong_sell": r.get("strongSell")}
                    for r in data.get("recommendationTrend", {}).get("trend", [])]
    upgrades = [{"date": u.get("epochGradeDate"), "firm": u.get("firm"), "to_grade": u.get("toGrade"),
                 "from_grade": u.get("fromGrade"), "action": u.get("action")}  # up/down/main/init
                for u in data.get("upgradeDowngradeHistory", {}).get("history", [])[:20]]
    return {"eps_trend": eps_trend, "rating_trend": rating_trend, "upgrade_downgrade": upgrades}
```

### 10.6 机构持仓 — Yahoo quoteSummary

```python
def institutional_holders(symbol: str) -> dict:
    """Yahoo 机构持仓 — 前10大机构 + 内部人持股比例。symbol: 'AAPL' 或 '0700.HK'"""
    data = yahoo_quote_summary(symbol, ["institutionOwnership", "majorHoldersBreakdown"])
    mhb = data.get("majorHoldersBreakdown", {})
    def _v(d, key):
        v = d.get(key, {})
        return v.get("raw") if isinstance(v, dict) else v
    overview = {"insiders_pct": _v(mhb, "insidersPercentHeld"),
                "institutions_pct": _v(mhb, "institutionsPercentHeld"),
                "institutions_float_pct": _v(mhb, "institutionsFloatPercentHeld"),
                "institutions_count": _v(mhb, "institutionsCount")}
    top_holders = [{"name": h.get("organization"), "shares": _v(h, "position"),
                    "value": _v(h, "value"), "pct_held": _v(h, "pctHeld"),
                    "report_date": h.get("reportDate", {}).get("fmt") if isinstance(h.get("reportDate"), dict) else None}
                   for h in data.get("institutionOwnership", {}).get("ownershipList", [])[:10]]
    return {"overview": overview, "top_holders": top_holders}
```

### 10.7 期权链 — Yahoo Finance（仅美股）

```python
def options_chain(symbol: str, expiration: int = None) -> dict:
    """Yahoo 期权链 calls+puts（仅美股；港股不在覆盖范围会返回空）
    symbol: 'AAPL'/'TSLA'；expiration: Unix 时间戳（不传则返回最近到期日+全部到期日列表）
    返回: {expiration_dates:[...时间戳...], calls:[...], puts:[...], underlying_price}"""
    s = get_yahoo_session()
    params = {"crumb": s._crumb}
    if expiration:
        params["date"] = expiration
    r = s.get(f"https://query2.finance.yahoo.com/v7/finance/options/{symbol}", params=params, timeout=15)
    r.raise_for_status()
    oc = r.json().get("optionChain", {}).get("result", [{}])[0]
    options = oc.get("options", [{}])[0] if oc.get("options") else {}
    def _parse(opts):
        out = []
        for o in opts:
            def _v(key):
                v = o.get(key, {})
                return v.get("raw") if isinstance(v, dict) else v
            out.append({"strike": _v("strike"), "last_price": _v("lastPrice"), "bid": _v("bid"),
                        "ask": _v("ask"), "volume": _v("volume"), "open_interest": _v("openInterest"),
                        "implied_volatility": _v("impliedVolatility"), "in_the_money": o.get("inTheMoney"),
                        "contract_symbol": o.get("contractSymbol")})
        return out
    return {"expiration_dates": oc.get("expirationDates", []),
            "calls": _parse(options.get("calls", [])), "puts": _parse(options.get("puts", [])),
            "underlying_price": oc.get("quote", {}).get("regularMarketPrice")}
```

### 10.8 SEC EDGAR — Filing 列表 / XBRL 结构化财务 / Ticker→CIK（仅美股，官方数据）

```python
SEC_HEADERS = {"User-Agent": "stock-data research/1.0 (contact@example.com)"}  # SEC 要求带 UA
_cik_cache = None

def ticker_to_cik(ticker: str) -> dict:
    """SEC ticker→CIK 映射。返回 {ticker, cik(10位补零), company}。首次下载全表缓存"""
    global _cik_cache
    if not _cik_cache:
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS, timeout=15)
        r.raise_for_status()
        _cik_cache = r.json()
    tu = ticker.upper()
    for _, v in _cik_cache.items():
        if v.get("ticker") == tu:
            return {"ticker": tu, "cik": str(v["cik_str"]).zfill(10), "company": v.get("title")}
    return {}


def sec_filings(cik: str, form_type: str = None) -> dict:
    """SEC EDGAR Filing 列表。cik: 10位补零如 '0000320193'(Apple)；form_type 如 '10-K'/'10-Q'/'8-K'
    返回 {company_name, cik, ticker, filings:[{form, date, accession_number, primary_document, url}]}"""
    r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=SEC_HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    filings = []
    for i in range(len(forms)):
        if form_type and forms[i] != form_type:
            continue
        doc = docs[i] if i < len(docs) else ""
        filings.append({"form": forms[i], "date": dates[i], "accession_number": accessions[i],
                        "primary_document": doc,
                        "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accessions[i].replace('-', '')}/{doc}" if doc else ""})
    return {"company_name": data.get("name"), "cik": cik,
            "ticker": (data.get("tickers") or [""])[0], "filings": filings[:50]}


def sec_xbrl_facts(cik: str, metrics: list = None) -> dict:
    """SEC EDGAR XBRL 结构化财务（503个GAAP指标）。cik: 10位补零
    metrics 不传→返回所有可用指标名；传入→提取指定指标多期数据（只取10-K/10-Q，最近20条）
    常用 XBRL 名: 营收 RevenueFromContractWithCustomerExcludingAssessedTax / Revenues,
      净利 NetIncomeLoss, 稀释EPS EarningsPerShareDiluted, 总资产 Assets, 总负债 Liabilities,
      股东权益 StockholdersEquity, 经营现金流 NetCashProvidedByOperatingActivities,
      研发 ResearchAndDevelopmentExpense, 回购 PaymentsForRepurchaseOfCommonStock"""
    r = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", headers=SEC_HEADERS, timeout=20)
    r.raise_for_status()
    facts = r.json()
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    if not metrics:
        available = [{"name": k, "label": v.get("label", k), "units": list(v.get("units", {}).keys())}
                     for k, v in us_gaap.items()]
        return {"company": facts.get("entityName"), "total_metrics": len(available), "available_metrics": available}
    result = {}
    for m in metrics:
        units = us_gaap.get(m, {}).get("units", {})
        if not units:
            result[m] = []
            continue
        unit_key = "USD" if "USD" in units else list(units.keys())[0]
        entries = [e for e in units[unit_key] if e.get("form") in ("10-K", "10-Q")]
        result[m] = [{"end": e.get("end"), "val": e.get("val"), "form": e.get("form"),
                      "filed": e.get("filed"), "fy": e.get("fy"), "fp": e.get("fp")} for e in entries[-20:]]
    return {"company": facts.get("entityName"), "metrics": result}
```

### 10.9 全球股票搜索 — 东财 search API（中英文，返回 secid 映射）

```python
def stock_search_global(keyword: str, count: int = 10) -> list:
    """东财全球搜索。keyword: 'AAPL'/'苹果'/'Tencent'/'00700'/'特斯拉'
    返回: [{code, name, mkt_num, market_name, security_type}]
    mkt_num 即 secid 前缀: 105=NASDAQ, 106=NYSE, 107=美股ETF, 116=港股"""
    r = requests.get("https://searchapi.eastmoney.com/api/suggest/get",
                     params={"input": keyword, "type": 14, "token": "D43BF722C8E33BDC906FB84D85E326E8", "count": count},
                     timeout=10)
    market_map = {"105": "NASDAQ", "106": "NYSE", "107": "US_OTHER", "116": "HK"}
    out = []
    for s in r.json().get("QuotationCodeTable", {}).get("Data", []):
        mkt = str(s.get("MktNum", ""))
        if mkt not in market_map:
            continue
        out.append({"code": s.get("Code"), "name": s.get("Name"), "mkt_num": int(mkt),
                    "market_name": market_map[mkt], "security_type": s.get("SecurityTypeName")})
    return out
```

### 10.10 美股/港股新闻 — Yahoo Finance search

```python
def stock_news_yahoo(keyword: str, count: int = 10) -> list:
    """Yahoo 新闻搜索。keyword: 'AAPL'/'Tesla'/'0700.HK'
    返回: [{title, publisher, link, publish_time, thumbnail}]（需先拿 cookie，否则 400）"""
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    s.get("https://fc.yahoo.com", timeout=10)
    r = s.get("https://query2.finance.yahoo.com/v1/finance/search",
              params={"q": keyword, "quotesCount": 0, "newsCount": count}, timeout=10)
    r.raise_for_status()
    return [{"title": n.get("title"), "publisher": n.get("publisher"), "link": n.get("link"),
             "publish_time": n.get("providerPublishTime"),
             "thumbnail": (n.get("thumbnail", {}).get("resolutions") or [{}])[0].get("url") if n.get("thumbnail") else None}
            for n in r.json().get("news", [])]
```

### 10.11 新浪美股 K线（回溯至 1984 年）

> Layer 8.3 的 Yahoo K线已覆盖美股/港股多周期。新浪美股 K线作为**超长历史**补充源（实测可取近万根日线），且无需 crumb。

```python
def us_stock_kline_sina(ticker: str, num: int = 120) -> list:
    """新浪美股日K — 可回溯至1984年。ticker: 'AAPL'
    返回: [{date, open, high, low, close, volume}, ...]（升序，末尾为最新）"""
    r = requests.get("https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var/US_MinKService.getDailyK",
                     params={"symbol": ticker.upper(), "num": num},
                     headers={"Referer": "https://finance.sina.com.cn/"}, timeout=15)
    m = re.search(r'\((\[.+\])\)', r.text)
    if not m:
        return []
    return [{"date": it.get("d"), "open": float(it.get("o", 0)), "high": float(it.get("h", 0)),
             "low": float(it.get("l", 0)), "close": float(it.get("c", 0)), "volume": int(it.get("v", 0))}
            for it in json.loads(m.group(1))]
```

### 10.12 本层典型组合用法

```python
# 美股深度调研一条龙（以 AAPL 为例）
info  = ticker_to_cik("AAPL")                          # → CIK
kstat = key_statistics("AAPL")                         # Yahoo 估值/利润率/目标价
gmi   = key_indicators_eastmoney("AAPL.O")             # 东财中文 ROE/毛利率/资产负债率
est   = analyst_estimates("AAPL")                      # 分析师 EPS 预测 + 评级趋势
inst  = institutional_holders("AAPL")                  # 机构持仓
xbrl  = sec_xbrl_facts(info["cik"], ["NetIncomeLoss", "Revenues", "EarningsPerShareDiluted"])  # SEC 官方多年财务
# 技术面（先取K线再算指标）
kl    = yahoo_kline("AAPL", period="6mo", interval="1d")   # Layer 8.3（升序，技术指标直接吃）
macd, rsi, boll = calc_macd(kl), calc_rsi(kl), calc_boll(kl)

# 港股深度（GMAININDICATOR 港股75字段含股息率，期权/SEC 不适用港股）
hk_gmi  = key_indicators_eastmoney("00700.HK")
hk_stat = key_statistics("0700.HK")
```

> **不适用提醒：** 期权链(10.7)、SEC(10.8) 仅美股；港股深度走 GMAININDICATOR(10.2) + Yahoo quoteSummary(10.4-10.6)。东财 push2 全市场涨跌幅列表端点（原 global-stock-data Layer 8.4）2026-06-04 实测美股返回空，已知不稳，本次未并入。

---

## 估值计算公式

### 前向PE

```python
def forward_pe(price: float, eps_forecast: float) -> float:
    """前向PE = 当前股价 / 未来年度一致预期EPS"""
    if eps_forecast <= 0:
        return float("inf")
    return price / eps_forecast
```

### PE消化时间

```python
import math

def pe_digestion(current_pe: float, cagr: float, target_pe: float = 30) -> float:
    """
    当前PE消化到目标PE需要多少年。
    target_pe 固定30x（A股成长股合理估值锚点）。
    cagr: 用 下一年EPS / 当年EPS - 1
    """
    if current_pe <= target_pe:
        return 0.0
    if cagr <= 0:
        return float("inf")
    return math.log(current_pe / target_pe) / math.log(1 + cagr)
```

### PEG

```python
def calc_peg(pe: float, cagr: float) -> float:
    """
    PEG = 前向PE / (CAGR * 100)
    PEG < 1   → 便宜
    PEG 1-1.5 → 合理
    PEG > 1.5 → 贵
    """
    if cagr <= 0:
        return float("inf")
    return pe / (cagr * 100)
```

### 投资框架速查

```
壁垒 → 增速 → PE消化 → PEG校验

1. 有壁垒吗？(tech_moat / capacity_moat) → 没有则排除
2. 增速多少？(CAGR > 30% 才有意义)
3. PE多久消化到30x？(< 2年合理, > 4年太贵)
4. PEG多少？(< 1 便宜, 1-1.5 合理, > 1.5 贵)

30x PE 锚点: A股成长股的合理估值重力线，所有行业统一用30x。
期权定价例外: PEG > 3 但壁垒极深时，本质是看涨期权，不适用PEG框架。
```

---

## 完整调研流程

### 流程 A: 单票完整估值（30秒）

```python
import requests
import urllib.request
import math
import pandas as pd

def full_valuation(code: str) -> dict:
    """单票完整估值分析"""
    # 1. 腾讯实时行情
    prefix = "sh" if code.startswith(("6","9")) else ("bj" if code.startswith("8") else "sz")
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    vals = data.split('"')[1].split("~")
    price = float(vals[3])
    mcap = float(vals[44])
    pe_ttm = float(vals[39]) if vals[39] else 0
    pb = float(vals[46]) if vals[46] else 0

    # 2. 机构一致预期（直连同花顺）
    df = ths_eps_forecast(code)
    eps_cur = eps_next = None
    analyst_count = 0
    if not df.empty and len(df.columns) >= 3:
        # 解析表格（列结构因页面可能变化，取前两行数据行）
        try:
            for i, row in df.iterrows():
                if i == 0:
                    eps_cur = float(row.iloc[2]) if pd.notna(row.iloc[2]) else None
                    analyst_count = int(row.iloc[1]) if pd.notna(row.iloc[1]) else 0
                elif i == 1:
                    eps_next = float(row.iloc[2]) if pd.notna(row.iloc[2]) else None
        except (ValueError, IndexError):
            pass

    # 3. 估值指标
    pe_fwd = price / eps_cur if eps_cur else float("inf")
    cagr = (eps_next / eps_cur - 1) if (eps_cur and eps_next) else 0
    peg = pe_fwd / (cagr * 100) if cagr > 0 else float("inf")
    digest = (
        math.log(pe_fwd / 30) / math.log(1 + cagr)
        if pe_fwd > 30 and cagr > 0 else 0
    )

    return {
        "name": vals[1],
        "price": price,
        "mcap_yi": mcap,
        "pe_ttm": pe_ttm,
        "pb": pb,
        "eps_cur": eps_cur,
        "eps_next": eps_next,
        "pe_fwd": round(pe_fwd, 1) if eps_cur else None,
        "cagr_pct": round(cagr * 100, 0) if cagr else None,
        "peg": round(peg, 2) if peg != float("inf") else None,
        "digest_years": round(digest, 1),
        "analyst_count": analyst_count,
    }

# 用法
result = full_valuation("688017")
print(result)
```

### 流程 B: 批量估值对比

```python
stocks = ["688017", "300308", "300476", "002463"]
for code in stocks:
    try:
        r = full_valuation(code)
        print(f"{r['name']}({code}): PE_fwd={r['pe_fwd']}x PEG={r['peg']} 消化={r['digest_years']}年 覆盖={r['analyst_count']}家")
    except Exception as e:
        print(f"{code}: 失败 - {e}")
```

### 流程 C: 主题研报批量检索

```python
# Step 1: iwencai 多 query 语义搜索
queries = [
    "人形机器人产业链深度 2026",
    "人形机器人减速器 丝杠",
    "特斯拉Optimus 国产供应链",
]
seen_uids = set()
all_articles = []
for q in queries:
    arts = iwencai_search(q, channel="report", size=50)
    for a in arts:
        uid = a.get("uid", "")
        if uid not in seen_uids:
            seen_uids.add(uid)
            all_articles.append(a)
print(f"共 {len(all_articles)} 篇去重后研报")

# Step 2: 东财补充同标的研报 + PDF
for a in all_articles[:10]:
    stocks = a.get("stock_infos") or []
    for s in stocks:
        stock_code = s.get("code", "")
        if stock_code:
            em = eastmoney_reports(stock_code, max_pages=1)
            print(f"  {stock_code}: 东财 {len(em)} 篇")
```

### 流程 D: 新标的快速调研（V3.0 增强版）

```python
code = "688017"

# 1. 有无机构覆盖？
forecast = ths_eps_forecast(code)
print(f"机构覆盖: {'有' if not forecast.empty else '无'}")

# 2. 实时估值
quotes = tencent_quote([code])
q = quotes[code]
print(f"PE={q['pe_ttm']} PB={q['pb']} 市值={q['mcap_yi']}亿")

# 3. PE消化 → 用 full_valuation()
# 4. PEG校验

# 5. 概念板块归属
blocks = baidu_concept_blocks(code)
print(f"概念: {', '.join(blocks['concept_tags'][:10])}")

# 6. 资金流向（百度分钟级）
flow = baidu_fund_flow_history(code)
if flow:
    recent = flow[0]
    print(f"最近主力净流入: {recent['mainIn']}万")

# 7. 资金流向（东财120日）
flow_120 = stock_fund_flow_120d(code)
if flow_120:
    total = sum(d["main_net"] for d in flow_120[-20:])
    print(f"近20日主力累计净流入: {total/1e8:.2f}亿")

# 8. 龙虎榜
dtb = dragon_tiger_board(code, "2026-05-17")
print(f"近30日上龙虎榜: {len(dtb['records'])} 次")

# 9. 解禁预警
lockup = lockup_expiry(code, "2026-05-17")
print(f"未来90天待解禁: {len(lockup['upcoming'])} 批")

# 10. 融资融券
margin = margin_trading(code, page_size=5)
if margin:
    print(f"最新融资余额: {margin[0]['rzye']/1e8:.2f}亿")

# 11. 股东户数
holders = holder_num_change(code)
if holders:
    print(f"最新股东数: {holders[0]['holder_num']} 环比{holders[0]['change_ratio']}%")
```

---

## 数据源优先级

### A股

| 优先级 | 数据源 | 用途 | 可靠性 | 封IP风险 |
|--------|--------|------|--------|---------|
| 1 | **mootdx** (TCP) | K线+五档盘口+逐笔成交+财务快照+F10 | 极稳定 | 极低 |
| 2 | **腾讯财经** (HTTP) | 实时PE/PB/市值/换手率/涨跌停/指数/ETF | 稳定 | 低 |
| 3 | **东财 datacenter** (HTTP) | 龙虎榜/解禁/融资融券/大宗交易/股东户数/分红 | 稳定 | 低 |
| 4 | **东财 push2/push2his** (HTTP) | 行业板块/个股资金流分钟级+120日 | 稳定 | 低 |
| 5 | **iwencai** (OpenAPI) | NL主题搜索研报(唯一能力) | 需X-Claw Header | 低 |
| 6 | **东财 reportapi/PDF** (HTTP) | 完整研报图表、评级 | 稳定 | 低 |
| 7 | **同花顺热点** (HTTP) | 当日强势股+题材归因 reason tags | 稳定 73ms | 极低（零鉴权） |
| 8 | **同花顺 hsgtApi** (HTTP) | 北向资金分钟级+自缓存历史 | 稳定 | 极低（零鉴权） |
| 9 | **百度股市通** (HTTP) | 概念板块+K线带MA | 稳定 | 极低（零鉴权） |
| 10 | **新浪财经** (HTTP) | 资产负债表/利润表/现金流量表 | 稳定 | 低 |
| 11 | **同花顺 basic** (HTTP) | 一致预期EPS | 稳定(需UA) | 低 |
| 12 | **财联社** (HTTP) | 全市场实时电报 | 稳定 | 低 |
| 13 | **巨潮 cninfo** (HTTP) | 公告全文检索+下载 | 稳定 | 低 |

### 港股（★V4.0 新增）

| 优先级 | 数据源 | 用途 | 可靠性 | 备注 |
|--------|--------|------|--------|------|
| 1 | **腾讯财经 hk前缀** (HTTP) | 实时行情/PE/PB/市值 | 稳定 | hk00700格式，延迟极低 |
| 2 | **Yahoo Finance** (HTTP) | K线/财报三表/关键指标/分析师目标价 | 稳定 | 0700.HK格式，15分钟延迟 |
| 3 | **东财 push2** (HTTP) | 实时行情备用 | 稳定 | secid 116.XXXXX，价格单位为分 |
| 4 | **Yahoo Finance** (HTTP) | 恒生指数/恒生科技/恒生国企 | 稳定 | ^HSI/^HSTECH/^HSCE |
| 5 | **东财 reportapi** (HTTP) | 港股研报 | 稳定 | 5位港股代码 |

### 美股（★V4.0 新增）

| 优先级 | 数据源 | 用途 | 可靠性 | 备注 |
|--------|--------|------|--------|------|
| 1 | **Yahoo Finance** (HTTP) | K线/财报三表/关键指标/三大指数/VIX | 稳定 | 最全面，无需key |
| 2 | **腾讯财经 us前缀** (HTTP) | 实时行情（延迟） | 稳定 | usAAPL格式 |
| 3 | **东财 push2** (HTTP) | 实时行情备用 | 稳定 | 105=NASDAQ, 106=NYSE |

**原则（A股）：** 行情走 mootdx+腾讯（不封IP），研报走东财+iwencai，资金面走东财 datacenter+push2，信号层走同花顺+百度+东财直连。

**原则（港股）：** 实时行情首选腾讯hk前缀，K线/财报/深度分析走 Yahoo Finance，研报走东财。

**原则（美股）：** Yahoo Finance 一站覆盖（K线+财报+指数），实时行情备用腾讯us前缀或东财push2。

---

## FAQ

### Q: mootdx 和腾讯有什么区别？
A: 互补关系。mootdx = 交易层（价格+盘口+K线），腾讯 = 估值层（PE/PB/市值/换手率/涨跌停价）。两者都不封IP。

### Q: V3.0 为什么移除 akshare？
A: akshare 本质是对东财/同花顺/新浪等公开 API 的封装，中间层增加了故障点（版本兼容 bug、pandas 3.0 ArrowInvalid 等）。V3.0 直连底层 HTTP API，零中间依赖，更稳定可控。

### Q: iwencai 返回 401
A: 检查两点：(1) API Key 是否有效 (2) 是否携带了 X-Claw-* Headers。SkillHub 2.0 后必须带 X-Claw Headers，否则一律 401。

### Q: 同花顺一致预期 ths_eps_forecast 返回空
A: 该股票无机构覆盖。小盘/次新/ST 股常见。可 fallback 到东财 reportapi 里的 predictThisYearEps 字段。

### Q: 东财 PDF 下载 403
A: 必须带 `Referer: https://data.eastmoney.com/` header。

### Q: 腾讯 API 返回乱码
A: 编码是 GBK，必须 `decode("gbk")`。

### Q: 腾讯 API 字段 43 是 PB 吗？
A: **不是！** 43=振幅%，46=PB。网上很多教程写错了，这里是实测校准结果。

### Q: iwencai search 返回条数太少
A: `size` 参数默认 10，调到 50。隐藏参数，文档未写明但实测可用。

### Q: 哪些数据源需要 API Key？
A: 只有 iwencai 需要。mootdx / 腾讯 / 东财 / 同花顺 / 百度股市通 / 新浪 / 巨潮 / 财联社全部免费无 key。

### Q: 同花顺热点接口需要 cookie 吗？
A: **不需要**。仅 User-Agent 即可，零鉴权 73ms 拿到 ~125 只当日强势股。但**不要去打 search.10jqka.com.cn 的 iwencai NL 选股接口** —— 那个有 hexin-v cookie JS 签名鉴权，跟热点接口完全两码事。

### Q: 百度股市通 ResultCode 有时是 0 有时是 "0"？
A: 已知坑。`ResultCode` 返回类型不稳定——有时 int，有时 string。代码里必须用 `str(d.get("ResultCode", -1)) != "0"` 统一比较。

### Q: 北向资金历史数据为什么只有最近几天？
A: 本地自缓存模式。eastmoney 全系北向数据自 2024-08 起断供（净买额字段返回 NaN/0）。每次调用实时 API 后自动写入本地 CSV，历史越跑越丰富。

### Q: 行业板块为什么从同花顺换成东财？
A: 同花顺 `stock_board_industry_summary_ths` 接口 2026 年初加了反爬 401（需要登录态）。东财 push2 行业板块数据（`m:90+t:2`）是完美替代，零鉴权且字段更丰富。

### Q: 在海外服务器跑，mootdx 接口超时？
A: mootdx 走 TCP 直连通达信行情服务器，需国内 IP 才稳定。海外环境建议走代理。腾讯财经和百度股市通不受影响。

### Q: 不用 Claude Code，能用吗？
A: 能。SKILL.md 本质是 Markdown + 内嵌 Python 代码。Codex、OpenClaw 或任何 AI 编程助手都能读取。你也可以直接把 Python 代码段复制出来在自己的脚本里跑。

### Q: 港股代码怎么传？00700 还是 700？
A: 两种均可，内部统一 `zfill(5)` 为五位（如 `700` → `00700`）。腾讯财经传 `hk00700`，东财传 `116.00700`，Yahoo Finance 传 `700.HK`。

### Q: 东财港股价格为什么是奇怪的大整数（如 37550）？
A: 东财 push2 港股价格单位为**分（fen）**，37550 ÷ 100 = 375.50 港元。代码里已处理（`d.get("f43") / 100`）。腾讯财经 hk 接口返回的是直接港元，无需换算。

### Q: Yahoo Finance 接口返回空或 404？
A: 检查 ticker 格式：港股必须带 `.HK` 后缀（`0700.HK` 而非 `00700`），A股必须带 `.SS`/`.SZ`（`600519.SS`），美股直接用 ticker（`AAPL`）。^开头是指数（`^GSPC`）。

### Q: Yahoo Finance 港股延迟多少？
A: 港股实时数据延迟15分钟（交易所规定），美股盘中准实时（延迟约1分钟），盘后/前市数据包含在 `includePrePost=true` 模式中。

### Q: 美股东财 push2 返回空，105 和 106 都没有？
A: 部分小盘/场外股票东财不收录。改用 Yahoo Finance `yahoo_quote([ticker])` 或腾讯 `tencent_us_quote([ticker])`。

### Q: Yahoo Finance 财报返回 None 字段？
A: Yahoo Finance 部分港股财务数据不完整（尤其是小市值港股）。可 fallback 到东财港股财报接口或手动查 cninfo 港交所披露。

### Q: 三大指数 ^GSPC / ^DJI / ^IXIC 在什么时间有数据？
A: 美东时间 9:30–16:00 有盘中数据，其余时间返回上一个收盘价。中国时间：夏令时 21:30–4:00，冬令时 22:30–5:00。

---

## 安装说明

```bash
# 1. 创建 skill 目录
mkdir -p ~/.claude/skills/a-stock-data

# 2. 将本文件复制为 SKILL.md
cp SKILL.md ~/.claude/skills/a-stock-data/SKILL.md

# 3. 安装 Python 依赖
pip install mootdx requests pandas stockstats

# 4. (可选) 配置 iwencai API Key
export IWENCAI_API_KEY="your_key_here"

# 5. 启动 Claude Code，说"查一下688017的估值"即可自动激活
```

---

> 📦 https://github.com/simonlin1212/a-stock-data — Star ⭐ 是最好的支持
