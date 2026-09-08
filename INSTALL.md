# 一键安装

把这份文件读完并按顺序执行，一套完整的投研工作流就装好了。设计目标：**你的朋友把这个仓库的链接和下面这句话丢给自己的 agent，agent 自己读这份文件、自己跑完全部步骤，不需要人再来回答"这一步该怎么办"**。

> **给朋友的一句话邀请（可以直接复制发给对方）**：
> "克隆 `https://github.com/lmy8737-boop/Macliu`，然后读 `INSTALL.md` 并严格按步骤执行到底，每一步执行完汇报状态（成功/跳过/需要你提供的信息），全部装完后跑一遍 `验收清单.md` 里的测试。"

## 装完之后能得到什么

| 层级 | 内容 | 是否零配置可用 |
|---|---|---|
| 方法论 | 六步流程、G/Y/R、11角色委员会、证据分级、写库规范 | ✅ 纯文档，读了就能用，不需要装任何东西 |
| 结构化数据 | `stock-data`（A/H/美股行情财报） | ✅ 装完 Python 依赖即可，全部走免费数据源 |
| 联网采集路由 | `web-harvest` | ✅ 装完依赖即用内置联网工具；外部通道锦上添花 |
| 一手内容抓取 | `web-access`、`agent-reach`、`anysearch` | ⚠️ 需要执行下面第 3 步的安装命令（全自动，但需要联网下载） |
| 大规模批量采集 | `Scrapling` | ⚠️ 需要装一次浏览器内核（约 260MB，一次性） |
| 结构化网页提取 | `Firecrawl` | ❌ 需要你朋友自己的付费 API Key，没有就跳过，不影响其他功能 |
| 卖方研报/纪要 | （示例里叫 BRM，是我自己的付费订阅） | ❌ 本包不含，需要你朋友自己找等价数据源，没有就跳过，只是少一层 P2 线索 |

**核心方法论和结构化数据这两层，装完 Python 依赖就能全功能跑起来，完全免费。** 后面几层是"锦上添花"的采集能力，装不上也不影响核心方法论生效——只是会少几条搜索/抓取通道。

## 前置要求

- Python 3.10+，能执行 `pip install`
- 如果需要 `web-access`（真实浏览器操作）：Node.js 22+
- 网络能访问 GitHub、PyPI（装 Python 包和克隆下面几个第三方仓库都需要）

## 第 1 步：装核心六个 skill 的 Python 依赖

```bash
# 六个自研 skill 里，有 requirements.txt 的都装一遍
pip install -r skills/investment-team-skill/requirements.txt
```

`stock-data`、`web-harvest`、`zhiku-research`、`research-data-verify` 目前依赖的都是标准库或 `investment-team-skill` 里已经覆盖的包（`requests`/`pandas` 等），如果单独运行某个脚本时报 `ModuleNotFoundError`，按报错信息 `pip install` 对应的包即可。

`quant-check` 需要独立的统计计算环境（避免和其他包的版本冲突）：

```bash
python3 -m venv .venv-quant-check
source .venv-quant-check/bin/activate   # Windows: .venv-quant-check\Scripts\activate
pip install alphalens-reloaded==0.4.6 "vectorbt==1.0.0" "plotly==5.24.1"
deactivate
```

这一步做完，**核心方法论 + 结构化行情数据 + 联网基础采集 + 打分回测**，四层全部可用。如果你朋友只是想用这套研究方法论，不需要交易信号计算和大规模网页采集，**到这里就可以停了，直接开始用**。

## 第 2 步（可选）：交易信号计算环境（缠论/DK 信号）

只有涉及真实交易决策、需要用到技术面信号时才需要这一步；纯粹的公司/行业基本面研究用不到。

```bash
cd skills/investment-team-skill
bash scripts/setup/auto_setup_czsc.sh
cd ../..
```

这个脚本会自动创建一个独立的 `.venv-czsc` 虚拟环境并安装 `czsc` 等技术分析库。如果安装失败（比如 `czsc` 包在某些 Python 版本上编译报错），不影响其他任何功能——`investment-team-skill` 会自动降级到不含缠论信号的模式，交易员角色仍然可以正常工作，只是少了技术面细节。

## 第 3 步（可选但推荐）：一手内容抓取三件套

这三个不是我自己写的，是三个独立的开源项目，`web-harvest` 的路由逻辑会调用它们。全部零成本、有免费额度，装好之后不需要额外配置就能用。

### 3.1 web-access（真实浏览器操作，MIT 协议）

```bash
git clone https://github.com/eze-is/web-access.git skills/web-access
```

装完之后跑一次前置检查：

```bash
node skills/web-access/scripts/check-deps.mjs
```

### 3.2 AnySearch（实时搜索，Apache 2.0 协议，匿名免费额度）

用 `git clone` 而不是下载 zip——这样以后能直接 `git pull` 拿到官方更新，AnySearch 项目自己发新版本时也是这样引导用户升级的：

```bash
git clone https://github.com/anysearch-ai/anysearch-skill.git skills/anysearch
pip install -r skills/anysearch/requirements.txt
```

默认匿名模式有每日免费搜索额度，不需要注册就能用；如果用量大想要更稳定，按 `skills/anysearch/SKILL.md` 里的说明申请免费 Key。

### 3.3 Agent Reach（多平台内容抓取 CLI：YouTube/B站/GitHub/RSS 等）

`skills/agent-reach/` 已经包含路由文档（怎么用它、覆盖哪些平台），但底层 CLI 工具本身是独立安装的第三方程序，装法请直接看它的项目主页（里面的安装命令可能会更新，不在这里写死）：

👉 https://github.com/Panniantong/Agent-Reach

装完 CLI 后跑一次健康检查确认可用：

```bash
agent-reach doctor --json
```

## 第 4 步（可选）：大规模批量采集 / 结构化字段提取

只有需要"批量抓取几十上百个页面"或者"给页面定义字段直接拿结构化 JSON"这类重度采集需求时才需要。日常研究用第 1-3 步就够了。

```bash
python3 -m pip install --user "scrapling[all]"
scrapling install    # 会下载浏览器内核，约 260MB，一次性
```

**Firecrawl**（结构化提取 + 全站 URL 发现）需要你朋友自己的 API Key（https://www.firecrawl.dev 注册获取，有免费额度）：

```bash
export FIRECRAWL_API_KEY="<你朋友自己的key>"
```

没有这个 Key 就跳过，`web-harvest` 会自动降级到用 AnySearch/Scrapling 完成同类任务，只是效果会差一点。

## 第 5 步：验收

全部装完后，跑一遍下面这些检查，确认真的装好了而不是"文件存在但链路不通"（这是从真实踩坑里总结的教训——很多健康检查脚本只确认"包已安装"，不代表真的能跑通一次请求）：

```bash
# web-harvest 自检（--live 会真的发一次网络请求，比只看安装状态更可信）
python3 skills/web-harvest/scripts/doctor.py --live

# stock-data 基本可用性（随便查一只股票的行情）
python3 skills/stock-data/scripts/stock_data_cli.py quote --code AAPL

# investment-team-skill 缠论环境（如果做了第2步）
skills/investment-team-skill/.venv-czsc/bin/python skills/investment-team-skill/scripts/cli/czsc_check.py SH600063 -m
```

再按《验收清单.md》跑一遍方法论理解度测试，确认 agent 不仅"装好了工具"，也真的理解这套研究方法论怎么用。

## 以后怎么升级

`skills/investment-team-skill`、`skills/zhiku-research`、`skills/research-data-verify`、`skills/quant-check`、`skills/stock-data`、`skills/web-harvest`、`skills/agent-reach` 这七个是本仓库自己维护的，跟着这个仓库 `git pull` 就会更新，不需要单独处理。

`skills/web-access` 和 `skills/anysearch` 是按第 3 步用 `git clone` 装的两个独立第三方开源项目，**它们的更新不会跟着这个仓库自动同步**，需要单独检查。最省事的方式是跑仓库自带的检查脚本：

```bash
./scripts/upgrade-vendored-skills.sh              # 交互式：发现更新会问你要不要升级
./scripts/upgrade-vendored-skills.sh --check-only  # 只报告落后情况，不动手
./scripts/upgrade-vendored-skills.sh --yes         # 有更新直接升级，不用交互确认（适合agent自动执行）
```

这个脚本会：检查是否落后上游、列出落后的提交、本地有未提交改动时先自动 `git stash`（不会丢）、拉取更新、重装依赖、**实际跑一次搜索/健康检查确认真的能用**（不是只看"文件装上了"）。默认检查 `./skills/` 下的副本；如果你把这两个工具装在别的位置（比如全局共享目录），用 `SKILLS_DIR=<路径> ./scripts/upgrade-vendored-skills.sh` 指定。

也可以手动做同样的事：

```bash
git -C skills/web-access pull
git -C skills/anysearch pull && pip install -r skills/anysearch/requirements.txt
```

`AnySearch` 项目更新比较活跃，建议每隔一段时间检查一次；它的发布记录里出现过安全相关的修复（比如 API key 在 HTTP 重定向时可能泄漏的问题），是这三个外部依赖里最值得保持更新的一个。

`agent-reach` 底层 CLI 是独立安装的全局工具，不在这个仓库管理范围内，升级方式看它自己的项目主页：https://github.com/Panniantong/Agent-Reach

## 装不上某一步怎么办

**不要卡在某一个可选组件上反复重试。** 按这个优先级判断：

1. 第 1 步（核心方法论 + 行情数据）失败 → 必须解决，否则整套系统跑不起来，检查 Python 版本和网络。
2. 第 2-4 步任何一步失败 → 记录下来告诉用户"这个可选能力没装上，原因是 X"，然后继续用其他能力工作，不要因为一个可选组件卡住整个安装流程。
3. Firecrawl / BRM 等价物没有账号 → 这是预期状态，不是错误，直接跳过，在后续研究中如实说明"这层证据数据源缺失"即可。
