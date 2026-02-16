# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.


## Strict Rules (MANDATORY)

Based on [myk-org/github-metrics CLAUDE.md](https://github.com/myk-org/github-metrics/blob/main/CLAUDE.md#strict-rules-mandatory)

### Linter Suppressions PROHIBITED

- ❌ **NEVER** add `# noqa`, `# type: ignore`, `# pylint: disable`
- ❌ **NEVER** disable linter/mypy rules to work around issues
- ✅ **FIX THE CODE** - If linter complains, the code is wrong
- If you think a rule is wrong: **ASK** the user for explicit approval

### Code Reuse (Search-First Development)

Before writing ANY new code:

1. **SEARCH** codebase for existing implementations
2. **CHECK** `utilities/` for shared functions
3. **CHECK** `libs/` for shared libraries
4. **CHECK** `tests/` for shared fixtures and helper functions
5. **VERIFY** no similar logic exists elsewhere
6. **NEVER** duplicate logic - extract to shared module
7. **REUSE** existing code and patterns — only write new when nothing exists

### Python Requirements

- **Type hints MANDATORY** - mypy strict mode in `libs/`, all new public functions under utilities MUST be typed
- **Google-format docstrings REQUIRED** - for all public functions with non-obvious return values OR side effects
- **No defensive programming** - fail-fast, don't hide bugs with fake defaults (see exceptions below)
- **ALWAYS use `uv run`** - NEVER execute `python`, `pip`, or `pytest` directly. Use `uv run python`, `uv run pytest`, `uv add` for package installation.
- **ALWAYS use absolute imports** - NEVER use relative imports
- **ALWAYS import specific functions** - use `from module import func`, NEVER `import module`
- **ALWAYS use named arguments** - for function calls with more than one argument
- **NEVER use single-letter variable names** - ALWAYS use descriptive, meaningful names
- **No dead code** - every function, variable, fixture MUST be used or removed. Code marked with `# skip-unused-code` is excluded from dead code analysis (enforced via custom ruff plugin).
- **Prefer direct attribute access** - use `foo.attr` directly. Save to variables only when: reusing the same attribute multiple times improves readability, or extracting clarifies intent.

### Acceptable Defensive Checks (Exceptions Only)

The "no defensive programming" rule has these five exceptions:

1. **Destructors/Cleanup** - May be called during incomplete initialization
2. **Optional Parameters** - Explicitly typed as `Type | None` with default `None`
3. **Lazy Initialization** - Attributes intentionally starting as `None` before first use
4. **Platform/Architecture Constants** - Features unavailable on all platforms (amd64, arm64, s390x)
5. **Unversioned External Libraries** - External dependencies with unknown API stability

**Still Prohibited (with examples):**

- ❌ **Checking attributes that are ALWAYS provided** - Do NOT check if `vm.name` exists when VirtualMachine always has a name field. If the schema guarantees it, trust it.
- ❌ **Defensive checks on data guaranteed by architecture** - Do NOT validate that `namespace.client` is not None when the Namespace class always sets client in `__init__`. If the constructor guarantees it, trust it.
- ❌ **Using `hasattr()` for type discrimination** - Do NOT use `if hasattr(obj, 'some_method')` to detect type. Use `isinstance(obj, ExpectedType)` for explicit type checking.
- ❌ **Version checking for pinned dependencies** - Do NOT check `if kubernetes_version >= X` when pyproject.toml pins the exact version. The lock file guarantees the version.

### Test Requirements

- **All new tests MUST have markers** - check pytest.ini for available markers, NEVER commit unmarked tests
  - **Tier marker reviews**: tier3 marker - when warranted (complex/hardware/platform-specific/time-consuming tests). Tier2 marker is not needed. Tier1 is not relevant.
- **Each test verifies ONE aspect only** - single purpose, easy to understand
- **Tests MUST be independent** - use `pytest-dependency` ONLY when test B requires side effects from test A (e.g., cluster-wide configuration).
  For resource dependencies, use shared fixtures instead. **When using `@pytest.mark.dependency`, a comment explaining WHY the dependency exists is REQUIRED.**
- **ALWAYS use `@pytest.mark.usefixtures`** - REQUIRED when fixture return value is not used by test

### Fixture Guidelines (CRITICAL)

1. **Single Action REQUIRED**: Fixtures MUST do ONE action only (single responsibility)
2. **Naming REQUIRED**: ALWAYS use NOUNS (what they provide), NEVER verbs
   - ✅ `vm_with_disk`
   - ❌ `create_vm_with_disk`
3. **Parametrization format**: Use `request.param` with dict structure for complex parameters
4. **Ordering REQUIRED**: pytest native fixtures first, then session-scoped, then module/class/function scoped
5. **Fixture scope rules**:
   - Use `scope="function"` (default) - for setup requiring test isolation
   - Use `scope="class"` - for setup shared across test class
   - Use `scope="module"` - for expensive setup in a test module
   - Use `scope="session"` - for setup that persists the entire test run (e.g., storage class, namespace)
   - **NEVER use broader scope if fixture modifies state or creates per-test resources**


### Logging Guidelines

- **INFO level REQUIRED for** - test phase transitions, resource creation/deletion, configuration changes, API responses, intermediate state
- **WARNING level REQUIRED for** - skipped operations due to known issues, unusual configurations that may cause problems, missing optional configuration, deprecation notices
- **ERROR level REQUIRED for** - exceptions with full context: what failed, expected vs actual values, resource state
- **NEVER use DEBUG level** - if a log is needed, use INFO.
- **NEVER log** - secrets, tokens, passwords, or PII
- **Log format REQUIRED** - Use f-string formatting:
  - `LOGGER.info(f"VM {vm} created in {ns} namespace")`
  - `LOGGER.warning(f"CRD {crd.name} is unreadable due to {jira_id} bug")`

### Code Patterns (Not Enforced by Linters)

**Exception Handling:**
- **ALWAYS re-raise with context** - use `raise NewError("message") from original_error` to preserve stack trace
- **Do not catch bare `Exception`** - catch specific exception types only
- **NEVER silently swallow exceptions** - at minimum, log the error before continuing

**Context Managers:**
- **ALWAYS use `with` for resources** - files, connections, locks MUST use context managers
- **Fixtures with cleanup MUST use yield** - use `yield resource` followed by cleanup code, NEVER return + finalizer

**Timeouts and Polling:**
- **ALWAYS use `timeout_sampler`** - from `timeout_sampler` package for any operation that waits for a condition:
  ```python
  from timeout_sampler import TimeoutSampler
  for sample in TimeoutSampler(wait_timeout=60, sleep=5, func=check_condition):
      if sample:
          break
  ```
- **NEVER use `time.sleep()` in loops** - use `timeout_sampler` with appropriate wait time

**Assertions:**
- **Use pytest assertions** - `assert actual == expected`, NEVER `self.assertEqual()`
- **Include failure messages** - `assert condition, "descriptive message explaining failure"`

**Boolean Checks:**
- **Use implicit boolean** - `if items:` NOT `if len(items) > 0:` or `if items != []:`
- **Use identity for None** - `if x is None:` NOT `if x == None:`
- **NEVER compare to True/False** - `if flag:` NOT `if flag == True:`

### Tests Directory Organization

- **Feature subdirectories REQUIRED** - each feature MUST have its own subdirectory under component (e.g., `tests/network/ipv6/`)
- **Test file naming REQUIRED** - ALWAYS use `test_<functionality>.py` format
- **Local helpers location** - place helper utils in `<feature_dir>/utils.py`
- **Local fixtures location** - place in `<feature_dir>/conftest.py`
- **Move to shared location** - move to `utilities/` or `tests/conftest.py` ONLY when used by different team directories

### Internal API Stability

This is a test suite - internal APIs have NO backward compatibility requirements:

- Return types and method signatures can change freely
- Internal utility functions can be refactored without deprecation
- Only external interfaces (pytest markers, CLI options) need stability

## Essential Commands

### Before commiting Verification (MANDATORY)

Before committing, these checks MUST pass:

```bash
# Required before every commit
pre-commit run --all-files  # Linting and formatting

# Full CI checks
tox

# Run utilities unit tests
tox -e utilities-unittests

```

**No exceptions.** Fix all failures before committing. Do not use `--no-verify` to bypass hooks.
