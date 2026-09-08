#!/usr/bin/env bash
# 检查并升级本包依赖的第三方开源 skill（AnySearch、web-access）。
#
# 这两个不是本仓库自己写的代码，是按 INSTALL.md 用 git clone 装的独立开源项目，
# 不会跟着 `git pull` 这个仓库自动更新，需要单独检查。Agent Reach 的底层 CLI 是
# 全局安装的第三方工具，不在这个脚本管理范围内，升级请看它自己的项目主页。
#
# 用法：
#   ./scripts/upgrade-vendored-skills.sh                  # 默认检查 ./skills/ 下的副本
#   SKILLS_DIR=~/.agents/skills ./scripts/upgrade-vendored-skills.sh   # 检查另一个位置的副本
#   ./scripts/upgrade-vendored-skills.sh --check-only      # 只报告落后情况，不实际升级
#   ./scripts/upgrade-vendored-skills.sh --yes             # 跳过确认，直接升级（用于自动化）

set -euo pipefail

SKILLS_DIR="${SKILLS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skills}"
CHECK_ONLY=false
AUTO_YES=false

for arg in "$@"; do
  case "$arg" in
    --check-only) CHECK_ONLY=true ;;
    --yes) AUTO_YES=true ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

echo "检查目录：$SKILLS_DIR"
echo

check_one() {
  local name="$1" repo_dir="$2" smoke_test_cmd="$3"

  if [ ! -d "$repo_dir/.git" ]; then
    echo "[SKIP] ${name}：$repo_dir 不是 git 仓库（可能还没装，或者是通过非 git 方式安装的），跳过。"
    echo "   如果这是本该跟踪升级的第三方 skill，考虑按 INSTALL.md 第 3 步用 git clone 重新装一次。"
    echo
    return
  fi

  local before after ahead
  before=$(git -C "$repo_dir" rev-parse --short HEAD)
  git -C "$repo_dir" fetch --quiet origin
  ahead=$(git -C "$repo_dir" rev-list --count HEAD..origin/main 2>/dev/null || echo "?")

  if [ "$ahead" = "0" ]; then
    echo "[OK] ${name}：已是最新（${before}）。"
    echo
    return
  fi

  echo "[UPDATE] ${name}：落后上游 $ahead 个提交（当前 ${before}）。最近的上游更新："
  git -C "$repo_dir" log --oneline HEAD..origin/main | head -10 | sed 's/^/     /'
  echo

  if [ "$CHECK_ONLY" = true ]; then
    return
  fi

  if [ "$AUTO_YES" != true ]; then
    read -r -p "   要现在升级 $name 吗？[y/N] " reply
    case "$reply" in
      [yY]*) ;;
      *) echo "   跳过。"; echo; return ;;
    esac
  fi

  # 本地若有未提交改动先 stash，避免升级时被冲掉或拦住
  if [ -n "$(git -C "$repo_dir" status --porcelain)" ]; then
    echo "   检测到本地未提交改动，先 stash 保存（可用 'git -C $repo_dir stash list' 找回）："
    git -C "$repo_dir" stash push -m "auto-stash before upgrade $(date +%Y-%m-%d)"
  fi

  git -C "$repo_dir" pull --quiet origin main
  after=$(git -C "$repo_dir" rev-parse --short HEAD)
  echo "   已升级：$before → $after"

  if [ -f "$repo_dir/requirements.txt" ]; then
    python3 -m pip install -q -r "$repo_dir/requirements.txt"
  fi

  echo "   实测验证（不只看安装状态，真的跑一次）："
  if eval "$smoke_test_cmd"; then
    echo "   [OK] 验证通过：升级后功能正常。"
  else
    echo "   [FAIL] 验证失败！升级后这个 skill 可能跑不通了，建议排查或者用 'git -C $repo_dir checkout $before' 回退。"
  fi
  echo
}

check_one "AnySearch" "$SKILLS_DIR/anysearch" \
  "python3 '$SKILLS_DIR/anysearch/scripts/anysearch_cli.py' search 'upgrade smoke test' --max_results 1 >/dev/null"

check_one "web-access" "$SKILLS_DIR/web-access" \
  "node '$SKILLS_DIR/web-access/scripts/check-deps.mjs' >/dev/null"

echo "---"
echo "Agent Reach 的底层 CLI 不归本脚本管，检查更新请看：https://github.com/Panniantong/Agent-Reach/releases"
echo "投研核心六个 skill（investment-team-skill 等）是本仓库自己维护的，跟着 'git pull' 这个仓库本身即可，不需要这个脚本。"
