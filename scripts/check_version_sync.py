#!/usr/bin/env python3
"""Check that version in __init__.py and pyproject.toml are in sync."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def get_init_version() -> str:
    text = (ROOT / "hutwatch" / "__init__.py").read_text()
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else ""


def get_pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    match = re.search(r'version\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else ""


def main() -> int:
    init_ver = get_init_version()
    pyproject_ver = get_pyproject_version()

    if not init_ver:
        print("ERROR: Could not find version in hutwatch/__init__.py")
        return 1
    if not pyproject_ver:
        print("ERROR: Could not find version in pyproject.toml")
        return 1

    if init_ver != pyproject_ver:
        print(f"VERSION MISMATCH: __init__.py={init_ver} vs pyproject.toml={pyproject_ver}")
        return 1

    print(f"version OK: {init_ver}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
