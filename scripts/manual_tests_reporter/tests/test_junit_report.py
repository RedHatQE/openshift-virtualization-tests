# Co-authored-by: Claude <noreply@anthropic.com>
"""Tests for scripts.manual_tests_reporter.junit_report module.

See scripts/manual_tests_reporter/README.md for the tool this module belongs to.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import fromstring

import pytest

from scripts.manual_tests_reporter.junit_report import (
    CLASSIFICATION_BY_DEFECT_LABEL,
    VALID_STATUSES,
    ManualTestResult,
    _node_id_to_classname_and_name,
    build_junit_xml,
    classification_for_issue_type,
    coerce_status,
    write_junit_report,
)
from scripts.manual_tests_reporter.manual_tests_reporter import _DEFECT_TYPES


class TestCoerceStatus:
    def test_valid_status_returned(self) -> None:
        """Verify a valid status is returned narrowed to the Status type."""
        result = coerce_status(value="PASSED")
        assert result == "PASSED", f"Expected 'PASSED', got {result!r}"

    def test_invalid_status_raises(self) -> None:
        """Verify an unrecognized status raises ValueError."""
        with pytest.raises(expected_exception=ValueError, match="Invalid status"):
            coerce_status(value="maybe")

    def test_valid_statuses_derived_from_status_literal(self) -> None:
        """Verify VALID_STATUSES stays in sync with the Status literal (single source of truth)."""
        assert VALID_STATUSES == {"PASSED", "FAILED", "SKIPPED"}, (
            f"Expected the Status literal and VALID_STATUSES to define the same statuses, got {VALID_STATUSES!r}"
        )


class TestNodeIdToClassnameAndName:
    @pytest.mark.parametrize(
        ("node_id", "expected"),
        [
            # Values verified against `pytest --junitxml` output: dots, no .py,
            # class appended with '.', param ids kept on the name.
            ("tests/foo/test_bar.py::TestClass::test_method", ("tests.foo.test_bar.TestClass", "test_method")),
            ("tests/foo/test_bar.py::test_func", ("tests.foo.test_bar", "test_func")),
            ("tests/foo/test_bar.py::TestClass::test_param[1]", ("tests.foo.test_bar.TestClass", "test_param[1]")),
            (
                "tests/foo/test_bar.py::TestClass::Nested::test_deep",
                ("tests.foo.test_bar.TestClass.Nested", "test_deep"),
            ),
        ],
    )
    def test_matches_pytest_junitxml_format(self, node_id: str, expected: tuple[str, str]) -> None:
        """Verify classname/name match what pytest's junitxml writes."""
        result = _node_id_to_classname_and_name(node_id=node_id)
        assert result == expected, f"Expected {expected!r} for {node_id!r}, got {result!r}"


class TestClassificationForIssueType:
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("Product Bug", "product_bug"),
            ("Automation Bug", "code_issue"),
            ("System Issue", "infrastructure"),
            ("To Investigate", "unknown"),
            ("No Defect", "unknown"),
            (None, "unknown"),
            ("Not A Real Label", "unknown"),
        ],
    )
    def test_maps_defect_label_to_rootcoz_classification(self, label: str | None, expected: str) -> None:
        """Verify every defect label maps into the RootCoz classification vocabulary."""
        result = classification_for_issue_type(issue_type_label=label)
        assert result == expected, f"Expected {expected!r} for {label!r}, got {result!r}"

    def test_every_cli_defect_label_is_classified(self) -> None:
        """Verify every interactive defect choice has a classification mapping.

        The CLI owns the label text and this module owns the label ->
        classification map; an unmapped label would silently bucket its
        failures as unknown on the dashboards.
        """
        unmapped = sorted(set(_DEFECT_TYPES.values()) - set(CLASSIFICATION_BY_DEFECT_LABEL))
        assert not unmapped, f"Defect labels with no classification mapping: {unmapped}"

    def test_vocabulary_is_the_dashboard_vocabulary(self) -> None:
        """Verify the mapping only emits values the failure dashboards filter on."""
        allowed = {"product_bug", "code_issue", "infrastructure", "unknown"}
        emitted = set(CLASSIFICATION_BY_DEFECT_LABEL.values())
        assert emitted <= allowed, f"Unexpected classification values: {emitted - allowed}"


class TestBuildJunitXml:
    def test_pass_fail_skip_structure(self) -> None:
        """Verify XML structure for passed, failed, and skipped results."""
        results = [
            ManualTestResult(test="tests/net/test_a.py::TestA::test_pass", status="PASSED"),
            ManualTestResult(
                test="tests/net/test_a.py::TestA::test_fail",
                status="FAILED",
                comment="boom",
                issue_type_label="Product Bug",
            ),
            ManualTestResult(test="tests/net/test_a.py::TestA::test_skip", status="SKIPPED"),
        ]
        xml_content = build_junit_xml(
            results=results,
            suite_name="Manual - NETWORK",
            attributes=[{"key": "TEAM", "value": "NETWORK"}],
        )
        root = fromstring(text=xml_content)
        suite = root.find("testsuite")
        assert suite is not None, f"Expected a <testsuite> element, got:\n{xml_content}"
        assert suite.get("name") == "Manual - NETWORK", f"Expected 'Manual - NETWORK', got {suite.get('name')!r}"
        assert suite.get("tests") == "3", f"Expected '3', got {suite.get('tests')!r}"
        assert suite.get("failures") == "1", f"Expected '1', got {suite.get('failures')!r}"
        assert suite.get("skipped") == "1", f"Expected '1', got {suite.get('skipped')!r}"

        testcases = suite.findall("testcase")
        assert len(testcases) == 3, f"Expected 3, got {len(testcases)!r}"

        passed, failed, skipped = testcases
        assert passed.get("name") == "test_pass", f"Expected 'test_pass', got {passed.get('name')!r}"
        assert passed.find("failure") is None, f"Expected no <failure> on a PASSED testcase, got:\n{xml_content}"

        failure = failed.find("failure")
        assert failure is not None, f"Expected a <failure> element on the FAILED testcase, got:\n{xml_content}"
        assert failure.get("type") == "Product Bug", f"Expected 'Product Bug', got {failure.get('type')!r}"
        assert failure.get("message") == "boom", f"Expected 'boom', got {failure.get('message')!r}"

        assert skipped.find("skipped") is not None, (
            f"Expected a <skipped> element on the SKIPPED testcase, got:\n{xml_content}"
        )

    def test_properties_included(self) -> None:
        """Verify run attributes and Polarion ID become testcase properties."""
        results = [ManualTestResult(test="tests/net/test_a.py::TestA::test_one", status="PASSED")]
        xml_content = build_junit_xml(
            results=results,
            suite_name="Manual - NETWORK",
            attributes=[{"key": "TEAM", "value": "NETWORK"}],
            polarion_lookup={"tests/net/test_a.py::TestA::test_one": "MOCK-1234"},
        )
        root = fromstring(text=xml_content)
        suite = root.find("testsuite")
        assert suite is not None, "Expected: run attributes and Polarion ID become testcase properties"
        testcase = suite.find("testcase")
        assert testcase is not None, "Expected: run attributes and Polarion ID become testcase properties"
        properties = testcase.find("properties")
        assert properties is not None, "Expected: run attributes and Polarion ID become testcase properties"
        props = {prop.get("name"): prop.get("value") for prop in properties.findall("property")}
        assert props["dd_tags[team]"] == "NETWORK", f"Expected 'NETWORK', got {props.get('dd_tags[team]')!r}"
        assert props["dd_tags[polarion-testcase-id]"] == "MOCK-1234", (
            f"Expected 'MOCK-1234', got {props['dd_tags[polarion-testcase-id]']!r}"
        )

    def test_classname_split(self) -> None:
        """Verify classname and name are split from the node ID."""
        results = [ManualTestResult(test="tests/net/test_a.py::TestA::test_one", status="PASSED")]
        xml_content = build_junit_xml(results=results, suite_name="s", attributes=[])
        root = fromstring(text=xml_content)
        suite = root.find("testsuite")
        assert suite is not None, "Expected: classname and name are split from the node ID"
        testcase = suite.find("testcase")
        assert testcase is not None, "Expected: classname and name are split from the node ID"
        assert testcase.get("classname") == "tests.net.test_a.TestA", (
            f"Expected pytest's dotted classname 'tests.net.test_a.TestA', got {testcase.get('classname')!r}"
        )
        assert testcase.get("name") == "test_one", f"Expected 'test_one', got {testcase.get('name')!r}"

    def test_run_attributes_are_datadog_ingestible_tags(self) -> None:
        """Verify every run attribute is a dd_tags[...] property.

        Datadog drops plain-named properties on upload, so only the
        dd_tags[...] form survives into tags.
        """
        attributes = [
            {"key": "job_name", "value": "manual-tests-network"},
            {"key": "build_number", "value": "1762268400"},
            {"key": "team", "value": "NETWORK"},
            {"key": "manual", "value": "true"},
            {"key": "rootcoz.url", "value": "https://rootcoz.example/run/1"},
        ]
        xml_content = build_junit_xml(
            results=[ManualTestResult(test="tests/net/test_a.py::TestA::test_one", status="PASSED")],
            suite_name="pytest",
            attributes=attributes,
        )
        root = fromstring(text=xml_content)
        testcase = root.find("testsuite").find("testcase")
        props = {prop.get("name"): prop.get("value") for prop in testcase.find("properties").findall("property")}
        assert props == {
            "dd_tags[job_name]": "manual-tests-network",
            "dd_tags[build_number]": "1762268400",
            "dd_tags[team]": "NETWORK",
            "dd_tags[manual]": "true",
            "dd_tags[rootcoz.url]": "https://rootcoz.example/run/1",
        }, f"Unexpected properties: {props!r}"

    def test_failed_test_carries_classification_tag(self) -> None:
        """Verify a failed testcase carries tfa.classification alongside <failure>."""
        results = [
            ManualTestResult(
                test="tests/net/test_a.py::TestA::test_fail",
                status="FAILED",
                comment="boom",
                issue_type_label="System Issue",
            )
        ]
        xml_content = build_junit_xml(results=results, suite_name="pytest", attributes=[])
        testcase = fromstring(text=xml_content).find("testsuite").find("testcase")
        props = {prop.get("name"): prop.get("value") for prop in testcase.find("properties").findall("property")}
        assert props["dd_tags[tfa.classification]"] == "infrastructure", (
            f"Expected 'infrastructure', got {props.get('dd_tags[tfa.classification]')!r}"
        )
        assert testcase.find("failure").get("type") == "System Issue", "Expected the defect label kept on <failure>"

    def test_passing_test_carries_no_classification_tag(self) -> None:
        """Verify only failures get a classification tag."""
        results = [ManualTestResult(test="tests/net/test_a.py::TestA::test_one", status="PASSED")]
        xml_content = build_junit_xml(results=results, suite_name="pytest", attributes=[])
        testcase = fromstring(text=xml_content).find("testsuite").find("testcase")
        props = {prop.get("name") for prop in testcase.find("properties").findall("property")}
        assert "dd_tags[tfa.classification]" not in props, f"Unexpected classification tag: {props!r}"

    def test_unclassified_failure_defaults_to_unknown(self) -> None:
        """Verify a failure with no defect label is classified as unknown."""
        results = [ManualTestResult(test="tests/net/test_a.py::TestA::test_fail", status="FAILED")]
        xml_content = build_junit_xml(results=results, suite_name="pytest", attributes=[])
        testcase = fromstring(text=xml_content).find("testsuite").find("testcase")
        props = {prop.get("name"): prop.get("value") for prop in testcase.find("properties").findall("property")}
        assert props["dd_tags[tfa.classification]"] == "unknown", (
            f"Expected 'unknown', got {props.get('dd_tags[tfa.classification]')!r}"
        )


class TestWriteJunitReport:
    def test_write_is_atomic_and_leaves_no_partial(self, tmp_path: Path) -> None:
        """Verify a successful write leaves only the report, no .partial sibling."""
        xml_path = tmp_path / "report.xml"
        write_junit_report(xml_path=xml_path, xml_content="<testsuites/>")

        assert xml_path.read_text(encoding="utf-8") == "<testsuites/>", "Expected the report content written"
        assert not list(tmp_path.glob("*.partial")), "Expected no leftover .partial file after a successful write"

    def test_write_refuses_symlink_destination(self, tmp_path: Path) -> None:
        """Verify the writer never overwrites a symlink's target."""
        victim = tmp_path / "victim.txt"
        victim.write_text(data="original", encoding="utf-8")
        link = tmp_path / "report.xml"
        link.symlink_to(target=victim)

        with pytest.raises(expected_exception=OSError, match="symlink"):
            write_junit_report(xml_path=link, xml_content="<testsuites/>")

        assert victim.read_text(encoding="utf-8") == "original", "Expected the symlink target left untouched"

    def test_lone_surrogate_stripped(self) -> None:
        """Verify a lone surrogate cannot reach the file write.

        A YAML escape such as "\\ud800" produces a string that is not
        UTF-8 encodable; it must be stripped during sanitisation instead of
        failing the report write.
        """
        results = [
            ManualTestResult(
                test="tests/net/test_a.py::TestA::test_fail",
                status="FAILED",
                comment="boom \ud800",
                issue_type_label="Product Bug",
            )
        ]
        xml_content = build_junit_xml(results=results, suite_name="pytest", attributes=[])

        xml_content.encode(encoding="utf-8")  # must not raise
        assert "\ud800" not in xml_content, "Expected the lone surrogate removed from the report"

    def test_write_junit_report(self, tmp_path: Path) -> None:
        """Verify XML content is written to disk."""
        xml_path = tmp_path / "report.xml"
        write_junit_report(xml_path=xml_path, xml_content="<testsuites/>")
        assert xml_path.read_text(encoding="utf-8") == "<testsuites/>", (
            f"Expected '<testsuites/>', got {xml_path.read_text(encoding='utf-8')!r}"
        )


class TestSanitizeXmlText:
    def test_control_characters_removed(self) -> None:
        """Verify illegal XML control characters are stripped from comments."""
        results = [
            ManualTestResult(test="tests/net/test_a.py::TestA::test_fail", status="FAILED", comment="boom\x01\x02"),
        ]
        xml_content = build_junit_xml(results=results, suite_name="s", attributes=[])
        root = fromstring(text=xml_content)
        suite = root.find("testsuite")
        assert suite is not None, "Expected: illegal XML control characters are stripped from comments"
        testcase = suite.find("testcase")
        assert testcase is not None, "Expected: illegal XML control characters are stripped from comments"
        failure = testcase.find("failure")
        assert failure is not None, "Expected: illegal XML control characters are stripped from comments"
        assert failure.get("message") == "boom", f"Expected 'boom', got {failure.get('message')!r}"


class TestSuiteNameSanitized:
    def test_suite_name_control_chars_removed(self) -> None:
        """Verify control characters in suite_name are stripped."""
        results = [ManualTestResult(test="tests/net/test_a.py::TestA::test_one", status="PASSED")]
        xml_content = build_junit_xml(
            results=results,
            suite_name="Manual - NET\x01WORK",
            attributes=[{"key": "TE\x02AM", "value": "NETWORK"}],
        )
        root = fromstring(text=xml_content)
        suite = root.find("testsuite")
        assert suite is not None, "Expected: suite name sanitized"
        assert suite.get("name") == "Manual - NETWORK", "Expected: suite name sanitized"
        testcase = suite.find("testcase")
        assert testcase is not None, "Expected: property key sanitized"
        properties = testcase.find("properties")
        assert properties is not None, "Expected: property key sanitized"
        prop = properties.find("property")
        assert prop is not None, "Expected: property key sanitized"
        assert prop.get("name") == "dd_tags[team]", "Expected: property key sanitized into a dd_tags property"
