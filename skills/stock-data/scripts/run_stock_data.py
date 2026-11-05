#!/usr/bin/env python3
"""Bootstrap and run stock-data in its dedicated, pinned virtual environment."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = Path(__file__).with_name("stock_data_cli.py")
REQUIREMENTS = SKILL_DIR / "requirements-runtime.txt"
VENV = SKILL_DIR / ".venv"
MARKER = VENV / ".stock-data-runtime.json"
MIN_PYTHON = (3, 10)
OFFICIAL_INDEX = "https://pypi.org/simple"


def _python_version(executable: str) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [executable, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            check=True,
            capture_output=True,
            text=True,
        )
        major, minor = result.stdout.strip().split()
        return int(major), int(minor)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def _bootstrap_python() -> str:
    candidates = [
        os.environ.get("STOCK_DATA_BOOTSTRAP_PYTHON"),
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
        shutil.which("python3"),
        sys.executable,
    ]
    for candidate in candidates:
        if candidate and (_python_version(candidate) or (0, 0)) >= MIN_PYTHON:
            return candidate
    raise SystemExit("stock-data runtime requires Python 3.10 or newer")


def _runtime_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _requirements_digest() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def _marker_matches(digest: str) -> bool:
    try:
        payload = json.loads(MARKER.read_text(encoding="utf-8"))
        return payload.get("requirements_sha256") == digest and _runtime_python().is_file()
    except (OSError, json.JSONDecodeError):
        return False


def _installed_versions_match(runtime_python: Path) -> bool:
    expected = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "==" in line:
            name, version = line.split("==", 1)
            expected[name] = version
    probe = (
        "import importlib.metadata as m,json,sys; "
        "e=json.loads(sys.argv[1]); "
        "sys.exit(0 if all(m.version(k)==v for k,v in e.items()) else 1)"
    )
    try:
        subprocess.run(
            [str(runtime_python), "-c", probe, json.dumps(expected)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _ensure_runtime() -> Path:
    digest = _requirements_digest()
    runtime_python = _runtime_python()
    if not runtime_python.is_file():
        subprocess.run(
            [_bootstrap_python(), "-m", "venv", str(VENV)],
            check=True,
            stdout=sys.stderr,
        )
    if not _marker_matches(digest) or not _installed_versions_match(runtime_python):
        subprocess.run(
            [
                str(runtime_python), "-m", "pip", "install",
                "--disable-pip-version-check", "--index-url", OFFICIAL_INDEX,
                "-r", str(REQUIREMENTS),
            ],
            check=True,
            stdout=sys.stderr,
        )
        MARKER.write_text(
            json.dumps(
                {
                    "requirements_sha256": digest,
                    "index_url": OFFICIAL_INDEX,
                    "python": str(runtime_python),
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
    return runtime_python


def main() -> None:
    if os.environ.get("STOCK_DATA_USE_SYSTEM_PYTHON") == "1":
        os.execv(sys.executable, [sys.executable, str(CLI), *sys.argv[1:]])
    runtime_python = _ensure_runtime()
    os.execv(str(runtime_python), [str(runtime_python), str(CLI), *sys.argv[1:]])


if __name__ == "__main__":
    main()
