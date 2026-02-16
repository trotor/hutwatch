#!/usr/bin/env python3
"""Validate that strings_fi.py and strings_en.py have matching keys.

Exit code 0 = all OK, 1 = mismatches found.
"""

import ast
import sys
from pathlib import Path


def extract_keys(filepath: Path) -> set[str]:
    """Extract STRINGS dict keys from a strings file using AST parsing."""
    source = filepath.read_text()
    tree = ast.parse(source, filename=str(filepath))

    for node in ast.walk(tree):
        # Handle both `STRINGS = {` and `STRINGS: dict = {`
        if isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        else:
            continue

        if isinstance(target, ast.Name) and target.id == "STRINGS" and isinstance(value, ast.Dict):
            keys = set()
            for key in value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
            return keys

    return set()


def main() -> int:
    base = Path(__file__).resolve().parent.parent / "hutwatch"
    fi_path = base / "strings_fi.py"
    en_path = base / "strings_en.py"

    if not fi_path.exists() or not en_path.exists():
        print("String files not found")
        return 1

    fi_keys = extract_keys(fi_path)
    en_keys = extract_keys(en_path)

    only_fi = fi_keys - en_keys
    only_en = en_keys - fi_keys
    ok = True

    if only_fi:
        ok = False
        print(f"Keys missing from strings_en.py ({len(only_fi)}):")
        for key in sorted(only_fi):
            print(f"  - {key}")

    if only_en:
        ok = False
        print(f"Keys missing from strings_fi.py ({len(only_en)}):")
        for key in sorted(only_en):
            print(f"  - {key}")

    if ok:
        print(f"i18n OK: {len(fi_keys)} keys in sync")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
