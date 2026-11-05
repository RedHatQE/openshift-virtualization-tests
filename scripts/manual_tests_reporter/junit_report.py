# Co-authored-by: Claude <noreply@anthropic.com>
"""JUnit XML report builder for manual test results.

Builds a JUnit XML report from collected manual test verdicts. The report
carries every run attribute and the failure classification as
``dd_tags[...]`` properties, so a later ``datadog-ci junit upload`` of this
file reproduces the same Datadog tags the Jenkins
``datadog-upload-results`` pipeline sets — without this tool pushing to
Datadog itself.

Note: durations are not tracked for manual verdicts, so every suite and
testcase intentionally reports ``time="0"``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast, get_args
from xml.etree import ElementTree

from simple_logger.logger import get_logger

LOGGER = get_logger(name=__name__)

# Characters illegal in XML 1.0 (control chars other than tab/newline/CR),
# plus lone surrogates and the two noncharacters — none of them are
# encodable as UTF-8, so leaving them in turns the file write into a
# UnicodeEncodeError at the very end of a session.
_ILLEGAL_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")

# Datadog tag keys/values allow alphanumerics and _ . : / @ + -; anything
# else (spaces, quotes, backslashes...) makes datadog-ci reject or mangle
# the tag. The Jenkins upload pipeline sanitizes its tag values the same
# way (replacing illegal characters with underscores).
_ILLEGAL_TAG_CHARS = re.compile(r"[^A-Za-z0-9_.:/@+\-]")

# Verdict status type for a manual test result — single source of truth
Status = Literal["PASSED", "FAILED", "SKIPPED"]

# Valid verdict statuses for a manual test result, derived from Status
VALID_STATUSES = frozenset(get_args(Status))


@dataclass
class ManualTestResult:
    """Verdict for a single manual test.

    Attributes:
        test: Pytest-style node ID of the test.
        status: Verdict — ``PASSED``, ``FAILED`` or ``SKIPPED``.
        comment: Optional tester comment.
        issue_type_label: Defect classification label for failures.
    """

    test: str
    status: Status
    comment: str = ""
    issue_type_label: str | None = None


def coerce_status(value: str) -> Status:
    """Narrow a status string to the ``Status`` literal type.

    Args:
        value: Status string, e.g. ``"PASSED"``.

    Returns:
        The value narrowed to ``Status``.

    Raises:
        ValueError: If the value is not one of ``VALID_STATUSES``.
    """
    if value not in VALID_STATUSES:
        raise ValueError(f"Invalid status {value!r}. Must be one of: {', '.join(sorted(VALID_STATUSES))}")
    return cast(Status, value)


# Defect label -> ``tfa.classification`` value. The vocabulary is RootCoz's,
# so a manual failure lands in the same Datadog facet buckets as an analysed
# CI failure. Source of truth: rootcoz ``models.py`` (``OverrideClassification
# Literal = Literal["CODE ISSUE", "PRODUCT BUG", "INFRASTRUCTURE"]`` plus
# ``_UNKNOWN_CLASSIFICATION``), rendered by ``exporters/datadog.py``'s
# ``_tag_label()`` which lowercases and folds spaces/hyphens to underscores —
# hence ``product_bug``/``code_issue``/``infrastructure``/``unknown``.
#
# "To Investigate" and "No Defect" have no RootCoz counterpart (RootCoz only
# sees failures that were classified as defects at all), so both fold to
# ``unknown``; the tester's original label is preserved on <failure type>.
CLASSIFICATION_BY_DEFECT_LABEL: dict[str, str] = {
    "Product Bug": "product_bug",
    "Automation Bug": "code_issue",
    "System Issue": "infrastructure",
    "To Investigate": "unknown",
    "No Defect": "unknown",
}

# Classification used when a failure carries no (or an unknown) defect label.
_DEFAULT_CLASSIFICATION = "unknown"

# Ordered defect labels offered by the interactive CLI. Declared here, next to
# the classification map above, so the vocabulary has a single home; the CLI
# only adds the numeric chooser keys.
DEFECT_LABELS: tuple[str, ...] = tuple(CLASSIFICATION_BY_DEFECT_LABEL)

# Defect label used when a failure carries none. Shared with the CLI's
# summary so the two cannot drift.
UNCLASSIFIED_LABEL = "Unclassified"


def classification_for_issue_type(issue_type_label: str | None) -> str:
    """Map a defect label to its ``tfa.classification`` tag value.

    Args:
        issue_type_label: Defect label chosen for the failure, e.g.
            ``"Product Bug"``; None when the tester gave no classification.

    Returns:
        The RootCoz classification tag value (e.g. ``"product_bug"``), or
        ``"unknown"`` when the label is absent or unrecognized.
    """
    return CLASSIFICATION_BY_DEFECT_LABEL.get(issue_type_label or "", _DEFAULT_CLASSIFICATION)


def _dd_tag_property(parent: ElementTree.Element, key: str, value: str) -> None:
    """Append a Datadog-ingestible tag property.

    Datadog only ingests ``<property name="dd_tags[key]">``; a plain-named
    property ships in the XML but is dropped on upload.

    Args:
        parent: ``<properties>`` element to append to.
        key: Tag key, e.g. ``"team"``.
        value: Tag value, e.g. ``"NETWORK"``.
    """
    ElementTree.SubElement(
        parent,
        "property",
        attrib={
            "name": f"dd_tags[{_sanitize_tag_text(text=key)}]",
            "value": _sanitize_tag_text(text=value),
        },
    )


def _sanitize_xml_text(text: str) -> str:
    """Remove characters that are illegal in XML 1.0.

    Args:
        text: User-supplied text destined for an XML attribute or body.

    Returns:
        The text with illegal control characters removed.
    """
    return _ILLEGAL_XML_CHARS.sub(repl="", string=text)


def _sanitize_tag_text(text: str) -> str:
    """Sanitize a value destined for a ``dd_tags[...]`` property.

    Datadog rejects or mangles tags containing characters outside its
    allowed set, so XML-illegal control characters are removed first and
    every character Datadog forbids in a tag becomes ``_``.

    Args:
        text: User-supplied tag key or value.

    Returns:
        The sanitized, tag-legal text.
    """
    return _ILLEGAL_TAG_CHARS.sub(repl="_", string=_sanitize_xml_text(text=text))


def _node_id_to_classname_and_name(node_id: str) -> tuple[str, str]:
    """Split a pytest node ID the way pytest's own junitxml plugin does.

    datadog-ci derives the test identity (full name, suite, module) from
    ``classname`` + ``name``, so the values must match what ``pytest
    --junitxml`` writes for the same node — otherwise a manual result lands
    on a different Datadog test than the identical CI run. pytest converts
    the module path to dots, drops the ``.py`` suffix and appends the class
    with ``.``, keeping any ``[param]`` id on the test name.

    Args:
        node_id: Pytest-style node ID, e.g.
            ``tests/foo/test_bar.py::TestClass::test_method[param]``.

    Returns:
        A tuple of (classname, name), e.g.
        ``("tests.foo.test_bar.TestClass", "test_method[param]")``.
        For a standalone test the classname is the dotted module path.
    """
    path_part, separator, scopes = node_id.partition("::")
    if not separator:
        return node_id, node_id
    module_path = path_part.removesuffix(".py").replace("/", ".")
    *class_names, name = scopes.split("::")
    if class_names:
        module_path = ".".join([module_path, *class_names])
    return module_path, name


def build_junit_xml(
    results: list[ManualTestResult],
    suite_name: str,
    attributes: list[dict[str, str]],
    polarion_lookup: dict[str, str] | None = None,
    description: str = "",
) -> str:
    """Build a JUnit XML report from manual test results.

    Args:
        results: List of test verdicts.
        suite_name: Name for the testsuite element.
        attributes: Run attributes, each emitted on every testcase as a
            ``dd_tags[<lower-cased key>]`` property (the only property-name
            form Datadog ingests into tags). Failed testcases additionally
            get ``dd_tags[tfa.classification]``.
        polarion_lookup: Optional node_id → Polarion ID mapping; matching
            tests get a ``dd_tags[polarion-testcase-id]`` property.
        description: Suite-level description.

    Returns:
        The JUnit XML document as a string.
    """
    polarion_lookup = polarion_lookup or {}
    passed_count = sum(1 for result in results if result.status == "PASSED")
    failed_count = sum(1 for result in results if result.status == "FAILED")
    skipped_count = sum(1 for result in results if result.status == "SKIPPED")

    root = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(
        root,
        "testsuite",
        attrib={
            "name": _sanitize_xml_text(text=suite_name),
            "tests": str(len(results)),
            "failures": str(failed_count),
            "errors": "0",
            "skipped": str(skipped_count),
            "time": "0",
            "timestamp": datetime.now(tz=UTC).isoformat(),
        },
    )
    if description:
        suite.set("description", _sanitize_xml_text(text=description))

    for result in results:
        classname, name = _node_id_to_classname_and_name(node_id=result.test)
        testcase = ElementTree.SubElement(
            suite,
            "testcase",
            attrib={
                "classname": _sanitize_xml_text(text=classname),
                "name": _sanitize_xml_text(text=name),
                "time": "0",
            },
        )

        properties = ElementTree.SubElement(testcase, "properties")
        for attr in attributes:
            _dd_tag_property(parent=properties, key=attr["key"].lower(), value=attr["value"])
        if result.status == "FAILED":
            # The classification is a first-class tag, not merely the
            # <failure> element's type attribute: the dashboards bucket
            # failures by tfa.classification.
            _dd_tag_property(
                parent=properties,
                key="tfa.classification",
                value=classification_for_issue_type(issue_type_label=result.issue_type_label),
            )
        polarion_id = polarion_lookup.get(result.test)
        if polarion_id:
            _dd_tag_property(parent=properties, key="polarion-testcase-id", value=polarion_id)

        if result.status == "FAILED":
            defect_label = result.issue_type_label or UNCLASSIFIED_LABEL
            failure = ElementTree.SubElement(
                testcase,
                "failure",
                attrib={
                    "type": _sanitize_xml_text(text=defect_label),
                    "message": _sanitize_xml_text(text=result.comment),
                },
            )
            failure.text = _sanitize_xml_text(text=f"{defect_label}: {result.comment}")
        elif result.status == "SKIPPED":
            ElementTree.SubElement(
                testcase,
                "skipped",
                attrib={"message": _sanitize_xml_text(text=result.comment)},
            )

    LOGGER.info(
        f"Built JUnit report '{suite_name}': {passed_count} passed, {failed_count} failed, {skipped_count} skipped"
    )
    ElementTree.indent(tree=root, space="  ")
    return ElementTree.tostring(element=root, encoding="unicode")


def write_junit_report(xml_path: Path, xml_content: str) -> None:
    """Write a JUnit XML document to disk atomically.

    The document is written to a sibling ``.partial`` file and then renamed
    onto the destination, so an interrupted or failing write never leaves a
    truncated report at the final path. Writing through a symlink is
    refused: the destination is a well-known name in the current directory,
    and following a link would overwrite whatever it points at.

    Args:
        xml_path: Destination file path.
        xml_content: JUnit XML document string.

    Raises:
        OSError: The destination is a symlink, or the write/rename failed.
    """
    if xml_path.is_symlink():
        raise OSError(f"Refusing to write the report through the symlink {xml_path}")
    # Per-process sibling: two runs writing the same destination must not
    # interleave on one scratch file (the retry writer uses microsecond stamps
    # for the same reason). The symlink check covers it too — a symlinked
    # scratch file would be written through just like a symlinked destination.
    partial_path = xml_path.with_name(f"{xml_path.name}.{os.getpid()}.partial")
    if partial_path.is_symlink():
        raise OSError(f"Refusing to write the report through the symlink {partial_path}")
    try:
        partial_path.write_text(data=xml_content, encoding="utf-8")
        os.replace(src=partial_path, dst=xml_path)
    finally:
        partial_path.unlink(missing_ok=True)
    LOGGER.info(f"Wrote JUnit report to {xml_path}")
