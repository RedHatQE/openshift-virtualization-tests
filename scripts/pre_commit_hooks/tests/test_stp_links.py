"""Unit tests for STP link verification."""

from __future__ import annotations

from pathlib import Path

from scripts.pre_commit_hooks.check_stp_links import (
    STP_REPOSITORY,
    check_stp_links,
    stp_references,
    unverified_stp_violation,
)

_MERGED_URL = (
    "https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/EVPN.md"
)
_UNMERGED_URL = (
    "https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-storage/missing.md"
)
_UNMERGED_MESSAGE = f"stp-links: STP document is not merged in {STP_REPOSITORY} on the default branch: {_UNMERGED_URL}"


def test_stp_references_collects_urls_with_first_line_numbers() -> None:
    source = f'"""STP: {_MERGED_URL}\n\nSTP: {_UNMERGED_URL}\nSTP: {_MERGED_URL}\n"""\n'

    references = stp_references(indexed_source=source, added_lines=None)

    assert references == {_MERGED_URL: 1, _UNMERGED_URL: 3}, "each URL maps to its first line"


def test_stp_references_filters_by_added_lines() -> None:
    source = f'"""STP: {_MERGED_URL}\n\nSTP: {_UNMERGED_URL}\n"""\n'

    references = stp_references(indexed_source=source, added_lines=frozenset({3}))

    assert references == {_UNMERGED_URL: 3}, "only added lines are inspected"


def test_stp_references_ignores_other_repositories() -> None:
    source = '"""STP: https://github.com/other/repo/blob/main/stps/EVPN.md\n"""\n'

    references = stp_references(indexed_source=source, added_lines=None)

    assert references == {}, "URLs outside the design-docs repository are ignored"


def test_stp_references_strips_trailing_punctuation() -> None:
    source = f'"""STP: {_UNMERGED_URL}.\n"""\n'

    references = stp_references(indexed_source=source, added_lines=None)

    assert references == {_UNMERGED_URL: 1}, "trailing sentence punctuation is not part of the URL"


def test_check_stp_links_rejects_unmerged_document() -> None:
    violations = check_stp_links(
        file_path=Path("tests/network/test_example.py"),
        references={_MERGED_URL: 1, _UNMERGED_URL: 3},
        merged_paths=frozenset({"stps/sig-network/EVPN.md"}),
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [(3, _UNMERGED_MESSAGE)], (
        "only the unmerged reference is rejected"
    )


def test_check_stp_links_accepts_merged_documents() -> None:
    violations = check_stp_links(
        file_path=Path("tests/network/test_example.py"),
        references={_MERGED_URL: 1},
        merged_paths=frozenset({"stps/sig-network/EVPN.md"}),
    )

    assert violations == [], "a merged reference must pass"


def test_unverified_stp_violation_reports_the_error() -> None:
    violation = unverified_stp_violation(file_path=Path("tests/network/test_example.py"), error="gh failed")

    assert violation.message == f"stp-links: could not verify STP documents against {STP_REPOSITORY}: gh failed", (
        "the fail-closed violation must report the fetch error"
    )


def test_check_stp_links_accepts_tree_directory_url() -> None:
    """A merged STP directory link is accepted."""
    tree_url = "https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/tree/main/stps/sig-network"

    violations = check_stp_links(
        file_path=Path("tests/network/test_example.py"),
        references={tree_url: 1},
        merged_paths=frozenset({"stps/sig-network"}),
    )

    assert violations == [], "a merged STP directory reference must pass"


def test_stp_references_excludes_fragment_from_url() -> None:
    """A scenario anchor fragment is not part of the referenced path."""
    anchored_url = f"{_MERGED_URL}#test-scenarios"

    references = stp_references(indexed_source=f'"""STP: {anchored_url}\n"""\n', added_lines=None)

    assert references == {_MERGED_URL: 1}, "the fragment must be stripped from the reference"
