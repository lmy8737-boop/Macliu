# czsc 真值引擎自启动协议（v6.5.0 新增）

## 触发条件

3 号数据收集员在执行 `prepare_data.py` 或 `czsc_check.py` 时，若：
- `.venv-czsc` 目录不存在，或
- `.venv-czsc/bin/python -c "import czsc"` 失败

→ **自动调用** `scripts/setup/auto_setup_czsc.sh` 三级 fallback 安装。

---

## v6.4.7 与 v6.5.0 的区别

| 维度 | v6.4.7 行为 | **v6.5.0 行为** |
|------|------------|----------------|
| 检测到 venv 缺失 | 直接 return None → 报告标注 fallback B 级 | **自动跑 setup 脚本 → 三级 fallback 安装** |
| 安装失败 | （从未触发，因为不会主动安装）| 打印根因 + 操作建议 + 继续以 B 级 fallback 写报告 |
| 老板介入成本 | 高（要看文档、跑命令、调试 6 层故障）| **低**（首次运行自动 5-8 分钟装好，后续幂等跳过）|
| 报告里 czsc 章节质量 | 大概率 fallback（江恩位）| **大概率真值**（笔/中枢/背驰/三买卖）|

---

## 三级 fallback 顺序

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 1：uv venv --python 3.11 + uv pip install czsc           │
│   首选 — 5 分钟内完成，绕过系统 Python 3.9 + pip 21.x 的 6 层故障 │
│   要求：网络可访问 astral.sh + pypi.org                       │
└─────────────────────────────────────────────────────────────┘
                    ↓ 失败
┌─────────────────────────────────────────────────────────────┐
│ Tier 2：python3.11 -m venv .venv-czsc + pip install czsc       │
│   备选 — 需用户已装 python3.11                                │
└─────────────────────────────────────────────────────────────┘
                    ↓ 失败
┌─────────────────────────────────────────────────────────────┐
│ Tier 3：python3 -m pip install --user czsc                    │
│   兜底 — 装到系统 Python，不创建 venv；                       │
│   只能保 import czsc 可用，不能解决 6 层故障；               │
│   创建 .czsc-system-pip 标记文件让 caller 知道                │
└─────────────────────────────────────────────────────────────┘
                    ↓ 失败
┌─────────────────────────────────────────────────────────────┐
│ Final fallback：江恩位 + 0.382 回撤 + 3 根分型法              │
│   报告标注「czsc venv 自动安装失败，已诚实降级」             │
│   3 号在 03_data_collection.md 必须写「自启动失败诊断段」    │
└─────────────────────────────────────────────────────────────┘
```

---

## 用户体验

### 第一次跑（无 venv）

```bash
$ python3 scripts/cli/czsc_check.py SH600063 -m
🔧 [czsc_check.py v6.5.0] 检测到 czsc 不可用，启动自动安装...
[czsc-setup 14:31:02] 🔍 .venv-czsc 不存在或 czsc 导入失败，开始自动安装...
[czsc-setup 14:31:02]    日志写入：.venv-czsc-setup.log
[czsc-setup 14:31:02] 📦 [Tier 1] 尝试 uv（绕过系统 Python 3.9 + pip 21.x 6 层故障）...
[czsc-setup 14:31:02]    uv 不存在，安装 uv（curl）...
[czsc-setup 14:31:18]    uv 已就绪：/Users/bojue/.local/bin/uv
[czsc-setup 14:31:18]    创建 .venv-czsc（自动下载 cpython 3.11）...
[czsc-setup 14:33:44]    安装 czsc + 依赖...
[czsc-setup 14:35:21] ✅ Tier 1 (uv) 安装成功
♻️  [v6.5.0] 用 .venv-czsc 重启 czsc_check.py（.venv-czsc/bin/python）...

══════════════════════════════════════════════════
 SH600063 — czsc 0.10.12 缠论真值（日级）
══════════════════════════════════════════════════
分型 fx:  98 / 笔 bi: 20 / 当前价: 8.22
...
```

### 第二次跑（venv 已就绪）

```bash
$ python3 scripts/cli/czsc_check.py SH600063 -m
══════════════════════════════════════════════════
 SH600063 — czsc 0.10.12 缠论真值（日级）
══════════════════════════════════════════════════
（直接出结果，没有自启动开销）
```

### 自启动失败（极端环境）

```bash
$ python3 scripts/cli/czsc_check.py SH600063
🔧 [czsc_check.py v6.5.0] 检测到 czsc 不可用，启动自动安装...
[czsc-setup] 📦 [Tier 1] 尝试 uv...
[czsc-setup]    ⚠️  uv 安装失败（curl 异常，离线环境）
[czsc-setup] 📦 [Tier 2] 尝试系统 python3.11...
[czsc-setup]    系统无 python3.11
[czsc-setup] 📦 [Tier 3] 尝试 pip --user...
[czsc-setup]    ⚠️  pip install --user czsc 失败（无网络）

❌❌❌ 三级 fallback 全部失败 ❌❌❌

诊断建议：
  1. 检查 .venv-czsc-setup.log 看具体报错
  2. 确认网络可访问 astral.sh / pypi.org
  3. 手动跑：curl -LsSf https://astral.sh/uv/install.sh | sh
  ...

# 此时 czsc_check.py 会抛 RuntimeError；
# prepare_data.py 会打印警告并 fallback，让团队继续以 B 级写报告
```

---

## 3 号数据收集员（roles/03_data_collector.md）的协议变更

### v6.4.7 旧约定
> "若 .venv-czsc 不存在 → 直接 return None，报告标注 fallback B 级"

### v6.5.0 新约定（强制）

1. **首次执行 prepare_data 必须尝试自启动**：
   ```python
   from prepare_data import _ensure_czsc_venv
   venv = _ensure_czsc_venv(auto_install=True)  # 默认 True
   ```

2. **无论自启动成功还是失败，都必须在 03_data_collection.md 写「czsc 启动状态」段**：
   - 成功 → 标注「czsc 0.10.12 真值已启用（v6.5 自启动 Tier X 完成）」
   - 失败 → 标注「czsc 自启动失败 → 见诊断段 → fallback B 级」+ 引用 `.venv-czsc-setup.log` 关键行

3. **5 号 supervisor 新增 audit 项**：
   - 检查 03 报告是否包含「czsc 启动状态」段（缺失视同偷懒）
   - 检查 fallback 是否真的诚实标注（不是假装跑了 czsc）

---

## 与 v6.4 6 层故障的关系

v6.4 SKILL.md 中记录的 6 层故障（rs_czsc 旧版索引 / pyobjc-core 编译 / calendar 命名冲突等）**全部被 Tier 1 (uv) 绕过**——这就是 v6.5 把 uv 设为首选的根本原因。

如果 Tier 1 失败（罕见，多半是网络问题），Tier 2/3 才有可能再次撞上 6 层故障——届时降级到 fallback 才是合理的。

---

## 老板的手动 escape hatch

如果老板就是不想让 skill 自己装东西：

```bash
# 关闭自启动
python3 scripts/cli/czsc_check.py SH600063 --no-auto-setup
```

但这会让团队报告大概率走 fallback（江恩位），失去 czsc 真值能力。
