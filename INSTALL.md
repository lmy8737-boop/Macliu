# 一键安装

把这份文件读完并按顺序执行，一套完整的投研工作流就装好了。设计目标：**一个刚装好 AI agent（不管是 Claude Code、Codex 还是任何国产 agent 应用）的完全新手，把下面这句话丢给自己的 agent，跑完之后不用再做任何配置，直接打开 Obsidian 就能开始研究**。整个过程里唯一可能需要用户自己动手的，是"Obsidian/Git 应用本体自动安装失败时手动点一次安装包"——除此之外不需要用户回答任何"装在哪""要不要装这个"之类的问题，agent 自己按约定决定。

> **给新手的一句话邀请（可以直接复制发给对方，让对方粘贴给自己的 agent）**：
> "打开 `https://raw.githubusercontent.com/lmy8737-boop/Macliu/main/INSTALL.md` 读取安装说明，然后严格按里面的步骤自动执行到底——包括它规定好的默认安装路径，不要停下来问我装在哪或者要不要装某个东西。每完成一个主要步骤用大白话跟我汇报一下进度。全部装完后跑一遍 `验收清单.md` 里的测试，告诉我可以开始用了。"

## 装完之后能得到什么

| 层级 | 内容 | 是否零配置可用 |
|---|---|---|
| 知识库 | Obsidian + 本仓库作为 vault，`00_首页/`、`03_公司研究/` 等目录已就位 | ✅ 第 1 步一条龙装好；Obsidian 应用本身如果自动安装失败，需要手动点一次安装包 |
| 方法论 | 六步流程、G/Y/R、11角色委员会、证据分级、写库规范 | ✅ 纯文档，读了就能用，不需要装任何东西 |
| 结构化数据 | `stock-data`（A/H/美股行情财报） | ✅ 装完 Python 依赖即可，全部走免费数据源 |
| 联网采集路由 | `web-harvest` | ✅ 装完依赖即用内置联网工具；外部通道锦上添花 |
| 一手内容抓取 | `web-access`、`agent-reach`、`anysearch` | ⚠️ 需要执行下面第 4 步的安装命令（全自动，但需要联网下载） |
| 大规模批量采集 | `Scrapling` | ⚠️ 需要装一次浏览器内核（约 260MB，一次性） |
| 结构化网页提取 | `Firecrawl` | ❌ 需要你朋友自己的付费 API Key，没有就跳过，不影响其他功能 |
| 卖方研报/纪要 | （示例里叫 BRM，是我自己的付费订阅） | ❌ 本包不含，需要你朋友自己找等价数据源，没有就跳过，只是少一层 P2 线索 |

**核心方法论和结构化数据这两层，装完 Python 依赖就能全功能跑起来，完全免费。** 后面几层是"锦上添花"的采集能力，装不上也不影响核心方法论生效——只是会少几条搜索/抓取通道。

## 前置要求

- Python 3.10+，能执行 `pip install`
- 如果需要 `web-access`（真实浏览器操作）：Node.js 22+
- 网络能访问 GitHub、PyPI（装 Python 包和克隆下面几个第三方仓库都需要）

## 第 0 步：拿到仓库，放到约定的位置

这是让整个流程对用户"零决策"的关键一步——**固定用下面这个路径，不要反问用户想装在哪**：

| 系统 | 目标路径 |
|---|---|
| macOS | `~/Documents/投研工作目录`（Finder 里这个目录显示成"文稿"，但磁盘上的真实目录名永远是 `Documents`——不要去找一个真的叫"文稿"的文件夹，也不要因为找不到而卡住） |
| Windows | `%USERPROFILE%\Documents\投研工作目录`（资源管理器里显示成"文档"） |
| Linux | `~/Documents/投研工作目录`；如果这台机器没有 `~/Documents` 目录，就直接用 `~/投研工作目录` |

### 0.1 确认 git 已安装

```bash
git --version
```

没装的话按系统尝试自动装：

```bash
# macOS：会弹出系统自带的 Xcode Command Line Tools 安装对话框
xcode-select --install

# Windows（PowerShell，winget 自带于 Windows 10/11）
winget install --id Git.Git -e

# Linux
sudo apt install -y git   # Debian/Ubuntu 系；其他发行版换成对应包管理器
```

和 Obsidian 那步一样，**这里可能需要用户点一下确认弹窗**——这是正常的，不是失败，跟用户说清楚"系统弹了个安装窗口，点一下确认"，等它装完再继续。如果自动安装完全跑不通，才退化成"打开 https://git-scm.com/downloads 手动装"。

### 0.2 克隆或更新到约定路径

```bash
# macOS/Linux（Windows 用等效的 PowerShell 逻辑，$TARGET 换成上表里 Windows 的路径）
TARGET="$HOME/Documents/投研工作目录"

if [ -d "$TARGET/.git" ]; then
  echo "已经装过，当成一次升级来处理"
  git -C "$TARGET" pull
elif [ -e "$TARGET" ]; then
  echo "目标路径已存在但不是这个仓库，不要覆盖——先看看里面是什么，跟用户确认怎么处理："
  ls -la "$TARGET"
else
  git clone https://github.com/lmy8737-boop/Macliu.git "$TARGET"
fi

cd "$TARGET"
```

这一步做完，下面第 1-6 步全部在 `$TARGET`（也就是 `~/Documents/投研工作目录`）这个目录里执行——后面步骤里出现的所有相对路径（`skills/...`、`scripts/...`）都是相对这里而言。

### 0.3 沿途给用户看得懂的进度

接下来的安装有好几个步骤、有的要下载东西（Obsidian、浏览器内核），**不要闷头跑完再一次性汇报**。每完成一个主要步骤就用大白话说一句人话（"Git 装好了，正在装 Obsidian，这个可能要一两分钟""知识库已经能打开了，现在装数据源……"），不要让用户对着一个不知道有没有卡住的窗口干等。全部做完后给一个清楚的总结：装好了什么、跳过了什么原因是什么、要不要用户现在做点什么。

## 第 1 步：部署 Obsidian 知识库

**目标：这个仓库克隆下来的文件夹，本身就是一个可以直接用的 Obsidian 知识库。** 这一步做完，用户打开 Obsidian 就能看到 `00_首页/`、`03_公司研究/` 等目录，可以直接开始研究，不需要自己再建一个 vault、抄一遍规则。

### 1.1 装 Obsidian 应用本身

**先检查是否已经装过**：macOS 看 `/Applications/Obsidian.app` 是否存在；Windows 看开始菜单或 `winget list --id Obsidian.Obsidian`；已装过跳到 1.2。

没装过时，按当前系统尝试自动安装：

```bash
# macOS（需要先装 Homebrew：https://brew.sh）
brew install --cask obsidian

# Windows（PowerShell，Windows 10/11 自带 winget）
winget install -e --id Obsidian.Obsidian

# Linux（任选其一，取决于发行版用哪个包管理）
flatpak install -y flathub md.obsidian.Obsidian
# 或
sudo snap install obsidian --classic
```

**如果上面的命令都跑不通**（没装 Homebrew/winget 不可用/是不支持 flatpak 和 snap 的发行版）：不要卡在这一步反复试。直接告诉用户——"请打开 https://obsidian.md/download 下载安装包并安装，装完后告诉我继续"，然后停下来等用户确认装完，再继续 1.2。这是唯一允许要求用户手动操作的一步。

### 1.2 把这个仓库当 vault 打开

Obsidian 装好后，用 URI 直接打开 `$TARGET`（也就是上面确定的 `~/Documents/投研工作目录`）这个文件夹作为 vault。路径里有中文，用 `python3` 做一次标准 URL 编码，不要手动拼：

```bash
# macOS/Linux
ENCODED=$(python3 -c "import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))" "$TARGET")
open "obsidian://open?path=$ENCODED"          # Linux 换成 xdg-open

# Windows（PowerShell，$TARGET 是第 0.2 步里 Windows 的路径）
$Encoded = [uri]::EscapeDataString($TARGET)
Start-Process "obsidian://open?path=$Encoded"
```

**如果 URI 没有自动弹出 Obsidian 或没有正确识别路径**（比如 Obsidian 是第一次启动、还没完成初始设置）：告诉用户手动做——"打开 Obsidian → 左下角『Open folder as vault』→ 选择 `文稿/投研工作目录`（Windows 上是『文档』里的『投研工作目录』）"，两次点击，不复杂。

### 1.3 确认知识库能用

打开后应该能在 Obsidian 左侧文件树看到 `00_首页`、`00_Inbox`、`01_每日投研`、`02_资料收集`、`03_公司研究`、`04_行业研究`、`05_投资主题`、`07_输出与报告`、`09_附件` 这些目录，以及 `SKILL.md`。打开 `00_首页/新手上路.md` 确认能正常渲染。

这一步做完，后面的第 2-6 步是给"帮这套系统干活的 agent"装能力（数据源、联网采集），不影响用户已经可以在 Obsidian 里跟 agent 对话开始研究——两件事可以并行，不需要严格先后顺序，但建议先做完第 1 步让用户能立刻上手，再慢慢装后面的可选能力。

## 第 2 步：装核心六个 skill 的 Python 依赖

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

## 第 3 步（可选）：交易信号计算环境（缠论/DK 信号）

只有涉及真实交易决策、需要用到技术面信号时才需要这一步；纯粹的公司/行业基本面研究用不到。

```bash
cd skills/investment-team-skill
bash scripts/setup/auto_setup_czsc.sh
cd ../..
```

这个脚本会自动创建一个独立的 `.venv-czsc` 虚拟环境并安装 `czsc` 等技术分析库。如果安装失败（比如 `czsc` 包在某些 Python 版本上编译报错），不影响其他任何功能——`investment-team-skill` 会自动降级到不含缠论信号的模式，交易员角色仍然可以正常工作，只是少了技术面细节。

## 第 4 步（可选但推荐）：一手内容抓取三件套

这三个不是我自己写的，是三个独立的开源项目，`web-harvest` 的路由逻辑会调用它们。全部零成本、有免费额度，装好之后不需要额外配置就能用。

### 4.1 web-access（真实浏览器操作，MIT 协议）

```bash
git clone https://github.com/eze-is/web-access.git skills/web-access
```

装完之后跑一次前置检查：

```bash
node skills/web-access/scripts/check-deps.mjs
```

### 4.2 AnySearch（实时搜索，Apache 2.0 协议，匿名免费额度）

用 `git clone` 而不是下载 zip——这样以后能直接 `git pull` 拿到官方更新，AnySearch 项目自己发新版本时也是这样引导用户升级的：

```bash
git clone https://github.com/anysearch-ai/anysearch-skill.git skills/anysearch
pip install -r skills/anysearch/requirements.txt
```

默认匿名模式有每日免费搜索额度，不需要注册就能用；如果用量大想要更稳定，按 `skills/anysearch/SKILL.md` 里的说明申请免费 Key。

### 4.3 Agent Reach（多平台内容抓取 CLI：YouTube/B站/GitHub/RSS 等）

`skills/agent-reach/` 已经包含路由文档（怎么用它、覆盖哪些平台），但底层 CLI 工具本身是独立安装的第三方程序，装法请直接看它的项目主页（里面的安装命令可能会更新，不在这里写死）：

👉 https://github.com/Panniantong/Agent-Reach

装完 CLI 后跑一次健康检查确认可用：

```bash
agent-reach doctor --json
```

## 第 5 步（可选）：大规模批量采集 / 结构化字段提取

只有需要"批量抓取几十上百个页面"或者"给页面定义字段直接拿结构化 JSON"这类重度采集需求时才需要。日常研究用第 2-4 步就够了。

```bash
python3 -m pip install --user "scrapling[all]"
scrapling install    # 会下载浏览器内核，约 260MB，一次性
```

**Firecrawl**（结构化提取 + 全站 URL 发现）需要你朋友自己的 API Key（https://www.firecrawl.dev 注册获取，有免费额度）：

```bash
export FIRECRAWL_API_KEY="<你朋友自己的key>"
```

没有这个 Key 就跳过，`web-harvest` 会自动降级到用 AnySearch/Scrapling 完成同类任务，只是效果会差一点。

## 第 6 步：验收

全部装完后，跑一遍下面这些检查，确认真的装好了而不是"文件存在但链路不通"（这是从真实踩坑里总结的教训——很多健康检查脚本只确认"包已安装"，不代表真的能跑通一次请求）：

```bash
# web-harvest 自检（--live 会真的发一次网络请求，比只看安装状态更可信）
python3 skills/web-harvest/scripts/doctor.py --live

# stock-data 基本可用性（随便查一只股票的行情）
python3 skills/stock-data/scripts/stock_data_cli.py quote --code AAPL

# investment-team-skill 缠论环境（如果做了第3步）
skills/investment-team-skill/.venv-czsc/bin/python skills/investment-team-skill/scripts/cli/czsc_check.py SH600063 -m
```

再按《验收清单.md》跑一遍方法论理解度测试，确认 agent 不仅"装好了工具"，也真的理解这套研究方法论怎么用。

装完之后，给用户的最终汇报至少要包含：装在了哪个路径、Obsidian 有没有自动打开、跳过了哪些可选能力及原因、现在可以直接跟 agent 说什么开始第一次研究（可以引用 `00_首页/新手上路.md` 里的例子）。

## 以后怎么升级

`skills/investment-team-skill`、`skills/zhiku-research`、`skills/research-data-verify`、`skills/quant-check`、`skills/stock-data`、`skills/web-harvest`、`skills/agent-reach` 这七个是本仓库自己维护的，跟着这个仓库 `git pull` 就会更新，不需要单独处理。

`skills/web-access` 和 `skills/anysearch` 是按第 4 步用 `git clone` 装的两个独立第三方开源项目，**它们的更新不会跟着这个仓库自动同步**，需要单独检查。最省事的方式是跑仓库自带的检查脚本：

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

1. 第 0-1 步（Git 或 Obsidian 应用本体）自动安装失败 → 这是唯一预期需要用户手动点一下/装一下的环节，不是错误，说清楚让用户去官网下载装，装完继续，不要反复重试自动安装命令。
2. 第 2 步（核心方法论 + 行情数据）失败 → 必须解决，否则整套系统跑不起来，检查 Python 版本和网络。
3. 第 3-5 步任何一步失败 → 记录下来告诉用户"这个可选能力没装上，原因是 X"，然后继续用其他能力工作，不要因为一个可选组件卡住整个安装流程。
4. Firecrawl / BRM 等价物没有账号 → 这是预期状态，不是错误，直接跳过，在后续研究中如实说明"这层证据数据源缺失"即可。
