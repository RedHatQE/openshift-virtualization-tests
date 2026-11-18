"""Tests for the Polarion -> Jira docstring backfill edits."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

import pytest

from scripts.polarion_backfill.polarion_jira_backfill import (
    FileResult,
    compute_new_source,
    scan_file,
)

if TYPE_CHECKING:
    from pathlib import Path

STP_URL = (
    "https://github.com/RedHatQE/openshift-virtualization-tests-design-docs"
    "/blob/main/stps/sig-infra/virtual-machine-template.md"
)
JIRA_ID = "CNV-73392"
POLARION_ID = "CNV-16822"
JIRA_LINE = f"Jira: https://redhat.atlassian.net/browse/{JIRA_ID} # <skip-jira-utils-check>"
POLARION_LINE = f"Polarion: {POLARION_ID}"


def _write_test_file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "test_sample.py"
    path.write_text(body)
    return path


def _backfill(path: Path, skip_stp: bool = True) -> tuple[str | None, list[str], FileResult]:
    """Run the scan + edit pipeline on a file, with a fake Polarion -> Jira mapping."""
    result = scan_file(path=path, skip_stp=skip_stp)
    result.mapping = {
        polarion_id: {"status": "ok", "jira": [JIRA_ID]}
        for func in result.functions
        for polarion_id in func.polarion_ids
    }
    new_source, added = compute_new_source(result=result)
    return new_source, added, result


TEST_WITH_STP = f'''
import pytest


@pytest.mark.polarion("{POLARION_ID}")
def test_with_stp():
    """
    Test that a VirtualMachineTemplate can be created before the upgrade.

    STP: {STP_URL}

    Steps:
        1. Create the template.
    """
    assert True
'''

TEST_WITHOUT_STP = f'''
import pytest


@pytest.mark.polarion("{POLARION_ID}")
def test_without_stp():
    """
    Test that a VirtualMachineTemplate can be created before the upgrade.

    Steps:
        1. Create the template.
    """
    assert True
'''

TEST_WITH_MODULE_STP = f'''
"""
VM template upgrade continuity tests.

STP: {STP_URL}
"""

import pytest


@pytest.mark.polarion("{POLARION_ID}")
def test_with_module_stp_only():
    """
    Test that a VirtualMachineTemplate can be created before the upgrade.
    """
    assert True
'''

TEST_WITH_PARAMETRIZED_POLARION = f'''
import pytest


@pytest.mark.parametrize(
    "value, marks",
    [
        pytest.param("one", marks=pytest.mark.polarion("{POLARION_ID}")),
        "two",
    ],
)
def test_parametrized(value, marks):
    """
    Test that a parametrized test keeps its parameters.

    STP: {STP_URL}
    """
    assert value
'''


def test_stp_linked_test_moves_polarion_without_adding_jira(tmp_path: Path) -> None:
    new_source, added, result = _backfill(path=_write_test_file(tmp_path=tmp_path, body=TEST_WITH_STP))

    assert new_source is not None, "the Polarion: line must still move into the docstring"
    assert POLARION_LINE in new_source, "the Polarion ID must be recorded in the docstring"
    assert "Jira:" not in new_source, "a test that links an STP must not get a Jira: fallback line"
    assert "@pytest.mark.polarion" not in new_source, "the Polarion decorator must be removed"
    assert added == [], "no Jira link may be reported as added for an STP-linked test"
    assert result.functions[0].stp_linked, "the scan must report the test as STP-linked"


def test_test_without_stp_gets_jira_and_polarion_lines(tmp_path: Path) -> None:
    new_source, added, result = _backfill(path=_write_test_file(tmp_path=tmp_path, body=TEST_WITHOUT_STP))

    assert new_source is not None, "a test with a mapped requirement must be backfilled"
    assert JIRA_LINE in new_source, "a test without an STP must get its Jira: line"
    assert POLARION_LINE in new_source, "the Polarion ID must be recorded in the docstring"
    assert "@pytest.mark.polarion" not in new_source, "the Polarion decorator must be removed"
    assert added == [JIRA_ID], "the added Jira link must be reported"
    assert not result.functions[0].stp_linked, "a test without an STP line must not be reported as STP-linked"


def test_no_skip_stp_adds_jira_line_for_stp_linked_test(tmp_path: Path) -> None:
    new_source, added, _ = _backfill(
        path=_write_test_file(tmp_path=tmp_path, body=TEST_WITH_STP),
        skip_stp=False,
    )

    assert new_source is not None, "the file must still be edited when --skip-stp is off"
    assert JIRA_LINE in new_source, "--no-skip-stp must add the Jira: line even when an STP is linked"
    assert POLARION_LINE in new_source, "the Polarion ID must be recorded in the docstring"
    assert added == [JIRA_ID], "the added Jira link must be reported"


def test_module_level_stp_does_not_replace_per_test_traceability(tmp_path: Path) -> None:
    new_source, added, result = _backfill(path=_write_test_file(tmp_path=tmp_path, body=TEST_WITH_MODULE_STP))

    assert new_source is not None, "the module-level STP link does not satisfy per-test traceability"
    assert JIRA_LINE in new_source, "a test without its own STP line must still get a Jira: line"
    assert added == [JIRA_ID], "the added Jira link must be reported"
    assert not result.functions[0].stp_linked, "a module-level STP link must not mark the test as STP-linked"


def test_scan_file_marks_stp_linked_test(tmp_path: Path) -> None:
    result = scan_file(path=_write_test_file(tmp_path=tmp_path, body=TEST_WITH_STP), skip_stp=True)

    assert [func.name for func in result.functions] == ["test_with_stp"], "the test function must be collected"
    assert result.functions[0].stp_linked, "a test whose docstring links an STP must be marked"


def test_scan_file_without_skip_stp_never_marks_stp_linked(tmp_path: Path) -> None:
    result = scan_file(path=_write_test_file(tmp_path=tmp_path, body=TEST_WITH_STP), skip_stp=False)

    assert not result.functions[0].stp_linked, "--no-skip-stp must disable the STP awareness entirely"


def test_stp_linked_parametrized_polarion_mark_is_stripped(tmp_path: Path) -> None:
    new_source, added, _ = _backfill(path=_write_test_file(tmp_path=tmp_path, body=TEST_WITH_PARAMETRIZED_POLARION))

    assert new_source is not None, "the parametrized Polarion mark must be migrated"
    assert "pytest.mark.polarion" not in new_source, "the Polarion mark must be stripped from parametrize"
    assert POLARION_LINE in new_source, "the Polarion ID must be recorded in the docstring"
    assert "Jira:" not in new_source, "the parametrized test links an STP, so no Jira: line is added"
    assert '"one",' in new_source, "the parametrize value must survive as a bare value"
    assert "marks=" not in new_source, "the now-empty marks= keyword must be dropped"
    assert added == [], "no Jira link may be reported as added"


def test_already_backfilled_stp_linked_test_is_unchanged(tmp_path: Path) -> None:
    body = TEST_WITH_STP.replace(f'@pytest.mark.polarion("{POLARION_ID}")\n', "").replace(
        "    STP:", f"    {POLARION_LINE}\n\n    STP:"
    )
    new_source, added, _ = _backfill(path=_write_test_file(tmp_path=tmp_path, body=body))

    assert new_source is None, "an already-backfilled file must not change"
    assert added == [], "no Jira link may be reported as added"


@pytest.mark.parametrize("body", [TEST_WITH_STP, TEST_WITHOUT_STP])
def test_edited_source_stays_parseable(tmp_path: Path, body: str) -> None:
    new_source, _, _ = _backfill(path=_write_test_file(tmp_path=tmp_path, body=body))

    assert new_source is not None, "each sample must be edited"
    ast.parse(new_source)
