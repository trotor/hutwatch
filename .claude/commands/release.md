Create a new HutWatch release.

This skill chains version bump, git tag, and GitHub release creation.

Steps:

1. **Check working tree**: Run `git status` and ensure there are no uncommitted changes. If there are, ask the user to commit or stash first.

2. **Bump version**: Use the `/bump-version` skill logic:
   - Read current version from `hutwatch/__init__.py` and `pyproject.toml`
   - If an argument is provided, use it as the new version. Otherwise suggest patch/minor/major increments and ask the user.
   - Update both files with the new version.

3. **Run checks**: Execute `/lint` logic (py_compile, check_i18n, check_version_sync, import check). If any check fails, stop and report the error.

4. **Commit**: Create a commit with message `Bump version to X.Y.Z`.

5. **Tag**: Create an annotated git tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`

6. **Push**: Push the commit and tag: `git push && git push --tags`

7. **GitHub Release**: Create a release using `gh release create vX.Y.Z --title "vX.Y.Z" --generate-notes`

Report the release URL when done.
