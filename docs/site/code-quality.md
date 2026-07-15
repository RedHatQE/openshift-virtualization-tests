# Code Quality & Pre-commits

Ensure your contributions meet project standards by automatically validating formatting, strict type hints, and eliminating dead code before every commit. Running local checks avoids CI failures and reduces back-and-forth during pull request reviews.

- Python and `uv` installed on your system.
- Dependencies initialized in your local environment.

```bash
# Format code, check types, and run linters across all files
uv run pre-commit run --all-files

# Verify no unused code exists in the repository
uv run tox -e unused-code
```

1. **Initialize Git Hooks:**
   Run `uv run pre-commit install` once to configure Git to automatically run checks during `git commit`.
2. **Write and Format Code:**
   The project uses `ruff` for code formatting and linting. Run `uv run pre-commit run ruff --all-files` to automatically format files and fix common linting errors.
3. **Verify Type Hints:**
   Strict type hints are enforced via `mypy`. Check your types by running `uv run pre-commit run mypy --all-files`.
4. **Eliminate Dead Code:**
   Every function, variable, and fixture must be used. Validate that you haven't left unused code behind by running `uv run tox -e unused-code`.

## Advanced Usage

### Skipping Checks on Specific Code

Sometimes the dead-code scanner needs a hint. If a piece of code is valid but not directly referenced in a way the scanner detects, you can append a `# skip-unused-code` comment on the same line to bypass the check.

> **Warning:** The project explicitly prohibits `# noqa`, `# type: ignore`, and `# pylint: disable`. If a linter complains, fix the code. Do not disable linter rules to work around issues.

### Running Utilities Unit Tests

When modifying shared helper functions or utilities, ensure your changes don't break existing logic and maintain the 95% test coverage threshold:

```bash
uv run tox -e utilities-unittests
```

### Validating Architecture Configurations

You can also trigger specialized test environments via `tox`. To verify that tests correctly collect across all supported CPU architectures locally without needing a cluster:

```bash
uv run tox -e pytest-check-multiarch
```

## Troubleshooting

- **Pre-commit hook fails on commit:** The tool will often fix formatting errors automatically but fail the commit process. Simply run `git add` on the modified files and execute `git commit` again.
- **Tox environment issues:** If `tox` fails due to stale dependencies, force recreation of the environment by appending the recreate flag: `uv run tox -e unused-code --recreate`.
- **Commit signing errors:** Ensure your commits include a `Signed-off-by` trailer (DCO), which is enforced by CI. See [Pull Request Discipline](pr-discipline.html) for details.

## Related Pages

- [Pull Request Discipline](pr-discipline.html)
- [Test Design Workflow (STP/STD)](test-design-workflow.html)
- [Quickstart & Setup](quickstart.html)
