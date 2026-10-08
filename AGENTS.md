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
- **Project-level config exceptions only** — `.flake8` and `pyproject.toml` contain deliberate historical suppression rules (e.g., `N802` for stdlib API overrides). Do NOT add new suppression rules to these files without explicit maintainer approval. All inline `# noqa` remains prohibited without exception.

**Known per-file suppression exceptions (do NOT re-add inline noqa for these):**
- **`tests/global_config*.py`** — `config` is runtime-injected by `pytest_testconfig`; `F821` is globally suppressed via `per-file-ignores`. Do NOT add inline `# noqa: F821` — the global suppression already covers it.
- **`N802` in `utilities/logger.py` and `scripts/tests_analyzer/pytest_marker_analyzer.py`** — method names are stdlib-mandated and cannot be renamed: `formatTime` is called by `logging.Formatter` internally, and `visit_ImportFrom` / `visit_FunctionDef` / etc. are dispatched dynamically by `ast.NodeVisitor` using the AST node's class name. Renaming them would silently break the override. Do NOT attempt to rename these methods.
- **`fcn_exclude_functions` in `.flake8`** (e.g., `enter_context`, `callback`) — standard repository configuration; do not modify.

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
- **ALWAYS use named arguments** - for function calls with more than one argument. Do NOT add bare `*` to function signatures solely to force keyword-only arguments — named-argument usage is enforced by convention, not by signature enforcement.
- **NEVER use single-letter variable names** - ALWAYS use descriptive, meaningful names
- **No dead code** - every function, variable, fixture MUST be used or removed. Code marked with `# skip-unused-code` is excluded from dead code analysis (enforced via custom ruff plugin).
- **Prefer direct attribute access** - use `foo.attr` directly. Save to variables only when: reusing the same attribute multiple times improves readability, or extracting clarifies intent.
- **Imports always at the top of the module** - do not import inside functions
- **`tests/conftest.py` and feature-level `conftest.py` files are for fixtures only** - helper functions, utility functions, and non-test classes must NOT be defined in these conftest.py files or in test_*.py; place them in dedicated utility modules instead (test classes used to group pytest tests are allowed in test_*.py). The root `conftest.py` is exempt — it holds only pytest hooks and plugin registration (see "conftest.py Architecture" below).

### HCO CR (v1)

CNV 5.0+ uses HyperConverged **v1** only. Never pin `api_version` to v1beta1.

- Spec patches and reads are nested dicts that match the CR groups (`virtualization`, `storage`, `security`, `deployment`, `workloadSources`, `networking`). Inline those names; do not add group-key constants.
- `spec.featureGates` is a list of `{name, state}` objects. Enable or disable with `hco_feature_gates_patch`. Read effective state with `is_feature_gate_enabled`. **Absence is not false** — it means the CRD phase default.
- Never write a featureGates **dict** (`{"featureGates": {"downwardMetrics": True}}`).
- `status.*` is not grouped.

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
- ❌ **Defensive `.get()` on guaranteed config keys** - Do NOT use `py_config.get('key')` when the key is always present in the config schema. Use direct access `py_config['key']` so a missing key raises an immediate `KeyError`.
- ❌ **`try/except AttributeError` on `ocp_resources` objects** - Do NOT wrap nested attribute access (e.g., `deployment.instance.status.readyReplicas`) in `try/except AttributeError`; `ocp_resources` handles missing attributes gracefully without raising `AttributeError`.

### Test Design Workflow (MANDATORY)

New feature tests MUST follow the STD-first workflow:

1. **STP (Software Test Plan)** — required for new features. Must be reviewed and approved before writing STDs.
2. **STD (Software Test Description)** — placeholder tests with docstrings, direct `@pytest.mark.manual`, and effective `__test__ = False` must be reviewed before implementation.
3. **Implementation** — only after STD review is approved; remove the placeholder controls when automation is added.

- ❌ **NEVER** submit test implementation without prior STD review
- ❌ **NEVER** skip the STD phase by submitting implementation directly
- ✅ STD and implementation MAY be in the same PR if STD is clearly separated and reviewed first

### Coverage Tracking

**Scope:** All traceability and STD lifecycle/format rules below, including the `__test__ = False` Usage Rules, apply only to product tests under `tests/`. Utilities unit tests under `utilities/unittests/` and tooling tests under `scripts/` are exempt; they require no STP/Jira traceability or STD docstring/lifecycle controls.

- **Per-test STP link REQUIRED** — every new product test function/method under `tests/` MUST include the exact `STP: <URL>` line in its own docstring when an STP exists. A module- or class-level link may provide shared context but does not replace per-test traceability
- **STP scenario coverage REQUIRED** — when an STD or test references an STP, every scenario in that STP which is in scope for this repo MUST have a corresponding STD/test declaration, either in the same file/PR or tracked per the incremental-delivery rule below. Partial coverage without one of the documented exclusions below blocks merge.
  - **Out-of-repo scenarios are not required here** — if the STP's own Test Strategy / Testing Tools & Frameworks section assigns a scenario to a different repository or test tier (e.g., Tier 1 scenarios owned by a dedicated feature repo while this repo covers Tier 2/Tier 3), that scenario is out of scope for this repo's coverage check. Cite the STP section that assigns ownership in the PR description (`Special notes for reviewer:`); no follow-up Jira link is required since coverage lives elsewhere.
  - **Incremental delivery across multiple PRs is allowed** — in-repo STP scenarios MAY be delivered a few at a time across a series of PRs rather than all in one PR. The PR description MUST list which scenarios this PR covers and link the tracking Jira (epic or umbrella ticket) under which the remaining in-repo scenarios will be delivered.
  - **Other intentional exclusions** — for any in-repo scenario excluded for a reason other than the two cases above (e.g., regression scenarios excluded from STP tables or scenarios inherited through child-STP extensions from parent STPs), document the justification in the PR description AND add a follow-up Jira link per excluded scenario.
- **STD alignment with STP** — STD docstring `Preconditions:`, `Steps:`, and `Expected:` sections MUST align with the STP scenario description for the scenario being covered.
- **Jira fallback REQUIRED when no STP exists** — if there is no STP, every new product test function/method under `tests/` MUST include the exact `Jira: <issue URL>` line in its own docstring. Use RFE/Jira issue links, never support-case links; include `# <skip-jira-utils-check>` on the same line. Module- or class-level links do not replace per-test traceability
- **Traceability preservation on modification REQUIRED** — when a PR modifies a test that references an STP, Jira, or RFE link, the modified test MUST retain its valid traceability link. New-format tests retain the direct link in their own docstring; legacy tests may retain historical labels and inherited module/class links. Removal or invalidation of the only traceability reference blocks merge. For STP-linked tests, reviewers MUST additionally verify that `Preconditions:`, `Steps:`, and `Expected:` docstring sections remain consistent with the STP, and that changes to the test body (assertions, fixture usage, helper calls) do not alter what the test validates in a way that diverges from the STP scenario. Misalignment between the modified test and its STP scenario blocks merge. New tests MUST NOT rely only on inherited module- or class-level links.
- **Traceability on deletion REQUIRED** — when a PR deletes a test (or test class/module) that references an STP, Jira, or RFE link, the PR description MUST document the justification (e.g., scenario removed from STP, consolidated into another test, feature deprecated). If the covered issue, feature, or scenario is still valid, a follow-up Jira link for re-coverage MUST be included. Deletion of traceability-linked tests without documented justification blocks merge.
- **False-positive violations from base-branch divergence** — ignore STP Link or Docstring Coverage violations reported during CNV release version-bump PRs or similar base-branch-only changes; these are caused by divergence between the PR base and the branch head, not by actual missing coverage.

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
  - A direct `@pytest.mark.manual` decorator
- ❌ **FORBIDDEN for implemented tests** - if a test has actual implementation code (assertions, test logic, setup/teardown), remove both `@pytest.mark.manual` and `__test__ = False`
- **Collection rule** - `@pytest.mark.manual` classifies a test but does not prevent pytest collection. Every docstring-only test must also have effective `__test__ = False` at module, class, or test-function scope. When partially automating a class/module, move suppression onto each remaining placeholder before removing the shared assignment.

**Rationale:** STD (Standard Test Design) placeholder tests document what will be tested before implementation. These can use `__test__ = False` to prevent collection errors. Every unautomated or docstring-only test also requires a direct `@pytest.mark.manual` decorator; the marker classifies the test but does not suppress collection. Once a test has implementation code, remove both `@pytest.mark.manual` and `__test__ = False` while retaining its direct traceability line.

**STD Docstring Format (MANDATORY):**

When writing or reviewing STD (Software Test Description) test docstrings, follow the format defined in [`docs/SOFTWARE_TEST_DESCRIPTION.md`](docs/SOFTWARE_TEST_DESCRIPTION.md):
- **Required sections:** `Preconditions:`, `Steps:`, `Expected:`
- ❌ **NEVER** use alternative section names.
- Each test verifies ONE thing with ONE `Expected:` assertion (rare exceptions allowed when multiple assertions verify a single behavior — see STD doc)
- **No implementation details in STD docstrings** — no fixture names, no code references, no variable names; describe behavior in natural language
- **Per-test STP link REQUIRED** — when an STP exists, the exact `STP: <URL>` line must appear in every new product test function/method under `tests/` (not as a reference to a README or other file). Module- or class-level links may document shared context but do not replace the direct link
- **Jira fallback REQUIRED** — when no STP exists, every new product test function/method under `tests/` must contain the exact `Jira: <issue URL>  # <skip-jira-utils-check>` line; use an RFE/Jira issue, not a support case
- **Manual placeholder controls REQUIRED** — every unautomated or docstring-only test must have direct `@pytest.mark.manual` and effective `__test__ = False`; remove both when automation is added
- **Markers can be at any level** — module, class, or test docstring; place them at the level they apply. Keep planned non-manual markers in the Phase 1 docstring. `manual` is the exception: use the direct decorator on each placeholder test. Convert planned `Markers:` entries to `pytestmark` or `@pytest.mark` decorators only during Phase 2 automation.
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
- **WARNING level REQUIRED for** - unexpected skipped operations due to known issues, unusual configurations that may cause problems, missing optional configuration, deprecation notices. Log expected, routine filtering (e.g., skipping architecture-incompatible features) at INFO level instead.
- **ERROR level REQUIRED for** - exceptions with full context: what failed, expected vs actual values, resource state
- **NEVER use DEBUG level** - if a log is needed, use INFO.
- **NEVER log** - secrets, tokens, passwords, or PII
- **Log format REQUIRED** - Use f-string formatting:
  - `LOGGER.info(f"VM {vm} created in {ns} namespace")`
  - `LOGGER.warning(f"CRD {crd.name} is unreadable due to {jira_id} bug")`

### Code Patterns (Not Enforced by Linters)

**Exception Handling:**
- **ALWAYS re-raise with context** - use `raise NewError("message") from original_error` to preserve stack trace
- **Do not catch bare `Exception`** - catch specific exception types only. **Exception:** broad `Exception` is allowed ONLY when intentionally aggregating failures across multiple targets for comprehensive reporting (e.g., verifying VM creation across all data sources); add a comment at the `except` site documenting the aggregation intent.
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
- **NEVER place `pytest.fail()` inside a `pytest.raises()` block** — it is redundant and unreachable; the `raises` context already fails the test if the expected exception is not raised.

**Boolean Checks:**
- **Use implicit boolean** - `if items:` NOT `if len(items) > 0:` or `if items != []:`
- **Use identity for None** - `if x is None:` NOT `if x == None:`
- **NEVER compare to True/False** - `if flag:` NOT `if flag == True:`

**OS Detection:**
- **Use substring containment for OS flavor matching** — use `OS_FLAVOR_WINDOWS in os_flavor` instead of exact equality to support variations like `win-container-disk`.

**SSL / Network Security:**
- **`verify=False` / `verify_ssl=False` / `-k` are allowed ONLY for requests to intended internal-cluster endpoints.** Review credential-bearing requests and requests to any other destination individually; do not disable SSL verification broadly just because a request targets an internal host.

### Tests Directory Organization

- **Feature subdirectories REQUIRED** - each feature MUST have its own subdirectory under component (e.g., `tests/network/ipv6/`)
- **Tests belong under the feature they test** - do NOT create standalone directories for cross-cutting concerns. If a test measures VM downtime during migration over a specific network type, it belongs under that network type's directory (e.g., `tests/network/l2_bridge/`), not a separate top-level directory.
- **Test file naming REQUIRED** - ALWAYS use `test_<functionality>.py` format
- **Local helpers location** - place helper utils in `<feature_dir>/utils.py`
- **Local fixtures location** - place in `<feature_dir>/conftest.py`
- **Move to shared location** - move to `utilities/` or `tests/conftest.py` ONLY when used by different team directories

### Scripts Directory

- Internal tooling and automation scripts live in `scripts/`. Each tool has its own subdirectory with an entry point, utilities, and tests. Scripts are NOT part of the test suite — they are standalone CLI tools for CI/CD integration and reporting.
- Test suites under `scripts/` (e.g. `scripts/reportportal/*/tests/*`) cover internal tooling and are excluded from standard product test-policy lint enforcement.

**Known script behaviors (do not "fix" these):**
- **Dockerfiles** — Bitwarden Secrets CLI (`bws`) is installed unpinned via curl and requires `unzip`; this is intentional.
- **`tox.ini` `verify-bugs-are-open-gh`** — uses `pyutils-jira` env vars (`JIRA_TOKEN`, `JIRA_USER`); these are distinct from the `PYTEST_JIRA_*` vars used by `utilities/jira.py`. Do not conflate the two.
- **`.coderabbit.yaml`** — empty objects `code_generation: {}` and `issue_enrichment: {}` are required for schema validation; do not remove them.

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
- AI-analysis code sections calling `setup_ai_analysis()` and `enrich_junit_xml()` are vendored from upstream and should be kept as-is
- **Do NOT add new hooks or complex logic directly** — extract into pytest plugins (registered via `pyproject.toml` entry points)
- **No fixtures** — root conftest is for hooks and plugin registration only

**`tests/conftest.py`**:
- Contains shared test fixtures used across multiple team directories
- **New shared fixtures should go in `tests/fixtures/`** as domain-specific modules (e.g., `tests/fixtures/network/`) and be imported via `tests/conftest.py`
- **Fixture-only** — no helper functions, no utility code (place those in `utilities/`)

**Feature-level `conftest.py`** (e.g., `tests/network/l2_bridge/conftest.py`):
- Contains fixtures specific to that feature directory
- Move to `tests/conftest.py` or `tests/fixtures/` only when used across team directories
- Module-level imports that trigger global side-effects (e.g., `urllib3.disable_warnings()` from `junit_ai_utils`) are acceptable in `conftest.py`.

### Internal API Stability

This is a test suite - internal APIs have NO backward compatibility requirements:

- Return types and method signatures can change freely
- Internal utility functions can be refactored without deprecation
- Only external interfaces (pytest markers, CLI options) need stability

### PR Discipline

- **Keep PRs focused** — each PR addresses ONE topic. Out-of-scope improvements go in a separate PR. Lint cleanup PRs (e.g. pre-commit hook bumps) should NOT be asked to fix pre-existing code patterns outside the diff; address those in dedicated follow-up PRs.
- **PR title must reflect the actual change** — not a side effect. If the title says "skip artifactory" but the change is "switch to DataSource", fix the title.
- **PR description must include motivation** — explain WHY the change is needed, not just what changed.
- **Mark PR as draft** when there are unresolved blockers, failing CI, or open design questions.
- **NEVER** merge a PR with known unresolved issues — fix or document them first.
- **Re-evaluate pre-merge checks after each commit push** — always report the current check status after every new push, not just once at PR open time.
- **Ignore false-positive STP Link or Docstring Coverage violations** caused by base-branch divergence (e.g., CNV release version-bump PRs); do not ask contributors to "fix" violations that are artifacts of the diff base.
- **DCO (Signed-off-by) REQUIRED** — all commits must include `Signed-off-by` trailer (enforced by CI) with a non-empty full name in the format `Signed-off-by: Full Name <email@example.com>`. For AI disclosure trailer requirements, see [`docs/AI_CONTRIBUTION_POLICY.md`](docs/AI_CONTRIBUTION_POLICY.md).
- **PR template sections REQUIRED** — the PR description MUST preserve these sections from `.github/pull_request_template.md` (evaluated on GitHub's rendered view, not raw diff alone; Jira tickets are not required for small infra fixes or enablement changes):
  - `##### What this PR does / why we need it:` — MUST be present **and have meaningful content** (not blank, whitespace-only, HTML comment only, or a placeholder such as `TBD`, `TBA`, `N/A`, `-`, `none`, or `.`)
  - `##### Which issue(s) this PR fixes:` — must be present (may be empty)
  - `##### Special notes for reviewer:` — must be present (may be empty)
  - `##### jira-ticket:` — must be present (may be empty)

### Utilities Unit Test Requirements

Changes under `utilities/` require matching unit test coverage unless an exception below applies. If you add a function, add its tests. If you change behavior, update the assertions. Do not treat a passing `utilities-unittests` as proof of coverage — it only runs existing tests. Missing test coverage for new or modified utility code is a defect.

**Add or update unit tests in the same commit/PR when ANY of these apply:**

- A **coverage-enforced** utilities module changed (any `utilities/*.py` file **not** listed in `[tool.coverage.run] omit` in `pyproject.toml`)
- A module that already has `utilities/unittests/test_<module>.py` and the change adds or modifies **testable behavior** (new public function, changed logic, bug fix, new error path)
- A bug fix in utilities code where a mocked unit test can lock the regression without a cluster

Add or update tests in `utilities/unittests/test_<module>.py`. New public functions need dedicated test methods. For changes to existing behavior, extend the matching test rather than adding a redundant one. Follow patterns in [`utilities/unittests/README.md`](utilities/unittests/README.md) and existing `test_*.py` files. Do not put utility helpers in `conftest.py` under `utilities/unittests/`.

**Unit tests are NOT required before commit when:**

- Only **coverage-omitted** large modules changed (`virt.py`, `infra.py`, `network.py`, `storage.py`) and the change is thin wiring (parameter pass-through, logging, default value) already covered by integration tests
- The change is docs-only, import-only, or a rename with no behavior change

When unit tests are not added, state why in the PR (`##### Special notes for reviewer:`) — e.g. "coverage-omitted `virt.py` helper; behavior covered by `test_migrate_snapshot_hotplugged_vm`".

## Essential Commands

### Before Committing Verification (MANDATORY)

Before committing, these checks MUST pass:

1. **Utilities unit test assessment** — per [Utilities Unit Test Requirements](#utilities-unit-test-requirements) above: add tests when required, or document why not
2. **Commands below** — all must pass

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
- [`utilities/unittests/README.md`](utilities/unittests/README.md) — Utilities unit test patterns and coverage status
- [`docs/QUARANTINE_GUIDELINES.md`](docs/QUARANTINE_GUIDELINES.md) — Test quarantine and de-quarantine procedures
- [`docs/SOFTWARE_TEST_DESCRIPTION.md`](docs/SOFTWARE_TEST_DESCRIPTION.md) — STD docstring format and requirements
- [`docs/CODING_AND_STYLE_GUIDE.md`](docs/CODING_AND_STYLE_GUIDE.md) — Detailed coding and style conventions
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — Contribution guidelines
- [`tests/network/README.md`](tests/network/README.md) — Network domain knowledge: terminology, naming conventions and functionality.
- [`docs/AI_CONTRIBUTION_POLICY.md`](docs/AI_CONTRIBUTION_POLICY.md) — AI contribution disclosure requirements
- [`docs/MAINTAINER_GUIDELINES.md`](docs/MAINTAINER_GUIDELINES.md) — Maintainer/approver progression guidelines
- [`docs/ARCHITECTURE_SUPPORT.md`](docs/ARCHITECTURE_SUPPORT.md) — Multi-architecture support documentation
