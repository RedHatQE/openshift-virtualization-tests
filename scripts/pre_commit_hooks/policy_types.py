"""Shared value types and CLI helpers for project policy checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sys import argv
from sys import modules as system_modules
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    """Describe one repository policy violation."""

    file_path: Path
    line_number: int | None
    message: str

    def __str__(self) -> str:
        """Return a pre-commit-friendly description of the violation."""
        location = str(self.file_path)
        if self.line_number is not None:
            location = f"{location}:{self.line_number}"
        return f"{location}: {self.message}"


def parse_check_arguments(
    program_name: str,
    check_families: Sequence[str],
    arguments: Sequence[str] | None,
) -> tuple[list[str], frozenset[str]]:
    """Split command-line arguments into filenames and selected check families.

    Shared by every policy-check entry point so ``--check`` handling cannot
    drift between them.

    Args:
        program_name: Program name prefixing usage errors.
        check_families: Check families this entry point accepts.
        arguments: Raw arguments, or ``None`` to use command-line arguments.

    Returns:
        Filenames and the selected check families; without an explicit
        ``--check`` selection every family runs.

    Raises:
        SystemExit: When ``--check`` is missing a family name or names an
            unknown family.
    """
    raw_arguments = list(argv[1:]) if arguments is None else list(arguments)
    file_names: list[str] = []
    selected: set[str] = set()
    index = 0
    while index < len(raw_arguments):
        argument = raw_arguments[index]
        if argument == "--check":
            index += 1
            if index >= len(raw_arguments):
                raise SystemExit(f"{program_name}: --check requires a check family name")
            selected.add(raw_arguments[index])
        else:
            file_names.append(argument)
        index += 1
    unknown_families = selected - set(check_families)
    if unknown_families:
        raise SystemExit(f"{program_name}: unknown check family: {sorted(unknown_families)}")
    return file_names, frozenset(selected) or frozenset(check_families)


def report_violations(violations: Iterable[PolicyViolation]) -> int:
    """Sort violations, print them to stderr, and return the exit status.

    Args:
        violations: Violations from every selected check family.

    Returns:
        Zero when ``violations`` is empty, otherwise one.
    """
    ordered = sorted(
        violations,
        key=lambda violation: (
            violation.file_path.as_posix(),
            violation.line_number is None,
            violation.line_number or 0,
            violation.message,
        ),
    )
    # stderr is looked up dynamically so test frameworks replacing sys.stderr
    # (for example pytest's capsys) keep capturing the reports.
    for violation in ordered:
        print(violation, file=system_modules["sys"].stderr)
    return int(bool(ordered))
