# Co-authored-by: Claude <noreply@anthropic.com>
"""Shared naming utilities for ReportPortal tools.

Provides conversion between pytest node IDs and ReportPortal item names.
"""

from __future__ import annotations


def node_id_to_rp_name(node_id: str) -> str:
    """Convert a pytest node ID to ReportPortal dotted name format.

    Transforms path separators and pytest delimiters into dots while
    preserving parametrize suffixes.

    Args:
        node_id: Pytest-style node ID, e.g.
            ``tests/foo/test_bar.py::TestClass::test_method[param]``.

    Returns:
        Dotted ReportPortal name, e.g.
            ``tests.foo.test_bar.TestClass.test_method[param]``.
    """
    param_suffix = ""
    base = node_id
    bracket_index = node_id.find("[")
    if bracket_index != -1:
        param_suffix = node_id[bracket_index:]
        base = node_id[:bracket_index]

    # Remove .py from the module path (before the first ::)
    # Using split/join to target only the file path portion
    parts = base.split("::")
    parts[0] = parts[0].removesuffix(".py")
    base = ".".join(parts)
    base = base.replace("/", ".")

    return base + param_suffix
