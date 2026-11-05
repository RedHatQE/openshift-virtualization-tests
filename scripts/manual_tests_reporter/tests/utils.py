# Co-authored-by: Claude <noreply@anthropic.com>
"""Test utilities for manual_tests_reporter tests."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from scripts.manual_tests_reporter.collector import ManualTestDetail


def junit_report_path(tests_dir: Path) -> Path:
    """Return the JUnit XML report path CLI tests write to.

    Args:
        tests_dir: Tests directory the run scans.

    Returns:
        The deterministic report path ``required_attr_args`` passes via
        ``--junit-output`` (a sibling of the tests directory, so every CLI
        test writes there without per-call flags).
    """
    return tests_dir.parent / "xunit_results.xml"


def read_junit_properties(xml_path: Path) -> dict[str, str]:
    """Read the first testcase's property name→value map from a report.

    Args:
        xml_path: Path to the written JUnit XML report.

    Returns:
        Mapping of ``<property name>`` to ``<property value>``; run
        attributes appear as ``dd_tags[<key>]`` entries.
    """
    root = ElementTree.parse(source=xml_path).getroot()
    properties = root.find(path="testsuite/testcase/properties")
    assert properties is not None, f"Expected a <properties> element in the report at {xml_path}"
    raw_props = {prop.get("name"): prop.get("value") for prop in properties.findall(path="property")}
    assert raw_props, f"Expected at least one <property> element in {xml_path}"
    assert all(name is not None and value is not None for name, value in raw_props.items()), (
        f"Expected every <property> to carry a name and a value in the report at {xml_path}, got {raw_props!r}"
    )
    return {str(name): str(value) for name, value in raw_props.items()}


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


def required_attr_args(tests_dir: Path) -> list[str]:
    """Build CLI args providing every required run attribute.

    Args:
        tests_dir: Tests directory to scan.

    Returns:
        Flag list with ``--tests-dir``, all required attribute overrides
        for a report-ready (non-dry-run) run, and ``--junit-output``
        pointing at the deterministic path returned by
        :func:`junit_report_path`. The team is derived from the tests
        directory, not passed as a flag.
    """
    args = [
        "--tests-dir",
        str(tests_dir),
        "--junit-output",
        str(junit_report_path(tests_dir=tests_dir)),
    ]
    args.extend([
        "--bundle",
        "v4.22.0",
        "--ocp-version",
        "4.22.0",
        "--cnv-version",
        "4.22",
        "--owner",
        "tester@redhat.com",
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
        ``tests/network/test_manual_multi.py::test_manual_<n>``.
    """
    tests_dir = tmp_path / "tests" / "network"
    tests_dir.mkdir(parents=True)
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
        ``tests/network/test_manual_minimal.py::test_minimal``.
    """
    tests_dir = tmp_path / "tests" / "network"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_manual_minimal.py").write_text(
        data=MINIMAL_MANUAL_TEST_SOURCE,
        encoding="utf-8",
    )
    return tests_dir


def write_config_file(tmp_path: Path, content: str) -> Path:
    """Write a reporter config file.

    Args:
        tmp_path: Pytest tmp_path the file is created under.
        content: Config file content.

    Returns:
        Path to the written config file.
    """
    config_path = tmp_path / "config.yaml"
    config_path.write_text(data=content, encoding="utf-8")
    return config_path


def write_minimal_batch(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal tests dir and a batch file with one passing result.

    Args:
        tmp_path: Pytest tmp_path the files are created under.

    Returns:
        Tuple of (tests_dir, batch_path). The batch contains a single
        passing result for the minimal manual test node ID.
    """
    tests_dir = write_minimal_tests_dir(tmp_path=tmp_path)
    batch_path = tmp_path / "batch.yaml"
    batch_path.write_text(
        data=("results:\n  - test: tests/network/test_manual_minimal.py::test_minimal\n    status: passed\n"),
        encoding="utf-8",
    )
    return tests_dir, batch_path
