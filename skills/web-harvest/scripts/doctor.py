#!/usr/bin/env python3
"""Read-only health audit for the web-harvest routing stack."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


HOME = Path.home()
SKILLS = HOME / ".agents" / "skills"


def command_version(name: str, args: list[str] | None = None) -> dict[str, object]:
    path = shutil.which(name)
    if not path:
        return {"status": "missing", "path": None}
    cmd = [path, *(args or ["--version"])]
    try:
        output = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        first = (output.stdout or output.stderr).strip().splitlines()
        return {"status": "ok" if output.returncode == 0 else "warn", "path": path, "version": first[0] if first else "unknown"}
    except Exception as exc:
        return {"status": "warn", "path": path, "error": str(exc)}


def path_check(path: Path) -> dict[str, object]:
    return {"status": "ok" if path.exists() else "missing", "path": str(path)}


def validate_anysearch_probe(returncode: int, stdout: str, stderr: str) -> tuple[str, str]:
    if returncode != 0:
        return "error", "nonzero_exit"
    text = stdout.strip()
    if not text:
        return "empty", "empty_stdout"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # 2026-09-07 修复：真实输出是 "## Search Results (1 results, 1862ms)"，
    # 带括号后缀（命中数+耗时）；旧正则要求标题后立刻结束（\s*$），从未匹配过
    # 真实响应，导致哪怕搜索真的成功也会被判定为 error——找到 AnySearch 密钥
    # 缺失问题时顺带发现，这里一并修正，不再要求标题后无内容。
    if not lines or not re.match(r"^#{1,6}\s*search results?\b", lines[0], re.I):
        return "error", "unexpected_result_heading"
    body = lines[1:]
    if body:
        first = re.sub(r"^(?:#{1,6}\s*)?[>*_`\-\s]*|[*_`\s]+$", "", body[0]).strip()
        if first.startswith("{"):
            try:
                parsed = json.loads(first)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("error") is not None:
                return "error", "error_text_result"
        if re.match(
            r"^(?:api\s+|http\s+)?error\b|^(?:an\s+)?error\s+(?:occurred|was returned)\b|"
            r"^(?:search|request|backend)\s+failed\b|^unable\s+to\s+search\b",
            first,
            re.I,
        ):
            return "error", "error_text_result"
    if not body or not re.search(r"https?://\S+", text):
        return "empty", "no_structured_search_item"
    if stderr.strip():
        return "error", "unexpected_stderr"
    return "ok", "probe_ok"


def validate_agent_reach_channels(channels: object) -> tuple[str, str, dict[str, str]]:
    if not isinstance(channels, dict) or not channels:
        return "empty", "empty_channel_report", {}
    allowed_statuses = {"ok", "warn", "off", "error"}
    statuses: dict[str, str] = {}
    healthy = 0
    for name, data in channels.items():
        if not isinstance(name, str) or not isinstance(data, dict):
            return "error", "malformed_channel_entry", {}
        status = data.get("status")
        if status not in allowed_statuses:
            return "error", "malformed_channel_status", {}
        statuses[name] = status
        if status == "ok":
            backend = data.get("active_backend")
            if not isinstance(backend, str) or not backend.strip():
                return "error", "healthy_channel_without_backend", {}
            healthy += 1
    if not healthy:
        return "empty", "no_healthy_channel", statuses
    return "ok", "probe_ok", statuses


def anysearch_check(live: bool) -> dict[str, object]:
    skill = SKILLS / "anysearch"
    cli = skill / "scripts" / "anysearch_cli.py"
    runtime = skill / "runtime.conf"
    result: dict[str, object] = {
        "status": "ok" if cli.exists() and runtime.exists() else "missing",
        "cli": str(cli),
        "runtime": str(runtime),
        "api_key_configured": bool(os.environ.get("ANYSEARCH_API_KEY") or (skill / ".env").exists()),
    }
    if runtime.exists():
        result["runtime_command"] = next((line.split(":", 1)[1].strip() for line in runtime.read_text().splitlines() if line.startswith("Command:")), None)
    if live and cli.exists():
        try:
            probe = subprocess.run([sys.executable, str(cli), "search", "OpenAI", "--max_results", "1"], capture_output=True, text=True, timeout=20)
            live_status, reason_code = validate_anysearch_probe(
                probe.returncode, probe.stdout, probe.stderr
            )
            result["live"] = live_status
            result["live_reason_code"] = reason_code
            if live_status == "error":
                result["live_error"] = (probe.stderr or probe.stdout).strip()[-500:]
        except Exception as exc:
            result["live"] = "error"
            result["live_reason_code"] = "probe_exception"
            result["live_error"] = str(exc)
    return result


def agent_reach_check(live: bool) -> dict[str, object]:
    binary = shutil.which("agent-reach")
    result: dict[str, object] = {"status": "ok" if binary else "missing", "path": binary}
    if live and binary:
        try:
            probe = subprocess.run([binary, "doctor", "--json"], capture_output=True, text=True, timeout=30)
            if probe.returncode != 0:
                result["live"] = "error"
                result["live_reason_code"] = "nonzero_exit"
                result["live_error"] = (probe.stderr or probe.stdout).strip()[-500:]
                return result
            channels = json.loads(probe.stdout)
            live_status, reason_code, statuses = validate_agent_reach_channels(channels)
            result["live"] = live_status
            result["live_reason_code"] = reason_code
            result["channels"] = statuses
        except Exception as exc:
            result["live"] = "error"
            result["live_reason_code"] = "probe_exception"
            result["live_error"] = str(exc)
    return result


def scrapling_check() -> dict[str, object]:
    """检查 Scrapling 不能只看包能否 import——DynamicFetcher/StealthyFetcher 依赖
    Playwright 浏览器内核，是单独下载的二进制，和 pip 安装是两回事。2026-09-07 实测：
    包装了半年、CLI 也在 PATH 上，但 ms-playwright 缓存目录从未创建，
    DynamicFetcher.fetch() 直接抛 BrowserType.launch_persistent_context 异常。
    这里额外验证浏览器缓存目录非空，避免再把"已安装"误判成"当前可用"。"""
    result: dict[str, object] = {
        "status": "ok" if importlib.util.find_spec("scrapling") else "missing",
        "cli": shutil.which("scrapling"),
    }
    if result["status"] != "ok":
        return result
    cache_dir = Path.home() / "Library" / "Caches" / "ms-playwright"
    browsers = sorted(p.name for p in cache_dir.glob("chromium*")) if cache_dir.exists() else []
    result["playwright_browser"] = "ok" if browsers else "missing"
    result["playwright_browsers_found"] = browsers
    if not browsers:
        result["status"] = "warn"
        result["warn"] = ("Scrapling 包已装但 Playwright 浏览器内核未下载，"
                           "DynamicFetcher/StealthyFetcher 会在首次调用时报错。"
                           "修复：python3 -m playwright install chromium")
    return result


def quality_control_check() -> dict[str, object]:
    root = SKILLS / "web-harvest"
    regression = root / "scripts" / "route_regression.py"
    result: dict[str, object] = {
        "status": "ok",
        "route_policy": str(root / "references" / "route-policy.json"),
        "source_quality": str(root / "scripts" / "source_quality.py"),
        "cache": str(root / "scripts" / "cache.py"),
    }
    required = [Path(result["route_policy"]), Path(result["source_quality"]), Path(result["cache"]), regression]
    if not all(path.exists() for path in required):
        result["status"] = "missing"
        result["missing"] = [str(path) for path in required if not path.exists()]
        return result
    try:
        probe = subprocess.run([sys.executable, str(regression), "--json"], capture_output=True, text=True, timeout=10)
        report = json.loads(probe.stdout) if probe.stdout else {}
        result["route_regression"] = f"{report.get('passed', 0)}/{report.get('total', 0)}"
        if probe.returncode != 0 or not report.get("success"):
            result["status"] = "warn"
    except Exception as exc:
        result["status"] = "warn"
        result["error"] = str(exc)
    return result


def build_report(live: bool) -> dict[str, object]:
    web_access = SKILLS / "web-access"
    wechat = SKILLS / "wechat-article-to-markdown-skill"
    stock_data = SKILLS / "stock-data"
    return {
        "mode": "live" if live else "local",
        "anysearch": anysearch_check(live),
        "agent_reach": agent_reach_check(live),
        "web_access": {
            **path_check(web_access / "SKILL.md"),
            "check_deps": str(web_access / "scripts" / "check-deps.mjs"),
            "node": command_version("node"),
        },
        "scrapling": scrapling_check(),
        "quality_control": quality_control_check(),
        "domain_skills": {
            "stock_data": path_check(stock_data / "SKILL.md"),
            "wechat_article": path_check(wechat / "SKILL.md"),
        },
        "commands": {
            "gh": command_version("gh"),
            "mcporter": command_version("mcporter"),
            "yt_dlp": command_version("yt-dlp"),
            "ffmpeg": command_version("ffmpeg", ["-version"]),
        },
    }


def print_human(report: dict[str, object]) -> None:
    print(f"web-harvest doctor ({report['mode']})")
    print("=" * 36)
    for key in ("anysearch", "agent_reach", "web_access", "scrapling", "quality_control"):
        item = report[key]
        suffix = f", live={item.get('live')}" if "live" in item else ""
        if key == "quality_control" and item.get("route_regression"):
            suffix += f", routes={item['route_regression']}"
        print(f"{key}: {item.get('status')}{suffix}")
    for key, item in report["domain_skills"].items():
        print(f"{key}: {item.get('status')}")
    for key, item in report["commands"].items():
        print(f"{key}: {item.get('status')} ({item.get('path') or '-'})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the web-harvest routing stack without changing configuration.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--live", action="store_true", help="Run lightweight AnySearch and Agent Reach network probes")
    args = parser.parse_args()
    report = build_report(args.live)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)


if __name__ == "__main__":
    main()
