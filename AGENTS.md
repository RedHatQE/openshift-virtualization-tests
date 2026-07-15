# AI Review and Development Standards

Assisted-by: Claude <noreply@anthropic.com>

Coding standards, conventions, and review guidelines for openshift-virtualization-tests.

> These rules apply to ALL contributors and review tools — human and AI alike.


## Strict Rules (MANDATORY)

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
5. **CHECK** `pyproject.toml` dependencies — project packages (e.g., `pyhelper-utils`, `ocp-resources`, `openshift-python-wrapper`) may already provide the functionality
6. **VERIFY** no similar logic exists elsewhere
7. **NEVER** duplicate logic - extract to shared module
8. **REUSE** existing code and patterns — only write new when nothing exists

**External package examples:**
- **Shell commands** — use `pyhelper_utils.shell.run_command`, NEVER use `subprocess.run` directly in test/utility code
- **OpenShift resources** — use `ocp-resources` classes, NEVER construct raw YAML dicts

### Python Requirements

- **Type hints MANDATORY** - mypy strict mode in `libs/`, all new public functions under utilities MUST be typed
- **Use `TYPE_CHECKING` for type-only imports** - wrap imports needed solely for type hints in `if TYPE_CHECKING:` to avoid runtime overhead and circular imports
- **Google-format docstrings REQUIRED** - for all public functions with non-obvious return values OR side effects
- **No defensive programming** - fail-fast, don't hide bugs with fake defaults (see exceptions below)
- **ALWAYS use `uv run`** - NEVER execute `python`, `pip`, `pytest`, `tox`, or `pre-commit` directly. Use `uv run python`, `uv run pytest`, `uv run tox`, `uv run pre-commit`, `uv add` for package installation.
- **ALWAYS use absolute imports** - NEVER use relative imports
- **Prefer specific imports** - use `from module import func` for functions and constants. Use `from package import module` (then `module.Name`) when retaining the module name at the call site meaningfully improves readability (e.g. `libstuntime.ContinuousPing` vs a bare `ContinuousPing` that loses its origin). Never use bare `import module` without a `from` clause.
- **ALWAYS use named arguments** - for function calls with more than one argument
- **NEVER use single-letter variable names** - ALWAYS use descriptive, meaningful names
- **No dead code** - every function, variable, fixture MUST be used or removed. Code marked with `# skip-unused-code` is excluded from dead code analysis (enforced via custom ruff plugin).
- **Prefer direct attribute access** - use `foo.attr` directly. Save to variables only when: reusing the same attribute multiple times improves readability, or extracting clarifies intent.
- **Imports always at the top of the module** - do not import inside functions
- **`conftest.py` is for fixtures only** - helper functions, utility functions, and classes must NOT be defined in conftest.py or test_*.py; place them in dedicated utility modules instead

### Utility Module Placement

When adding functions to `utilities/`, place them in the module that matches the domain.
Each module is named after its domain (e.g., `network.py` for networking, `storage.py` for storage).

- Browse `utilities/` for existing modules before creating a new one
- If no matching module exists, create one named after the domain
- **NEVER** add functions to the wrong utility module — match the domain

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

### Test Design Workflow (MANDATORY)

New feature tests MUST follow the STD-first workflow:

1. **STP (Software Test Plan)** — required for new features. Must be reviewed and approved before writing STDs.
2. **STD (Software Test Description)** — placeholder tests with docstrings (`__test__ = False`) must be reviewed before implementation.
3. **Implementation** — only after STD review is approved.

- ❌ **NEVER** submit test implementation without prior STD review
- ❌ **NEVER** skip the STD phase by submitting implementation directly
- ✅ STD and implementation MAY be in the same PR if STD is clearly separated and reviewed first

### Coverage Tracking

- **STP link REQUIRED** — every new feature test file MUST include an STP link in the module, class, or test docstring
- **STP scenario coverage REQUIRED** — when an STD or test references an STP, every test scenario defined in that STP MUST have a corresponding STD/test declaration in the same file or PR, unless the scenario is intentionally excluded. Intentional exclusions MUST be documented in the PR description with justification and a follow-up Jira link per excluded scenario. Partial STP coverage without documented exclusions blocks merge.
- **STD alignment with STP** — STD docstring `Preconditions:`, `Steps:`, and `Expected:` sections MUST align with the STP scenario description for the scenario being covered.
- **RFE/Jira link REQUIRED when no STP exists** — if there is no STP, the module, class, or test docstring MUST include a link to the RFE or Jira epic (not support cases) for coverage tracking

### Test Requirements

- **All new tests MUST have markers** - check pytest.ini for available markers, NEVER commit unmarked tests
  - **Tier marker semantics**: tier2 = customer use case tests (default), tier3 = complex/hardware/platform-specific/time-consuming tests. Assign the correct tier based on what the test validates, not its complexity.
  - **`tier2` is implicit** — added automatically to all tests that don't have an exclusion marker (see `EXCLUDE_MARKER_FROM_TIER2_MARKER` in `conftest.py` for the full list). Do NOT add `@pytest.mark.tier2` explicitly.
  - **Team markers are implicit** — `network`, `storage`, `virt`, `iuo`, `observability`, `infrastructure`, `data_protection`, and `chaos` are added automatically based on the test's directory location. Do NOT add them explicitly.
  - **`gating` marker** — marks tier2 tests that are part of the gating job. Apply when a test should block release promotion.
  - **`special_infra` marker REQUIRED for special hardware/configuration** — new tests that require non-standard cluster capabilities MUST include `@pytest.mark.special_infra` at module (`pytestmark`), class, or test level, in addition to the specific requirement marker. See `pytest.ini` marker definitions. This applies when the test uses any of:
    - **Hardware requirements** (`pytest.ini`): `gpu`, `sriov`, `bgp`, `ibm_bare_metal`
    - **Configuration requirements** (`pytest.ini`): `dpdk`, `swap`, `cpu_manager`, `numa`, `hugepages`, `jumbo_frame`, `rwx_default_storage`, `descheduler`
    - **Resource requirements** (`pytest.ini`): `high_resource_vm`
    - **Exempt** (do NOT require `special_infra`): `single_nic` (runs on minimal-NIC clusters), `remote_cluster`, `mixed_os_nodes`, `cclm`, and operator-only markers (`hpp`, `mtv`, `tekton`, `service_mesh`, `nmstate`)
- **Each test verifies ONE aspect only** - single purpose, easy to understand
- **Tests MUST be independent** - use `pytest-dependency` ONLY when test B requires side effects from test A (e.g., cluster-wide configuration).
  For resource dependencies, use shared fixtures instead. **When using `@pytest.mark.dependency`, a comment explaining WHY the dependency exists is REQUIRED.**
- **ALWAYS use `@pytest.mark.usefixtures`** - REQUIRED when fixture return value is not used by test
- **Do not offer to use `pytest.skip()` or `@pytest.mark.skip` or `@pytest.mark.skipif`** - pytest skip and skipif options are forbidden

**`__test__ = False` Usage Rules:**

- ✅ **ALLOWED for STD placeholder tests** - tests that contain ONLY:
  - Docstrings describing expected behavior
  - No actual implementation code (no assertions, no test logic)
- ❌ **FORBIDDEN for implemented tests** - if a test has actual implementation code (assertions, test logic, setup/teardown), do NOT use `__test__ = False`

**Rationale:** STD (Standard Test Design) placeholder tests document what will be tested before implementation. These can use `__test__ = False` to prevent collection errors. Once a test has implementation code, `__test__ = False` must be removed.

**STD Docstring Format (MANDATORY):**

When writing or reviewing STD (Software Test Description) test docstrings, follow the format defined in [`docs/SOFTWARE_TEST_DESCRIPTION.md`](docs/SOFTWARE_TEST_DESCRIPTION.md):
- **Required sections:** `Preconditions:`, `Steps:`, `Expected:`
- ❌ **NEVER** use alternative section names.
- Each test verifies ONE thing with ONE `Expected:` assertion (rare exceptions allowed when multiple assertions verify a single behavior — see STD doc)
- **No implementation details in STD docstrings** — no fixture names, no code references, no variable names; describe behavior in natural language
- **STP link REQUIRED** — must appear directly in the module, class, or test docstring (not a reference to a README or other file); place it at the level that applies
- **Markers can be at any level** — module, class, or test docstring; place them at the level they apply to
- **Parametrized markers** — parameter values may have inline markers using `[Markers: ...]` syntax (e.g., `- ipv4 [Markers: ipv4]`) to differentiate common markers from parameter-specific ones
- **Name resources by function** — in Preconditions, name objects by their role (e.g., "client VM", "server VM", "under-test VM"), not generic labels (e.g., "VM-A", "VM-B")
- **Shared vs. test-specific preconditions** — class/module docstring holds shared `Preconditions:`, individual tests add only their own. When a shared resource (e.g., a VM) is directly used by a test, it must appear in both the shared and test-level preconditions.
- **`[NEGATIVE]` indicator REQUIRED** — tests verifying failure scenarios must include `[NEGATIVE]` in the description

### Quarantine Review Checkpoints

When reviewing quarantine PRs, verify the **quarantine mechanism matches the failure category** (see `docs/QUARANTINE_GUIDELINES.md` for full procedures):

| Failure Category                            | Correct Mechanism                                             | Wrong Mechanism                         |
|---------------------------------------------|---------------------------------------------------------------|-----------------------------------------|
| **Product bug** (feature broken in product) | `@pytest.mark.jira("CNV-XXXXX", run=False)`                   | `@pytest.mark.xfail` with `QUARANTINED` |
| **Automation issue or unidentified** (test code problem, potential bug, or env issue under investigation) | `@pytest.mark.xfail(reason=f"{QUARANTINED}: ...", run=False)` | `@pytest.mark.jira`                     |

**Why this matters:**
- `pytest.mark.jira` is **conditional** — test auto-re-enables when the Jira is resolved
- `@pytest.mark.xfail` quarantine is **unconditional** — requires a manual de-quarantine PR to remove

**Review signal:** If the quarantine reason describes a **confirmed** product behavior that is broken (e.g., "feature X is not functioning in Y"), it is a product bug — use `@pytest.mark.jira`. If the root cause is unclear, under investigation, or relates to test/automation/environment issues (e.g., "test times out due to framework issue", "intermittent failure under investigation"), use `@pytest.mark.xfail` quarantine.

- **`quarantined` marker is auto-added** — tests with `@pytest.mark.xfail(reason=f"{QUARANTINED}: ...", run=False)` automatically receive the `quarantined` marker at collection time. Do NOT add `@pytest.mark.quarantined` explicitly.

### Fixture Guidelines (CRITICAL)

1. **Single Action REQUIRED**: Fixtures MUST do ONE action only (single responsibility)
2. **Naming REQUIRED**: ALWAYS use NOUNS (what they provide), NEVER verbs
   - ✅ `vm_with_disk`
   - ❌ `create_vm_with_disk`
3. **Parametrization format**: Use `request.param` with dict structure for complex parameters
4. **Ordering REQUIRED**: pytest native fixtures first, then session-scoped, then module/class/function scoped
5. **Fixtures should return/yield the resource** - even setup fixtures should yield the created object so tests can inspect it if needed.
6. **Fixture scope rules**:
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
- **Error messages must be specific** - include what failed, expected vs actual, and resource context. Do NOT wrap multiple calls in a single generic try/except — each function should raise its own descriptive error.

**Function Design:**
- **No hidden side effects** - function behavior MUST be controlled via explicit arguments, not hardcoded internally. If a function starts/stops a VM, that should be visible to the caller via an argument, not buried in the implementation.
- **NEVER use `async`** - the codebase does not use async/await patterns.

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
- **Do NOT duplicate TimeoutSampler logs** - the sampler already logs timeout duration and exceptions. Only log additional context (e.g., resource state, what was being waited for).

**Assertions:**
- **Use pytest assertions** - `assert actual == expected`, NEVER `self.assertEqual()`
- **Include failure messages** - `assert condition, "descriptive message explaining failure"`

**Boolean Checks:**
- **Use implicit boolean** - `if items:` NOT `if len(items) > 0:` or `if items != []:`
- **Use identity for None** - `if x is None:` NOT `if x == None:`
- **NEVER compare to True/False** - `if flag:` NOT `if flag == True:`

### Tests Directory Organization

- **Feature subdirectories REQUIRED** - each feature MUST have its own subdirectory under component (e.g., `tests/network/ipv6/`)
- **Tests belong under the feature they test** - do NOT create standalone directories for cross-cutting concerns. If a test measures VM downtime during migration over a specific network type, it belongs under that network type's directory (e.g., `tests/network/l2_bridge/`), not a separate top-level directory.
- **Test file naming REQUIRED** - ALWAYS use `test_<functionality>.py` format
- **Local helpers location** - place helper utils in `<feature_dir>/utils.py`
- **Local fixtures location** - place in `<feature_dir>/conftest.py`
- **Move to shared location** - move to `utilities/` or `tests/conftest.py` ONLY when used by different team directories

### Scripts Directory

Internal tooling and automation scripts live in `scripts/`. Each tool has its own subdirectory with an entry point, utilities, and tests. Scripts are NOT part of the test suite — they are standalone CLI tools for CI/CD integration and reporting.

### Generated Documentation

`docs/site/` contains an auto-generated documentation site (produced by [docsfy](https://github.com/myk-org/docsfy)).

- ❌ **NEVER modify files under `docs/site/`** — they are auto-generated and overwritten on each regeneration
- ❌ **NEVER include `docs/site/` changes in PRs** — reject any PR that modifies generated docs
- ✅ To update, generate docs manually with docsfy and commit directly to `main` (not via PR)

### Constants Module Placement

Project constants live in `utilities/constants/` as domain-specific modules.
Each module groups constants by domain (e.g., `cluster.py`, `virt.py`, `storage.py`).

- Place new constants in the module matching their domain
- If no matching module exists, create one with a module docstring describing its scope and listing what does NOT belong (with a pointer to the correct module)
- The `__init__.py` re-exports all names for backward compatibility — new code should import directly from the submodule (e.g., `from utilities.constants.virt import X`)

### conftest.py Architecture

**Root `conftest.py`** (project root):
- Contains pytest hooks (`pytest_collection_modifyitems`, `pytest_runtest_makereport`, etc.) and global configuration
- **Do NOT add new hooks or complex logic directly** — extract into pytest plugins (registered via `pyproject.toml` entry points)
- **No fixtures** — root conftest is for hooks and plugin registration only

**`tests/conftest.py`**:
- Contains shared test fixtures used across multiple team directories
- **New shared fixtures should go in `tests/fixtures/`** as domain-specific modules (e.g., `tests/fixtures/network/`) and be imported via `tests/conftest.py`
- **Fixture-only** — no helper functions, no utility code (place those in `utilities/`)

**Feature-level `conftest.py`** (e.g., `tests/network/l2_bridge/conftest.py`):
- Contains fixtures specific to that feature directory
- Move to `tests/conftest.py` or `tests/fixtures/` only when used across team directories

### Internal API Stability

This is a test suite - internal APIs have NO backward compatibility requirements:

- Return types and method signatures can change freely
- Internal utility functions can be refactored without deprecation
- Only external interfaces (pytest markers, CLI options) need stability

### PR Discipline

- **Keep PRs focused** — each PR addresses ONE topic. Out-of-scope improvements go in a separate PR.
- **PR title must reflect the actual change** — not a side effect. If the title says "skip artifactory" but the change is "switch to DataSource", fix the title.
- **PR description must include motivation** — explain WHY the change is needed, not just what changed.
- **Mark PR as draft** when there are unresolved blockers, failing CI, or open design questions.
- **NEVER** merge a PR with known unresolved issues — fix or document them first.
- **DCO (Signed-off-by) REQUIRED** — all commits must include `Signed-off-by` trailer (enforced by CI).
- **PR template sections REQUIRED** — the PR description MUST preserve these sections from `.github/pull_request_template.md` (even if left empty):
  - `##### What this PR does / why we need it:` — MUST be present **and have meaningful content** (not blank, whitespace-only, HTML comment only, or a placeholder such as `TBD`, `TBA`, `N/A`, `-`, `none`, or `.`)
  - `##### Which issue(s) this PR fixes:` — must be present (may be empty)
  - `##### Special notes for reviewer:` — must be present (may be empty)
  - `##### jira-ticket:` — must be present (may be empty)

## Essential Commands

### Before Committing Verification (MANDATORY)

Before committing, these checks MUST pass:

```bash
# Required before every commit
uv run pre-commit run --all-files  # Linting and formatting

# Full CI checks
uv run tox

# Run utilities unit tests
uv run tox -e utilities-unittests

```

**No exceptions.** Fix all failures before committing. Do not use `--no-verify` to bypass hooks.

### AI Documentation Reference

When working on code or reviewing changes, consult `docs/site/llms.txt` for a structured index of project documentation.
To understand a specific domain, read the corresponding `.md` file from `docs/site/` listed in the index.
Per-domain documentation may also live under the relevant `tests/<domain>/` directory (e.g., `tests/network/README.md`).

- **Quick orientation** — read `docs/site/llms.txt` for the full docs index
- **Deep dive** — read specific `docs/site/<topic>.md` files relevant to the task
- ❌ **Do NOT** load `docs/site/llms-full.txt` into context — read individual topic files instead

## Related Documentation

- [`docs/CODE_ORGANIZATION.md`](docs/CODE_ORGANIZATION.md) — Constants, utilities, and fixtures layout and import rules
- [`docs/QUARANTINE_GUIDELINES.md`](docs/QUARANTINE_GUIDELINES.md) — Test quarantine and de-quarantine procedures
- [`docs/SOFTWARE_TEST_DESCRIPTION.md`](docs/SOFTWARE_TEST_DESCRIPTION.md) — STD docstring format and requirements
- [`docs/CODING_AND_STYLE_GUIDE.md`](docs/CODING_AND_STYLE_GUIDE.md) — Detailed coding and style conventions
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — Contribution guidelines
- [`tests/network/README.md`](tests/network/README.md) — Network domain knowledge: terminology, naming conventions and functionality.
- [`docs/AI_CONTRIBUTION_POLICY.md`](docs/AI_CONTRIBUTION_POLICY.md) — AI contribution disclosure requirements
- [`docs/MAINTAINER_GUIDELINES.md`](docs/MAINTAINER_GUIDELINES.md) — Maintainer/approver progression guidelines
- [`docs/ARCHITECTURE_SUPPORT.md`](docs/ARCHITECTURE_SUPPORT.md) — Multi-architecture support documentation
