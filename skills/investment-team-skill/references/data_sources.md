# 数据源与抗反爬协议 (Data Sources & Anti-Block Protocol)

> **背景**：2026-06-01 实战暴露 eastmoney `push2his` 子域对 akshare 客户端做**动态指纹拦截**——同一时刻、同一接口，每分钟成功率不一样。akshare 单源依赖在反爬升级面前不可靠。本文档定义 v6.0.x 的多源 fallback 策略。

---

## 一、为什么需要多源

### 实战触发事件

- **2026-05-31 23:48**：collector 冒烟测试 6/6 全过（akshare 完全可用）
- **2026-06-01 00:09**：cycle #3 因 akshare RemoteDisconnected 全失败 ABORT
- **2026-06-01 10:30**：cycle #4 在新办公地点（不同 IP）仍超时 180s
- **2026-06-01 11:xx**：诊断发现 push2his 是 **动态概率性 reset**（curl/akshare/baostock 都中招），**与 IP 无关**
- **同时验证**：雪球公开 K 线 API、新浪、腾讯实时行情**全部 200 OK**

### 结论

| 数据源风险 | 说明 |
|---|---|
| **eastmoney push2his** | 动态指纹拦截，时通时不通；不可作为单源依赖 |
| **akshare 客户端** | 默认 UA `python-requests/*` 被识别；底层多接口走 push2his |
| **baostock** | 服务器协议层不稳定（实测 login 时常卡住） |
| **雪球公开 API** | 0 反爬（本身给雪球网页用），但需先拿 cookie |
| **新浪 / 腾讯** | 极稳定，但只有实时行情，无完整历史 K 线 |

---

## 二、源优先级矩阵

| 数据类型 | 主源 | Fallback 1 | Fallback 2 | 备注 |
|---|---|---|---|---|
| **历史 K 线（个股 + ETF）** | akshare | **雪球 K 线 API** | 新浪 K 线 | 雪球已实装（`_hist_kline_with_fallback`） |
| **实时报价** | akshare（`stock_zh_a_spot_em` / `fund_etf_spot_em`） | 雪球（`stock.xueqiu.com/v5/stock/realtime/quotec.json`） | 新浪 `hq.sinajs.cn` | scanner 步骤待加 |
| **财务报表** | 同花顺 F10（WebFetch） | akshare | 雪球 | 当前由 finance_collector 处理 |
| **ETF 筹码（份额）** | akshare `fund_etf_fund_info_em` | — | — | 雪球暂无对应接口 |
| **宏观指标** | akshare（`bond_zh_us_rate` / `stock_hsgt_*`） | WebFetch（财联社/金十） | — | 失败可降级，不阻塞 cycle |

---

## 三、主源 vs Fallback 字段映射

### 雪球 K 线 → akshare 中文列名

雪球 `stock.xueqiu.com/v5/stock/chart/kline.json` 返回：
```json
{
  "data": {
    "column": ["timestamp", "volume", "open", "high", "low", "close", "chg", "percent", ...],
    "item":   [[ts_ms, vol, open, high, low, close, chg, percent, ...], ...]
  }
}
```

映射规则（`_xueqiu_kline_to_akshare_df`）：

| 雪球字段 | akshare 中文列名 | 转换 |
|---|---|---|
| `timestamp` (ms) | `日期` | `datetime.utcfromtimestamp(ts/1000).strftime('%Y-%m-%d')` |
| `open` | `开盘` | 直传 |
| `close` | `收盘` | 直传 |
| `high` | `最高` | 直传 |
| `low` | `最低` | 直传 |
| `volume` | `成交量` | 直传（注意单位：股 vs 手——雪球是"股"） |
| `amount`（如有） | `成交额` | 直传，否则 `vol * close` 估算 |
| `chg` | `涨跌额` | 直传 |
| `percent` | `涨跌幅` | 直传（已是百分数） |
| `turnoverrate`（如有） | `换手率` | 直传，否则 0 |
| 派生 | `振幅` | `(high - low) / (close - chg) * 100` |

---

## 四、ticker → 数据源代码格式映射

| 数据源 | 沪市个股（6XXX）| 深市个股（0XX/3XX）| 沪市 ETF（5XX）| 深市 ETF（1XX）|
|---|---|---|---|---|
| **akshare** | `'603296'` | `'300750'` | `'510300'` | `'159915'` |
| **雪球** | `'SH603296'` | `'SZ300750'` | `'SH510300'` | `'SZ159915'` |
| **新浪** | `'sh603296'` | `'sz300750'` | `'sh510300'` | `'sz159915'` |
| **腾讯** | `'sh603296'` | `'sz300750'` | `'sh510300'` | `'sz159915'` |

工具函数：`_xueqiu_symbol(code)` 在 `real_data_collector.py`。

---

## 五、Fallback 触发与日志规范

### 触发条件（`_hist_kline_with_fallback`）

```
1. 主源 akshare 调用 + _call_with_retry（最多 2 次）
2. 任一异常（ConnectionError / RemoteDisconnected / Timeout / RuntimeError）
   → 进入 fallback 分支
3. 雪球 _xueqiu_hist(count=500) 拉 500 个交易日（约 2 年）
4. 雪球失败 → 抛 RuntimeError("akshare+xueqiu 双源失败")
   → 上层 collect_structures 跳过该 ticker，继续下一个
```

### 日志规范

| 场景 | stderr 输出 |
|---|---|
| akshare 成功 | （无 fallback 标记） |
| akshare 失败、雪球救回 | `  [fallback xueqiu] {code}: rows={n}` |
| 双源都失败 | `  ⚠️  {code} structures 失败：akshare+xueqiu 双源失败 — ...` |

### 5 号 audit 关注点

5 号在 audit 5 检查 `structures_<date>.json` 时，应：
1. 统计 ticker 总数 vs 成功数（如 11/11 / 9/11）
2. 检查 generated_by 字段，标记本次是否触发了 fallback
3. 若 fallback 触发率 >50%，**写入 audit_log 备忘**：`数据源主源不稳定，建议复盘 push2his 状态`

---

## 六、雪球 cookie 管理

雪球公开 API 需要 cookie（`xq_a_token` / `cookiesu` / `aliyungf_tc`），但**不需要登录**——任何匿名访客打 `https://xueqiu.com` 主页即可拿到。

**实现**（`_xueqiu_session` 模块级缓存）：
- 单进程内复用 cookie，避免每次新建 session
- cookie 过期（403 时）的自动重建：**待实现**（v6.0.3 计划）
- 当前已知 cookie 寿命：~24 小时

---

## 七、限制与已知问题

| 限制 | 影响 | 应对 |
|---|---|---|
| 雪球 K 线最多倒推 5000 个交易日（约 20 年） | 长期回测足够 | 默认 count=500 |
| 雪球字段比 akshare 少（无逐日资金流向） | 缠论计算不影响，alpha 资金流引擎可能降级 | 4 号 alpha B 引擎 fallback 走北向资金 |
| 雪球速率限制 ~10 QPS | 11 个 ticker 顺序拉无问题 | 不并发；`time.sleep(0.3)` 节流 |
| 新浪/腾讯只能拉实时（10-20 个最近 tick） | 不能用于历史回测 | 仅用于 scanner 实时报价 fallback |
| `baostock` 在某些网络环境握手卡死 | 暂不纳入 fallback | 待客户端协议层修复 |

---

## 八、版本与升级路线

> **v6.1 包含 v6.0.0 → v6.0.3 全部迭代**（一日内的快速演进）。下面列出每一步的来源：

- **v6.0.0（2026-05-31）**：单源 akshare，无 fallback——push2his 反爬升级即崩
- **v6.0.1（2026-06-01）**：UA 反爬补丁 + akshare 重试补丁——治标不治本
- **v6.0.2（2026-06-01）**：✅ 雪球 K 线 API fallback 实装（仅 collect_structures）
- **v6.0.3（2026-06-01）**：✅ **按 query intent 分模式采集**——见章节十一
- **v6.1（2026-06-01）✅ 当前 skill 版本**：合并 v6.0.0 → v6.0.3 全部改动；选美评分协议升级 v1.0 → v1.1（行业 z-score）
- **v6.1.1（计划）**：scanner 步骤接雪球 quote 实时报价 fallback；ETF 筹码无 fallback 仍是单点
- **v6.1.2（计划）**：cookie 自动续期 + fallback 触发率写入 audit_log
- **v6.2.0（计划）**：collector 抽象 `DataSourceProvider` 接口，akshare/xueqiu/sina/baostock 同 schema 注册
- **v6.3.0（计划）**：可选启用 baostock + Wind/同花顺 收费源（如有授权）

---

## 十一、按 Query Intent 分模式采集（v6.1）

### 11.1 触发动机

v6.0.0/v6.0.2 的 `collect_all` 是**全量采集**——不管用户问"开盘前讨论"还是"分析单只华勤"，
都跑 6 步骤（structures + scanner + chip + holdings + macro + finance），耗时约 8 分钟。

实证数据（2026-06-01 实测）：

| 步骤 | 耗时 | 个股查询时的必要性 | 浪费率 |
|---|---|---|---|
| chip | ~4-5 min | 个股查询完全用不到 | **100%** |
| scanner | ~30-60s | 只需目标股 | 90% |
| structures | ~75s | 只需目标股 + 同行 | 45% |

→ 个股查询 80% 时间在白干。

### 11.2 模式定义

| Mode | 用户场景 | 跑哪些步骤 | 实测耗时 |
|------|---------|----------|--------|
| `portfolio` (默认) | 开盘前 / 全盘讨论 / 持仓审视 | 全 6 步 | 8 min |
| `stock` | 分析单只个股 | structures + holdings + macro + finance | **22s** |
| `etf` | ETF 焦点讨论 | structures + scanner + chip + holdings + macro | ~60s |
| `macro` | 美股 / 宏观 / 美债 | holdings + macro | **6s** |

### 11.3 query_intent 识别规则

`bot_runtime/query_intent.py:classify(text)` 优先级：

1. **PORTFOLIO 关键词**（"全盘/持仓/开盘前/今日策略/复盘" 等）→ `portfolio`
2. **ticker 代码或名字命中**（华勤/603296/0285.HK 等）→ `stock` 或 `etf`（看 5XX/15X 前缀）
3. **ETF 关键词**（"ETF/指数/红利"）→ `etf`
4. **MACRO 关键词**（"美股/宏观/美债/降息"）→ `macro`
5. **兜底** → `portfolio`（保守，宁慢勿漏）

### 11.4 同行业 peers 自动取

`references/industry_peers.yaml`：每行业 5-6 家头部公司池。
`stock` 模式下 query_intent 自动取 5 家同行加入 ticker 池，给 finance_collector
跑颜值评分（z-score 行业修正）和 czsc 缠论引擎对照用。

### 11.5 协议级保障

- **5 号 audit 职责 E**：必须主动声明 cycle mode + 跳过项（`roles/05_supervisor.md`）
- **phase_orchestrator 硬门槛**：required JSON 列表按 mode 动态调整
  （`stock` 模式不强制 scanner/chip 文件）
- **CLI 参数**：`real_data_collector.py --mode stock --target 603296 --peers 600745,...`
- **回退**：query_intent classify 失败 → 自动 fallback `portfolio` 模式（保守）

### 11.6 测试矩阵

| 用例 | 期望模式 | 耗时 | 必出文件 |
|------|--------|------|--------|
| `@foreman 华勤分析` | stock | <30s | structures + finance + macro + holdings |
| `@foreman 510300 怎么样` | etf | <90s | + scanner + chip |
| `@foreman 美股今晚机会` | macro | <15s | macro + holdings |
| `@foreman 开盘前讨论今日策略` | portfolio | <10min | 全 6 个 |

### 11.7 已知限制

- 名字识别有限（`NAME_TO_TICKER` 字典约 50 个常见股）→ 未命中时回退 `portfolio`
- 用户问多个个股（"华勤和闻泰对比"）→ 当前只识别第一个，其他归 peers
- 港股代码识别（`0285.HK`）已支持，但 akshare 不一定能拉（雪球 fallback 部分支持）

---

## 九、测试矩阵（每次新增/修改 fallback 必跑）

| 用例 | 期望 |
|---|---|
| akshare 全可用 | 11/11 通过，**0 条** `[fallback xueqiu]` 日志 |
| akshare 全失败 | 11/11 通过，**11 条** `[fallback xueqiu]` 日志 |
| akshare 部分失败（如 5 个 ETF 通、6 个个股断） | 11/11 通过，**6 条** fallback 日志 |
| 雪球也失败（断网/cookie 失效） | 双源失败 RuntimeError，上层跳过该 ticker |
| 雪球 cookie 过期（403） | 待 v6.0.3 自动续期；当前需重启 collector 进程 |

---

## 十、与 v6.0 协议的兼容性

- **不违反"禁 fixture"**：雪球数据是真实历史 K 线，不是 mock
- **5 号 audit 第 1 项（引用闭环）**：fallback 触发的 ticker 在 `generated_by` 字段标 `[via xueqiu fallback]`（待 v6.0.3 实装；当前仅 stderr 日志）
- **5 号 audit 第 2 项（数据真实性）**：fallback 字段映射不引入精度损失（雪球字段已是浮点数，不需要 round）
- **3 号缠论引擎**：`bars_count=500` 足够计算 czsc 日线缠论（czsc 推荐 ≥250 根）

---

**文档维护**：每次新增/修复 fallback 路径必须同步更新章节二、三、八。
