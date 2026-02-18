Run all static checks on the HutWatch codebase.

Execute the following checks in order, reporting results for each:

1. **Python syntax check**: Run `python -m py_compile` on all `.py` files under `hutwatch/` and `scripts/`. Report any syntax errors.

2. **i18n key sync**: Run `python scripts/check_i18n.py` to verify Finnish and English string files have matching keys.

3. **Version sync**: Run `python scripts/check_version_sync.py` to verify `hutwatch/__init__.py` and `pyproject.toml` have the same version.

4. **Import check**: Run `python -c "from hutwatch.app import HutWatchApp"` to verify the main module imports cleanly.

Report a summary at the end: how many checks passed, how many failed, and details of any failures.
