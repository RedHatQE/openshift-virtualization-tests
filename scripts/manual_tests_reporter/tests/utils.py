# Co-authored-by: Claude <noreply@anthropic.com>
"""Test utilities for manual_tests_reporter tests."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from scripts.manual_tests_reporter.collector import ManualTestDetail


def cleanup_kept_junit_report(result_output: str) -> None:
    """Assert the kept JUnit report exists, then remove its temp directory.

    The reporter keeps the temp report directory on upload failure for
    post-mortem inspection; tests must remove it so repeated runs do not
    accumulate ``/tmp/manual_tests_reporter_*`` entries.

    Args:
        result_output: CliRunner output containing the kept-report line.
    """
    kept_line = next(
        (line for line in result_output.splitlines() if "JUnit report kept at:" in line),
        None,
    )
    assert kept_line is not None, "Expected a 'JUnit report kept at:' line in the output"
    kept_xml_path = Path(kept_line.split("JUnit report kept at:", 1)[1].strip())
    assert kept_xml_path.exists(), f"Expected the kept JUnit report at {kept_xml_path}"
    shutil.rmtree(kept_xml_path.parent)


def capture_uploaded_xml(uploaded_xml: list[str]) -> Callable[..., None]:
    """Build an upload side effect recording the JUnit XML content.

    The report file is deleted after a successful upload, so its content
    must be captured while the upload runs, not afterwards.

    Args:
        uploaded_xml: List the uploaded XML content is appended to.

    Returns:
        A side-effect callable for patching ``upload_junit_report``.
    """

    def record_upload(xml_path: Path, service: str, tags: list[str]) -> None:
        uploaded_xml.append(xml_path.read_text(encoding="utf-8"))

    return record_upload


def make_detail(
    node_id: str = "tests/net/test_a.py::TestA::test_one",
    module_markers: list[str] | None = None,
    class_markers: list[str] | None = None,
    test_markers: list[str] | None = None,
) -> ManualTestDetail:
    """Create a ManualTestDetail with minimal fields for testing.

    Args:
        node_id: Pytest node ID for the detail.
        module_markers: Module-level markers.
        class_markers: Class-level markers.
        test_markers: Test-level markers.

    Returns:
        A ManualTestDetail populated with the given marker fields.
    """
    return ManualTestDetail(
        file_path="tests/net/test_a.py",
        class_name="TestA",
        method_name="test_one",
        node_id=node_id,
        module_markers=module_markers or [],
        class_markers=class_markers or [],
        test_markers=test_markers or [],
    )


MINIMAL_MANUAL_TEST_SOURCE = "import pytest\n\n\n@pytest.mark.manual\ndef test_minimal():\n    pass\n"


def required_attr_args(tests_dir: Path, team: str | None = "NETWORK") -> list[str]:
    """Build CLI args providing every required run attribute.

    Args:
        tests_dir: Tests directory to scan.
        team: Team flag value; ``None`` omits ``--team`` for team-less runs.

    Returns:
        Flag list with ``--tests-dir``, ``--team`` and all required
        attribute overrides for an upload-ready (non-dry-run) run.
    """
    args = [
        "--tests-dir",
        str(tests_dir),
    ]
    if team is not None:
        args.extend([
            "--team",
            team,
        ])
    args.extend([
        "--bundle",
        "v4.22.0",
        "--ocp-version",
        "4.22.0",
        "--cnv-version",
        "4.22",
        "--arch",
        "amd64",
        "--cluster-name",
        "bm15a",
        "--cluster-domain",
        "example.com",
        "--sc",
        "ocs",
        "--channel",
        "candidate",
    ])
    return args


def write_manual_tests_dir(tmp_path: Path, test_count: int = 1) -> Path:
    """Create a tests directory with a given number of manual tests.

    Args:
        tmp_path: Pytest tmp_path the directory is created under.
        test_count: Number of ``@pytest.mark.manual`` tests to create.

    Returns:
        Path to the created tests directory. Node IDs are
        ``tests/test_manual_multi.py::test_manual_<n>``.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    source = "import pytest\n\n\n"
    for index in range(test_count):
        source += f"\n\n@pytest.mark.manual\ndef test_manual_{index}():\n    pass\n"
    (tests_dir / "test_manual_multi.py").write_text(
        data=source,
        encoding="utf-8",
    )
    return tests_dir


def write_minimal_tests_dir(tmp_path: Path) -> Path:
    """Create a minimal tests directory with one manual test.

    Args:
        tmp_path: Pytest tmp_path the directory is created under.

    Returns:
        Path to the created tests directory containing a single
        ``@pytest.mark.manual`` test with node ID
        ``tests/test_manual_minimal.py::test_minimal``.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_manual_minimal.py").write_text(
        data=MINIMAL_MANUAL_TEST_SOURCE,
        encoding="utf-8",
    )
    return tests_dir
