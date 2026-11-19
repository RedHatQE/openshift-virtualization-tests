"""Tests for the Polarion -> Jira docstring backfill edits."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

import pytest

from scripts.polarion_backfill.polarion_jira_backfill import scan_file
from scripts.polarion_backfill.tests.utils import (
    JIRA_ID,
    JIRA_LINE,
    POLARION_ID,
    POLARION_LINE,
    TEST_WITH_EMPTY_STP,
    TEST_WITH_MODULE_STP,
    TEST_WITH_PARAMETRIZED_POLARION,
    TEST_WITH_PLACEHOLDER_STP,
    TEST_WITH_STP,
    TEST_WITHOUT_STP,
    backfill,
    write_test_file,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_stp_linked_test_moves_polarion_without_adding_jira(tmp_path: Path) -> None:
    new_source, added, result = backfill(path=write_test_file(tmp_path=tmp_path, body=TEST_WITH_STP))

    assert new_source is not None, "the Polarion: line must still move into the docstring"
    assert POLARION_LINE in new_source, "the Polarion ID must be recorded in the docstring"
    assert "Jira:" not in new_source, "a test that links an STP must not get a Jira: fallback line"
    assert "@pytest.mark.polarion" not in new_source, "the Polarion decorator must be removed"
    assert added == [], "no Jira link may be reported as added for an STP-linked test"
    assert result.functions[0].stp_linked, "the scan must report the test as STP-linked"


def test_test_without_stp_gets_jira_and_polarion_lines(tmp_path: Path) -> None:
    new_source, added, result = backfill(path=write_test_file(tmp_path=tmp_path, body=TEST_WITHOUT_STP))

    assert new_source is not None, "a test with a mapped requirement must be backfilled"
    assert JIRA_LINE in new_source, "a test without an STP must get its Jira: line"
    assert POLARION_LINE in new_source, "the Polarion ID must be recorded in the docstring"
    assert "@pytest.mark.polarion" not in new_source, "the Polarion decorator must be removed"
    assert added == [JIRA_ID], "the added Jira link must be reported"
    assert not result.functions[0].stp_linked, "a test without an STP line must not be reported as STP-linked"


def test_no_skip_stp_adds_jira_line_for_stp_linked_test(tmp_path: Path) -> None:
    new_source, added, _ = backfill(
        path=write_test_file(tmp_path=tmp_path, body=TEST_WITH_STP),
        skip_stp=False,
    )

    assert new_source is not None, "the file must still be edited when --skip-stp is off"
    assert JIRA_LINE in new_source, "--no-skip-stp must add the Jira: line even when an STP is linked"
    assert POLARION_LINE in new_source, "the Polarion ID must be recorded in the docstring"
    assert added == [JIRA_ID], "the added Jira link must be reported"


@pytest.mark.parametrize("body", [TEST_WITH_EMPTY_STP, TEST_WITH_PLACEHOLDER_STP])
def test_stp_field_without_a_link_does_not_suppress_the_jira_line(tmp_path: Path, body: str) -> None:
    new_source, added, result = backfill(path=write_test_file(tmp_path=tmp_path, body=body))

    assert new_source is not None, "the test must be backfilled"
    assert JIRA_LINE in new_source, "an STP field without a link is not traceability, so the Jira line is required"
    assert added == [JIRA_ID], "the added Jira link must be reported"
    assert not result.functions[0].stp_linked, "an STP field without a link must not count as STP-linked"


def test_module_level_stp_does_not_replace_per_test_traceability(tmp_path: Path) -> None:
    new_source, added, result = backfill(path=write_test_file(tmp_path=tmp_path, body=TEST_WITH_MODULE_STP))

    assert new_source is not None, "the module-level STP link does not satisfy per-test traceability"
    assert JIRA_LINE in new_source, "a test without its own STP line must still get a Jira: line"
    assert added == [JIRA_ID], "the added Jira link must be reported"
    assert not result.functions[0].stp_linked, "a module-level STP link must not mark the test as STP-linked"


def test_scan_file_marks_stp_linked_test(tmp_path: Path) -> None:
    result = scan_file(path=write_test_file(tmp_path=tmp_path, body=TEST_WITH_STP), skip_stp=True)

    assert [func.name for func in result.functions] == ["test_with_stp"], "the test function must be collected"
    assert result.functions[0].stp_linked, "a test whose docstring links an STP must be marked"


def test_scan_file_without_skip_stp_never_marks_stp_linked(tmp_path: Path) -> None:
    result = scan_file(path=write_test_file(tmp_path=tmp_path, body=TEST_WITH_STP), skip_stp=False)

    assert not result.functions[0].stp_linked, "--no-skip-stp must disable the STP awareness entirely"


def test_stp_linked_parametrized_polarion_mark_is_stripped(tmp_path: Path) -> None:
    new_source, added, _ = backfill(path=write_test_file(tmp_path=tmp_path, body=TEST_WITH_PARAMETRIZED_POLARION))

    assert new_source is not None, "the parametrized Polarion mark must be migrated"
    assert "pytest.mark.polarion" not in new_source, "the Polarion mark must be stripped from parametrize"
    assert POLARION_LINE in new_source, "the Polarion ID must be recorded in the docstring"
    assert "Jira:" not in new_source, "the parametrized test links an STP, so no Jira: line is added"
    assert added == [], "no Jira link may be reported as added"

    module = ast.parse(new_source)
    test_function = next(node for node in ast.walk(module) if isinstance(node, ast.FunctionDef))
    parametrize = next(
        decorator
        for decorator in test_function.decorator_list
        if isinstance(decorator, ast.Call) and decorator.func.attr == "parametrize"
    )
    assert len(test_function.args.args) == 1, "the test must keep exactly one parameter"
    assert not parametrize.keywords, "the emptied marks= keyword must be dropped"
    rows = parametrize.args[1]
    assert isinstance(rows, ast.List), "the parametrize rows must stay a list"
    assert [row.value for row in rows.elts if isinstance(row, ast.Constant)] == [
        "one",
        "two",
    ], "both rows must survive as bare values"


def test_already_backfilled_stp_linked_test_is_unchanged(tmp_path: Path) -> None:
    body = TEST_WITH_STP.replace(f'@pytest.mark.polarion("{POLARION_ID}")\n', "").replace(
        "    STP:", f"    {POLARION_LINE}\n\n    STP:"
    )
    new_source, added, _ = backfill(path=write_test_file(tmp_path=tmp_path, body=body))

    assert new_source is None, "an already-backfilled file must not change"
    assert added == [], "no Jira link may be reported as added"


def test_leftover_polarion_marker_is_removed_when_the_docstring_already_has_the_id(tmp_path: Path) -> None:
    # The ID is already documented but the decorator is still there: only the
    # marker has to go.
    body = TEST_WITH_STP.replace("    STP:", f"    {POLARION_LINE}\n\n    STP:")
    new_source, added, _ = backfill(path=write_test_file(tmp_path=tmp_path, body=body))

    assert new_source is not None, "a leftover Polarion marker must still be removed"
    assert "@pytest.mark.polarion" not in new_source, "the leftover decorator must be removed"
    assert new_source.count(POLARION_LINE) == 1, "the existing Polarion: line must not be duplicated"
    assert "Jira:" not in new_source, "the test links an STP, so no Jira: line is added"
    assert added == [], "no Jira link may be reported as added"


@pytest.mark.parametrize("body", [TEST_WITH_STP, TEST_WITHOUT_STP])
def test_edited_source_stays_parseable(tmp_path: Path, body: str) -> None:
    new_source, _, _ = backfill(path=write_test_file(tmp_path=tmp_path, body=body))

    assert new_source is not None, "each sample must be edited"
    ast.parse(new_source)
