"""Sample sources and pipeline helpers for the polarion_backfill tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

TEST_WITH_EMPTY_STP = f'''
import pytest


@pytest.mark.polarion("{POLARION_ID}")
def test_with_empty_stp():
    """
    Test that a VirtualMachineTemplate can be created before the upgrade.

    STP:

    Steps:
        1. Create the template.
    """
    assert True
'''

TEST_WITH_PLACEHOLDER_STP = f'''
import pytest


@pytest.mark.polarion("{POLARION_ID}")
def test_with_placeholder_stp():
    """
    Test that a VirtualMachineTemplate can be created before the upgrade.

    STP: TBD

    Steps:
        1. Create the template.
    """
    assert True
'''

TEST_WITH_PARAMETRIZED_POLARION = f'''
import pytest


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("one", marks=pytest.mark.polarion("{POLARION_ID}")),
        "two",
    ],
)
def test_parametrized(value):
    """
    Test that a parametrized test keeps its parameters.

    STP: {STP_URL}
    """
    assert value
'''


def write_test_file(tmp_path: Path, body: str) -> Path:
    """Write a sample test module into tmp_path and return its path."""
    path = tmp_path / "test_sample.py"
    path.write_text(body)
    return path


def backfill(path: Path, skip_stp: bool = True) -> tuple[str | None, list[str], FileResult]:
    """Run the scan + edit pipeline on a file, with a fake Polarion -> Jira mapping."""
    result = scan_file(path=path, skip_stp=skip_stp)
    result.mapping = {
        polarion_id: {"status": "ok", "jira": [JIRA_ID]}
        for func in result.functions
        for polarion_id in func.polarion_ids
    }
    new_source, added = compute_new_source(result=result)
    return new_source, added, result
