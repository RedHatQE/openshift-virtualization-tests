# Co-authored-by: Claude <noreply@anthropic.com>
"""Test utilities for rp_manual_reporter collector tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.reportportal.rp_manual_reporter.collector import PlaceholderTestDetail
from scripts.reportportal.rp_utils.naming import node_id_to_rp_name


@dataclass
class MockPlaceholderClass:
    """Mock of PlaceholderClass from std_placeholder_stats."""

    name: str
    test_methods: list[str] = field(default_factory=list)
    disabled_methods: list[str] = field(default_factory=list)


@dataclass
class MockPlaceholderFile:
    """Mock of PlaceholderFile from std_placeholder_stats."""

    file_path: str
    classes: list[MockPlaceholderClass] = field(default_factory=list)
    standalone_tests: list[str] = field(default_factory=list)
    disabled_standalone_tests: list[str] = field(default_factory=list)


def make_detail(
    node_id: str = "tests/net/test_a.py::TestA::test_one",
    module_markers: list[str] | None = None,
    class_markers: list[str] | None = None,
    test_markers: list[str] | None = None,
) -> PlaceholderTestDetail:
    """Create a PlaceholderTestDetail with minimal fields for testing."""
    return PlaceholderTestDetail(
        file_path="tests/net/test_a.py",
        class_name="TestA",
        method_name="test_one",
        node_id=node_id,
        rp_name=node_id_to_rp_name(node_id=node_id),
        module_markers=module_markers or [],
        class_markers=class_markers or [],
        test_markers=test_markers or [],
    )
