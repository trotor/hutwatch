Bump the HutWatch version number.

Read the current version from `hutwatch/__init__.py` and `pyproject.toml`. Show the current version to the user.

If an argument is provided, use it as the new version. Otherwise ask the user for the new version number (suggest patch/minor/major increments).

Validate the version follows semver format (X.Y.Z).

Update the version in both files:
- `pyproject.toml`: the `version = "..."` line under `[project]`
- `hutwatch/__init__.py`: the `__version__ = "..."` line

After updating, show the change and ask if the user wants to commit it.
