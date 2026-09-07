#!/usr/bin/env python3
import importlib.util
import os
import shutil
import subprocess
import sys


def version(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip().splitlines()[0]
    except Exception as exc:
        return f"missing ({exc})"


def main():
    user_bin = os.path.expanduser("~/Library/Python/3.12/bin")
    scrapling_cli = shutil.which("scrapling") or os.path.join(user_bin, "scrapling")
    if not os.path.exists(scrapling_cli):
        scrapling_cli = "missing"
    anysearch_cli = "<your-skills-root>/anysearch/scripts/anysearch_cli.py"
    print(f"python: {sys.version.split()[0]}")
    print(f"scrapling: {'ok' if importlib.util.find_spec('scrapling') else 'missing'}")
    print(f"scrapling-cli: {scrapling_cli}")
    print(f"anysearch-cli: {anysearch_cli if os.path.exists(anysearch_cli) else 'missing'}")
    print(f"node: {version(['node', '--version']) if shutil.which('node') else 'missing'}")
    print(f"chrome: {shutil.which('google-chrome') or shutil.which('chromium') or 'check macOS /Applications'}")
    print(f"ffmpeg: {shutil.which('ffmpeg') or 'optional/missing'}")


if __name__ == "__main__":
    main()
