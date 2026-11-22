"""Stateless whole-file policy checks for pre-commit.ci.

Unlike ``check_policy.py``, these checks read no Git state: pre-commit
supplies filenames and each file is read from the worktree, so the checks
also run on pre-commit.ci, which executes ``pre-commit run --all-files``
over a clean committed checkout. Only rules that hold for the entire
repository (plus async/await in the code roots) are enforced here;
staged-diff ratchets and checks that need the
project environment or network access stay in ``check_policy.py`` and run
in the "Pre-commit Policy Checks" GitHub Actions workflow.

The module must stay importable in a stdlib-only pre-commit hook
environment: import nothing beyond the standard library and sibling modules
under ``scripts/pre_commit_hooks/``.
"""

from __future__ import annotations

from ast import AST, Call, parse, walk
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.pre_commit_hooks.check_linter_directives import EXCEPTIONS_PATH
from scripts.pre_commit_hooks.check_policy import (
    DYNAMIC_CLIENT_MESSAGE,
    check_top_level_test_path,
    is_dynamic_client_call,
    module_name,
    resolved_names,
    scopes,
)
from scripts.pre_commit_hooks.check_test_basics import (
    ASYNC_COMPREHENSION_MESSAGE,
    ASYNC_FOR_MESSAGE,
    ASYNC_FUNCTION_MESSAGE,
    ASYNC_WITH_MESSAGE,
    AWAIT_MESSAGE,
    RELATIVE_IMPORT_MESSAGE,
    check_test_basics,
)
from scripts.pre_commit_hooks.policy_types import PolicyViolation, parse_check_arguments, report_violations

if TYPE_CHECKING:
    from collections.abc import Sequence

_CHECK_FAMILIES = ("banned-paths", "banned-constructs")
_BANNED_CONSTRUCT_MESSAGES = frozenset({
    RELATIVE_IMPORT_MESSAGE,
    ASYNC_FUNCTION_MESSAGE,
    ASYNC_COMPREHENSION_MESSAGE,
    AWAIT_MESSAGE,
    ASYNC_FOR_MESSAGE,
    ASYNC_WITH_MESSAGE,
})
_SYMLINKED_PYTHON_MESSAGE = "policy: Python symlinks are not allowed; commit the real file so its source is checked"
_SYMLINKED_MANIFEST_MESSAGE = (
    "policy: the exception manifest must be a real file; commit the actual manifest so its records are checked"
)


def banned_path_violations(file_path: Path) -> list[PolicyViolation]:
    """Reject banned repository paths and worktree symlinks for one file.

    Args:
        file_path: Repository-relative path selected by pre-commit.

    Returns:
        Violations for top-level test modules and Python symlinks.
    """
    violations: list[PolicyViolation] = []
    if (violation := check_top_level_test_path(file_path=file_path)) is not None:
        violations.append(violation)
    if file_path.is_symlink():
        if file_path.suffix == ".py":
            violations.append(PolicyViolation(file_path=file_path, line_number=None, message=_SYMLINKED_PYTHON_MESSAGE))
        elif file_path == EXCEPTIONS_PATH:
            violations.append(
                PolicyViolation(file_path=file_path, line_number=None, message=_SYMLINKED_MANIFEST_MESSAGE)
            )
    return violations


def banned_construct_violations(file_path: Path, source: str) -> list[PolicyViolation]:
    """Reject banned constructs in a whole Python source file.

    Reuses the staged-flow rule implementations over every line (the
    whole-file equivalent of an empty added-lines filter) and keeps only
    the rules that hold for the entire repository: relative imports and
    direct ``DynamicClient`` construction, plus async/await in the code
    roots (``libs/``, ``scripts/``, ``tests/``, ``utilities/``). Ratcheted
    rules such as ``time.sleep`` replacement stay staged-only.

    Args:
        file_path: Repository-relative path selected by pre-commit.
        source: Worktree file content to inspect.

    Returns:
        Violations for banned constructs, ordered by source location.
    """
    tree = parse(source=source, filename=str(file_path))
    file_scopes = scopes(
        tree=tree,
        module_name=module_name(file_path=file_path),
        is_package=file_path.name == "__init__.py",
    )

    def resolve_name(node: AST) -> frozenset[tuple[str, ...]]:
        return resolved_names(node=node, scopes=file_scopes)

    violations = [
        violation
        for violation in check_test_basics(
            file_path=file_path,
            source=source,
            added_lines=None,
            tree=tree,
            resolve_name=resolve_name,
        )
        if violation.message in _BANNED_CONSTRUCT_MESSAGES
    ]
    violations.extend(
        PolicyViolation(file_path=file_path, line_number=node.lineno, message=DYNAMIC_CLIENT_MESSAGE)
        for node in walk(tree)
        if isinstance(node, Call) and is_dynamic_client_call(node=node, scopes=file_scopes)
    )
    return sorted(violations, key=lambda violation: violation.line_number or 0)


def _banned_construct_violations_for_path(file_path: Path) -> list[PolicyViolation]:
    """Read one Python file from the worktree and check it, failing closed.

    Args:
        file_path: Repository-relative path selected by pre-commit.

    Returns:
        Violations for banned constructs, or a violation when the file
        cannot be read or parsed.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [PolicyViolation(file_path=file_path, line_number=None, message=f"could not be read: {error}")]
    try:
        return banned_construct_violations(file_path=file_path, source=source)
    except SyntaxError as error:
        return [
            PolicyViolation(
                file_path=file_path,
                line_number=error.lineno,
                message=f"could not be parsed: {error.msg}",
            )
        ]


def main(arguments: Sequence[str] | None = None) -> int:
    """Run whole-file policy checks over the filenames pre-commit supplies.

    Each check family can be selected individually with ``--check <family>``
    so pre-commit runs them as separate hooks; without a selection every
    family runs. Files are read from the worktree; no Git state is used.

    Args:
        arguments: Filenames and optional ``--check`` selections, or ``None``
            to use command-line arguments.

    Returns:
        Zero when all files comply, otherwise one.
    """
    file_names, selected_checks = parse_check_arguments(
        program_name="check_banned",
        check_families=_CHECK_FAMILIES,
        arguments=arguments,
    )
    violations: list[PolicyViolation] = []
    for file_name in file_names:
        file_path = Path(file_name)
        if "banned-paths" in selected_checks:
            violations.extend(banned_path_violations(file_path=file_path))
        if "banned-constructs" in selected_checks and file_path.suffix == ".py":
            violations.extend(_banned_construct_violations_for_path(file_path=file_path))
    return report_violations(violations=violations)


if __name__ == "__main__":
    raise SystemExit(main())
