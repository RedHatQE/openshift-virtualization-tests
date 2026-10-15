# Project policy pre-commit hooks

The policy hooks enforce the approved source and test policies for changed
files. They are configured in `.pre-commit-config.yaml` as separate local
hooks, one per check family, all sharing this entry point:

```text
uv run python scripts/pre_commit_hooks/check_policy.py --check <family>
```

The check families are `path-policy`, `linter-directives`, `python-source`,
`test-std`, and `stp-links`. Without a `--check` selection the entry point
runs every family.

## Installation and usage

Install the Git hook once per clone (see
[`docs/DEVELOPER_GUIDE.md`](../../docs/DEVELOPER_GUIDE.md) for the full setup):

```bash
uv run pre-commit install
```

Run the hook over the staged changes (Python source checks read the Git
index, so stage the intended changes first — unstaged files are not checked):

```bash
uv run pre-commit run check-staged-paths
uv run pre-commit run check-linter-directives
uv run pre-commit run check-python-source
uv run pre-commit run check-test-std
uv run pre-commit run check-stp-links
```

Pre-commit supplies the filenames to the entry point. For staged files, the
hook reads the Git index and compares the staged result with `HEAD`; it does
not silently inspect an unstaged worktree version. Stage the intended source
changes before relying on a staged policy result.

The source-analysis checks are static. Resource discovery parses the installed
`ocp_resources` source and lazily parses only the staged/index snapshot of
imported local modules under `libs/`, `tests/`, and `utilities/`, following
transitive resource bases. They do not import cluster-facing modules or
connect to a cluster, and worktree-only local source must not affect
staged-source classification. The only network access is `check-stp-links`,
which contacts the design-docs repository through `gh api` when staged STP
references exist.

## Path checks

The hook has three separate path checks for staged paths:

1. **Generated documentation path rejection:** changes under generated
   `docs/site/` are rejected.
2. **Top-level test path rejection:** top-level test modules such as
   `tests/test_example.py` and `tests/example_test.py` are rejected. Put tests
   in a feature subdirectory under `tests/` instead.
3. **Staged symlink rejection:** staged Python symlinks and a symlinked
   `scripts/pre_commit_hooks/exceptions.toml` are rejected. The Git index
   stores only the link-target text for a symlink, not the source that runs
   after checkout, so the policy checks cannot examine what would actually
   execute. Commit the real file so its source is checked.

These path checks inspect every staged path even when pre-commit supplies no
filename arguments. Python source checks remain limited to supplied filenames.

## Pytest skip check

The pytest skip check is separate from the path checks. For added Python
source, it rejects these skip forms: `pytest.skip()`, `pytest.mark.skip`, and
`pytest.mark.skipif`, including equivalent forbidden markers reached through a
module-level `pytestmark`. The check normally uses staged added-line filtering,
but an unchanged skip call, marker, or `pytestmark` may still be reported when a
newly added or changed import or alias activates its binding. This
dependency-sensitive behavior is not a full historical all-files audit.

## Resource clients

Resource constructors and `Resource` class `.get()` calls must include an
explicit `client=` keyword whose value is syntactically not the literal
`None`. This covers known `Resource` subclasses and local wrappers discovered
by source analysis. It excludes specs, dictionaries, dictionary lookups, and
instance `.get()` calls.

Use the client already passed into the surrounding code. Do not construct a
new `DynamicClient`, and do not add a factory just to satisfy this policy.

`cache_admin_client()` is allowed when it is required for correctness. Its call
site must have a nonempty comment-only line immediately before the enclosing
statement or an inline comment within that statement's header, including
multiline calls, decorators, and defaults. Empty comments, trailing comments on
prior code, and comments in the statement body do not qualify. The hook checks
only that a comment is present; reviewers are responsible for verifying that the
explanation is correct and states the actual reason. The comment is not a
general suppression.

The staged Python checks use an added-line ratchet, but binding-sensitive checks
may still report an unchanged `time.sleep()`, pytest skip/`pytestmark`, direct
`DynamicClient`, or Resource constructor/class `.get()` call when a newly added
or changed import or alias activates its binding. The cache check is also
deletion-sensitive: removing the only qualifying comment from an otherwise
unchanged `cache_admin_client()` call may be reported even when the call itself
was not added. The hook is not a full historical all-files audit.

## Linter-directive exceptions

New `noqa`, `type-ignore`, and `pylint-disable` directives are not allowed
unless the directive has an exact record in
`scripts/pre_commit_hooks/exceptions.toml`. The manifest starts as:

```toml
exceptions = []
```

Each record must contain exactly these fields:

```toml
[[exceptions]]
rule = "noqa"
path = "path/to/file.py"
directive = "# noqa: RULE"
source_fingerprint = "sha256:<64 lowercase hexadecimal characters>"
reason = "Specific correctness reason for retaining this directive"
approval_url = "https://example.invalid/review/123"
```

Do not copy this example as an approval. `approval_url` is syntactically
validated as an HTTP(S) URL; it is not proof that approval exists. A reviewer
must verify the actual approval and the reason. Do not fabricate approval URLs
or records. Existing directives are permitted when their exact identity is
unchanged from `HEAD`; newly introduced or modified directives require a
reviewed exception record. Every new record and its matching newly introduced
or modified directive occurrence must be staged together in the same index
snapshot. One new record must match one new occurrence. Existing `reason` and
`approval_url` fields cannot be changed in place; obsolete records may be
removed.

A manifest exception identity is the rule, repository-relative path, normalized
directive text, and source fingerprint. The HEAD-versus-index linter ratchet
compares directive identities by rule, normalized directive text, and source
fingerprint; manifest records additionally bind the exception to the path. The
fingerprint is a SHA-256 of the directive rule, normalized directive comment,
and the smallest enclosing statement's attribute-free AST. It is stable across
line shifts when the statement and directive remain the same. When semicolons
place multiple simple statements on one line, a trailing directive fingerprints
the rightmost statement on that line.

The six manifest fields above are fixed; there is no occurrence field. Matching
unchanged occurrences from `HEAD` are consumed one-for-one first. Each exact
manifest record then grants one matching indexed occurrence. A copied
suppression with a distinct full identity needs its own record; a copied
suppression with the same full identity is not granted another allowance by the
existing record, even when distinct contexts share a fingerprint. Duplicate
exception records are still rejected. An obsolete record may be deleted as
cleanup. A valid-looking URL is not local approval, and the reviewer must
verify the actual approval and reason.

Renaming a Python file preserves the `HEAD` baseline of its old path, so
unchanged suppressions stay grandfathered — no new records are needed for
them. A suppression that is added or modified while renaming needs a new
record for the new repository path, and every old-path record must be deleted
as part of the same staged change (retained old-path records are rejected).
Do not edit an existing record in place — the path is part of the record
identity.

Compute a fingerprint from the complete file and the directive's one-based
line number. The helper must read the file with a context manager; use named
arguments for the helper call:

```bash
uv run python - <<'PY'
from pathlib import Path

from scripts.pre_commit_hooks.check_linter_directives import compute_source_fingerprint

path = Path("path/to/file.py")
line_number = 42
directive = "# noqa: RULE"
with path.open(encoding="utf-8") as source_file:
    source = source_file.read()
print(
    compute_source_fingerprint(
        source=source,
        line_number=line_number,
        directive=directive,
    )
)
PY
```

The line number and directive must describe the actual source. The directive
string in this example is only input to the fingerprint helper, not source to
copy into a file. Add the exact record only after the required review; the
checker does not create or infer approval metadata.

## Python-basics check

The Python-basics check is separate from the path and pytest skip checks.
Absolute imports are required, and the relative-import check applies to added
lines in every Python file. The seven rules below are scoped to added
or changed source under `libs/`, `scripts/`, `tests/`, or `utilities/`, except
that `time.sleep()` is rejected in added or changed Python anywhere, including
the root `conftest.py`. Rules 1 through 6 are Python mechanics; rule 7 adds a
marker-policy requirement for `tests/` files:

1. Replace `unittest` `self.assert*` calls with pytest `assert` statements.
2. Give every `assert` a descriptive failure message.
3. Do not add `async def`, `await`, `async for`, or `async with`; use synchronous
   code.
4. Do not add or change `time.sleep()`; use `TimeoutSampler`.
5. Do not compare values with `==` or `!=` to the boolean constants `True` or
   `False`; use implicit truthiness.
6. Compare with `None` using `is` or `is not`, not `==` or `!=`.
7. In `tests/`, a newly added requirement marker (`gpu`, `sriov`, `bgp`,
   `ibm_bare_metal`, `dpdk`, `swap`, `cpu_manager`, `numa`, `hugepages`,
   `jumbo_frame`, `rwx_default_storage`, `descheduler`, `high_resource_vm`)
   must be paired with `@pytest.mark.special_infra` at module, class, or test
   level.

The check is a staged/index added-line ratchet: unchanged legacy violations are
left alone unless a binding-sensitive check is activated by a newly added or
changed import or alias. In particular, an unchanged `time.sleep()` may still
be reported when its binding is activated; `time.sleep()` remains rejected on
added or changed Python anywhere, including the root `conftest.py`. The rules
other than 4 and 7 remain scoped to added or changed source under `libs/`,
`scripts/`, `tests/`, and `utilities/`. This is not a full historical all-files
audit of every Python rule.

## New product-test STD structure

For a product test function or method that is new when the index is compared
with `HEAD`, its own test docstring must contain:

- a meaningful description;
- nonempty `Steps:` and `Expected:` sections.

Only `Preconditions:` may be inherited from an enclosing class or module
docstring. The tracking URL must appear in the test's own docstring; a link
found only on an enclosing class or module does not satisfy a new test. A
nonempty effective `Preconditions:` section is still accepted at the test,
class, or module scope. Accepted tracking links are either a Jira/RFE browse URL on
`issues.redhat.com` or `redhat.atlassian.net` (`…/browse/KEY-N`), or a direct
STP URL in `RedHatQE/openshift-virtualization-tests-design-docs` under
`/blob/<ref>/stps/…` or `/tree/<ref>/stps/…`. A label or key alone, such as
`STP: CNV-88909`, is not accepted, and every Jira URL in a new test's own
docstring must carry `# <skip-jira-utils-check>` on that same line, whether or not
the line carries a `Jira:` label. The shared `Preconditions:` format follows
[`docs/SOFTWARE_TEST_DESCRIPTION.md`](../../docs/SOFTWARE_TEST_DESCRIPTION.md).
The hook accepts inherited shared preconditions, but cannot infer which shared
resources a test directly uses; reviewers must still name each directly used
shared resource at test level under that document's existing rule.

A docstring-only STD placeholder must have effective `__test__ = False` and
must declare `@pytest.mark.manual` on the test itself. The marker must be
direct: a marker on an enclosing class or module does not satisfy the
requirement even when the effective `__test__ = False` comes from that class or
module. The bare `@mark.manual` from `from pytest import mark` is accepted, and
so is an aliased binding such as `from pytest import mark as m` used as
`@m.manual` or `import pytest as pt` used as `@pt.mark.manual`; an unrelated
attribute such as `@framework.mark.manual`, or a pytest import that does not
resolve to the marker chain (for example `from pytest import fixture as mark`),
is not. An implemented
test must not keep the marker; remove both controls once the scenario is
automated.
Implemented tests must not have effective `__test__ = False`. When an
existing STD placeholder is converted to implementation, remove the disable.
A copied or renamed test has no `HEAD` baseline at its new path, so every
definition there must satisfy the full STD even when its qualified name is
unchanged. An additional occurrence of a qualified name already present in the
same path's `HEAD` baseline is not treated as fully new; it inherits that
name's retention obligations below.

For an existing test, any Description, `Steps:`, `Expected:`, effective
`Preconditions:`, or tracking URL that was valid in `HEAD` must remain valid in
the index. Unchanged legacy omissions remain allowed. Effective
`Preconditions:` and tracking URLs may move among their allowed test, class,
and module scopes.

This check compares qualified test names between `HEAD` and the index. It
covers product test modules under `tests/` and excludes tooling tests under
`scripts/` and utility unit tests under `utilities/unittests/`. The structure
check cannot prove prior STP/STD review, scenario coverage, epic validation, or
approval order, and it does not judge whether a scenario is negative (the
`[NEGATIVE]` indicator) or verify that `Markers:` declarations match applied
pytest markers. Those remain PR review responsibilities, not local evidence or
an arbitrary same-PR approval gate.

## STP links

The `check-stp-links` hook verifies that every staged `STP:` reference points
to a document merged on the default branch of
[openshift-virtualization-tests-design-docs](https://github.com/RedHatQE/openshift-virtualization-tests-design-docs).
References are collected from added lines of the staged Python files
pre-commit supplies; when a reference resolves to no merged document, the
commit is rejected. The merged set is fetched once per run with
`gh api` (an authenticated GitHub CLI is required); when the fetch fails, the
check fails closed rather than passing unverified references.

## Staged operation and test command

The hook intentionally compares only the relevant staged/index source with
`HEAD`; it does not claim to audit all historical Python code. Even
`uv run pre-commit run --all-files` makes these policy hooks audit the
staged/index diff only, so stage intended changes before relying on its result.
The exception manifest must remain present in the index; deleting it is
rejected. Stage each new exception record with its matching newly introduced or
modified source directive so the hook checks both in the same index snapshot.
Existing approval metadata cannot be edited in place.

The hook's unit tests, when requested, use:

```bash
uv run pytest -c scripts/pre_commit_hooks/tests/pytest.ini \
    --confcutdir=scripts/pre_commit_hooks/tests \
    scripts/pre_commit_hooks/tests
```

No cluster or network imports are required for these checks.
