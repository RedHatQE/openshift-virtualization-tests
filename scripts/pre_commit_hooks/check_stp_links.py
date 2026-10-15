"""Verify STP references point to merged design-docs content."""

from __future__ import annotations

from re import IGNORECASE, compile
from typing import TYPE_CHECKING

from scripts.pre_commit_hooks.policy_types import PolicyViolation

if TYPE_CHECKING:
    from collections.abc import Collection
    from pathlib import Path

STP_REPOSITORY = "RedHatQE/openshift-virtualization-tests-design-docs"
_STP_URL = compile(
    pattern=(
        rf"https?://github\.com/{STP_REPOSITORY}"
        r"/(?:blob|tree)/[^\s/]+/(?P<path>stps/[^\s)>\]#?]+)"
    ),
    flags=IGNORECASE,
)
_STP_MESSAGE = f"stp-links: STP document is not merged in {STP_REPOSITORY} on the default branch: {{url}}"
_UNVERIFIED_MESSAGE = f"stp-links: could not verify STP documents against {STP_REPOSITORY}: {{error}}"


def _reference_path(url: str) -> str:
    """Return the design-docs repository path referenced by ``url``."""
    match = _STP_URL.match(string=url)
    return match.group("path").rstrip("/") if match else ""


def stp_references(indexed_source: str, added_lines: Collection[int] | None) -> dict[str, int]:
    """Map each design-docs STP URL on the given lines to its first line number.

    Args:
        indexed_source: Staged file content.
        added_lines: Line numbers to inspect, or ``None`` for every line.

    Returns:
        STP URLs mapped to the first matching line number.
    """
    references: dict[str, int] = {}
    for line_number, line in enumerate(iterable=indexed_source.split("\n"), start=1):
        if added_lines is not None and line_number not in added_lines:
            continue
        for match in _STP_URL.finditer(string=line):
            references.setdefault(match.group(0).rstrip(".,;:!'\""), line_number)
    return references


def check_stp_links(
    file_path: Path,
    references: dict[str, int],
    merged_paths: Collection[str],
) -> list[PolicyViolation]:
    """Reject STP references whose design-docs document is not merged.

    Args:
        file_path: Repository-relative source path.
        references: STP URLs mapped to their first line number.
        merged_paths: Repository-relative paths present on the design-docs
            default branch.

    Returns:
        Violations for STP URLs that resolve to no merged document.
    """
    return [
        PolicyViolation(
            file_path=file_path,
            line_number=line_number,
            message=_STP_MESSAGE.format(url=url),
        )
        for url, line_number in sorted(references.items(), key=lambda item: item[1])
        if _reference_path(url=url) not in merged_paths
    ]


def unverified_stp_violation(file_path: Path, error: str) -> PolicyViolation:
    """Return the fail-closed violation used when merged paths cannot be fetched.

    Args:
        file_path: Repository-relative source path carrying STP references.
        error: Fetch failure description.

    Returns:
        Violation reporting that the file's STP links could not be verified.
    """
    return PolicyViolation(
        file_path=file_path,
        line_number=None,
        message=_UNVERIFIED_MESSAGE.format(error=error),
    )
