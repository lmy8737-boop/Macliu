#!/usr/bin/env bash
# auto_setup_czsc.sh — v6.5.0 czsc 子环境自启动一键脚本
# ============================================================
# 触发场景：3 号数据收集员检测到 .venv-czsc 不存在或 import czsc 失败时
# 自动调用本脚本，5-8 分钟内完成"零环境 → czsc 真值可用"。
#
# 设计原则：
#   1. 幂等（重复执行不破坏现有环境）
#   2. 三级 fallback（uv → python3.11 -m venv → 系统 pip --user）
#   3. 失败时打印明确根因 + 用户可操作建议
#   4. 输出到 stderr，不污染 stdout（让 caller 能 capture）
#
# 用法：
#   bash scripts/setup/auto_setup_czsc.sh                 # 默认尝试三级 fallback
#   bash scripts/setup/auto_setup_czsc.sh --strict-uv      # 仅尝试 uv，失败立即退出
#   bash scripts/setup/auto_setup_czsc.sh --check          # 只检查不安装
#
# 退出码：
#   0 = czsc venv 已就绪（import czsc 通过）
#   1 = uv 安装失败（仅 --strict-uv 模式）
#   2 = 三级 fallback 全失败（罕见）
#   3 = 用户系统缺少 Python 3.11（且 uv 也下不到）
# ============================================================

set -e

SKILL_HOME="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="$SKILL_HOME/.venv-czsc"
VENV_PY="$VENV_DIR/bin/python"
LOG_FILE="$SKILL_HOME/.venv-czsc-setup.log"

MODE="${1:-auto}"

log()  { echo "[czsc-setup $(date +%H:%M:%S)] $*" >&2; }
fail() { log "❌ $*"; exit "$2"; }

# ---- 健康检查（幂等核心）----
check_venv() {
    if [ -x "$VENV_PY" ]; then
        if "$VENV_PY" -c "import czsc; print(f'czsc {czsc.__version__} OK')" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

if check_venv; then
    log "✅ .venv-czsc 已就绪（czsc 真值可用）"
    exit 0
fi

if [ "$MODE" = "--check" ]; then
    log "⚠️  .venv-czsc 未就绪，但 --check 模式不安装"
    exit 1
fi

log "🔍 .venv-czsc 不存在或 czsc 导入失败，开始自动安装..."
log "   日志写入：$LOG_FILE"

# ============================================================
# Tier 1：uv 子环境（首选 — 5 分钟内完成）
# ============================================================
try_uv() {
    log "📦 [Tier 1] 尝试 uv（绕过系统 Python 3.9 + pip 21.x 6 层故障）..."

    UV_BIN="$HOME/.local/bin/uv"
    if [ ! -x "$UV_BIN" ]; then
        log "   uv 不存在，安装 uv（curl）..."
        if command -v curl >/dev/null 2>&1; then
            curl -LsSf https://astral.sh/uv/install.sh 2>>"$LOG_FILE" | sh >>"$LOG_FILE" 2>&1 || {
                log "   ⚠️  uv 安装失败（curl 或 sh 异常），见 $LOG_FILE"
                return 1
            }
        else
            log "   ⚠️  系统无 curl，跳过 uv tier"
            return 1
        fi
    fi

    if [ ! -x "$UV_BIN" ]; then
        # uv 安装到非默认路径，再找一次
        UV_BIN="$(command -v uv 2>/dev/null || true)"
        [ -z "$UV_BIN" ] && { log "   ⚠️  uv 装完仍找不到 binary"; return 1; }
    fi

    log "   uv 已就绪：$UV_BIN"
    log "   创建 .venv-czsc（自动下载 cpython 3.11）..."
    "$UV_BIN" venv --python 3.11 "$VENV_DIR" >>"$LOG_FILE" 2>&1 || {
        log "   ⚠️  uv venv 创建失败，见 $LOG_FILE"
        return 1
    }

    log "   安装 czsc + 依赖..."
    "$UV_BIN" pip install --python "$VENV_PY" czsc >>"$LOG_FILE" 2>&1 || {
        log "   ⚠️  uv pip install czsc 失败，见 $LOG_FILE"
        return 1
    }

    if check_venv; then
        log "✅ Tier 1 (uv) 安装成功"
        return 0
    fi
    return 1
}

# ============================================================
# Tier 2：系统 python3.11 -m venv（备选 — 需用户已装 3.11）
# ============================================================
try_system_python311() {
    log "📦 [Tier 2] 尝试系统 python3.11 -m venv..."
    PY311="$(command -v python3.11 2>/dev/null || true)"
    [ -z "$PY311" ] && { log "   系统无 python3.11"; return 1; }

    "$PY311" -m venv "$VENV_DIR" >>"$LOG_FILE" 2>&1 || {
        log "   ⚠️  python3.11 -m venv 失败"
        return 1
    }
    "$VENV_PY" -m pip install --upgrade pip >>"$LOG_FILE" 2>&1 || true
    "$VENV_PY" -m pip install czsc >>"$LOG_FILE" 2>&1 || {
        log "   ⚠️  pip install czsc 失败，见 $LOG_FILE"
        return 1
    }

    if check_venv; then
        log "✅ Tier 2 (系统 python3.11) 安装成功"
        return 0
    fi
    return 1
}

# ============================================================
# Tier 3：用户级 pip --user（最后兜底 — czsc 装到系统 Python）
# 注意：此 tier 只能保 import czsc 可用，不能解决 v6.4 的 6 层故障
# ============================================================
try_user_pip() {
    log "📦 [Tier 3] 尝试 python3 -m pip install --user czsc（兜底，可能触发 6 层故障）..."
    if ! command -v python3 >/dev/null 2>&1; then
        log "   系统无 python3"
        return 1
    fi
    python3 -m pip install --user czsc >>"$LOG_FILE" 2>&1 || {
        log "   ⚠️  pip install --user czsc 失败"
        return 1
    }
    # Tier 3 不创建 venv，直接让 caller 用系统 python3，但要打 marker
    if python3 -c "import czsc" 2>/dev/null; then
        log "⚠️  Tier 3 (系统 pip --user) 装上了，但请注意："
        log "    .venv-czsc 仍不存在，czsc_check.py 等脚本会继续 fallback"
        log "    建议老板手动跑 Tier 1（装 uv）以获得真值能力"
        # 创建标记文件，让 caller 知道
        touch "$SKILL_HOME/.czsc-system-pip"
        return 0
    fi
    return 1
}

# ---- 执行 ----
if [ "$MODE" = "--strict-uv" ]; then
    try_uv && exit 0
    fail "uv 安装失败，--strict-uv 模式直接退出" 1
fi

if try_uv; then exit 0; fi
log "→ Tier 1 失败，尝试 Tier 2..."

if try_system_python311; then exit 0; fi
log "→ Tier 2 失败，尝试 Tier 3..."

if try_user_pip; then exit 0; fi

log ""
log "❌❌❌ 三级 fallback 全部失败 ❌❌❌"
log ""
log "诊断建议："
log "  1. 检查 $LOG_FILE 看具体报错"
log "  2. 确认网络可访问 astral.sh / pypi.org"
log "  3. 手动跑：curl -LsSf https://astral.sh/uv/install.sh | sh"
log "  4. 装好 uv 后：~/.local/bin/uv venv --python 3.11 $VENV_DIR"
log "  5. 装 czsc：~/.local/bin/uv pip install --python $VENV_PY czsc"
log ""
log "团队报告将以 fallback B 级（江恩位 + 0.382 回撤）继续，"
log "缠论真值章节会标注「czsc venv 自动安装失败，已诚实降级」"
exit 2
