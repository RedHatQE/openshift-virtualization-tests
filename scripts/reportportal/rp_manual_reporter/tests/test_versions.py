"""Tests for the shared CNV version parsing helper."""

from __future__ import annotations

import pytest

from scripts.reportportal.rp_manual_reporter.versions import cnv_xy_version_from_version_string


class TestCnvXyVersionFromVersionString:
    """Verify major.minor derivation covers both caller shapes and malformed input."""

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("4.22.0", "4.22"),
            ("v4.22.0.rhel9-102", "4.22"),
            ("V4.22.0", "4.22"),
            ("  4.22.0  ", "4.22"),
            (" v4.22.0 ", "4.22"),
            ("4.22", "4.22"),
        ],
    )
    def test_derives_xy_version(self, version: str, expected: str) -> None:
        """Verify accepted inputs yield the major.minor portion."""
        assert cnv_xy_version_from_version_string(version=version) == expected, (
            f"Expected {expected!r} derived from {version!r}"
        )

    @pytest.mark.parametrize(
        "version",
        ["", "   ", "4", "4.", ".22", "v", "v.", "foo.bar", "version.2", "\u0664.\u0662\u0662"],
    )
    def test_returns_none_without_usable_xy_pair(self, version: str) -> None:
        """Verify inputs lacking a usable major.minor pair yield None."""
        assert cnv_xy_version_from_version_string(version=version) is None, f"Expected None derived from {version!r}"
