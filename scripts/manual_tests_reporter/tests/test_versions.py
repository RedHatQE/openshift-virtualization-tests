"""Tests for the shared CNV version-string derivation."""

from __future__ import annotations

from scripts.manual_tests_reporter.versions import cnv_versions_from_version_string


class TestCnvVersionsFromVersionString:
    def test_bundle_string(self) -> None:
        """Verify a bundle string derives both versions."""
        result = cnv_versions_from_version_string(version_string="v4.22.0.rhel9-102")
        assert result == ("4.22.0", "4.22"), f"Expected ('4.22.0', '4.22'), got {result!r}"

    def test_plain_hco_version(self) -> None:
        """Verify a plain HCO version string derives both versions."""
        result = cnv_versions_from_version_string(version_string="4.22.0")
        assert result == ("4.22.0", "4.22"), f"Expected ('4.22.0', '4.22'), got {result!r}"

    def test_two_part_string(self) -> None:
        """Verify a major.minor string derives only the X.Y version."""
        result = cnv_versions_from_version_string(version_string="4.22")
        assert result == (None, "4.22"), f"Expected (None, '4.22'), got {result!r}"

    def test_double_v_prefix_bundle_string(self) -> None:
        """Verify a double-v-prefixed bundle string derives both versions.

        All leading ``v`` characters are stripped (matching the historical
        CLI-path behavior), so a typo'd double prefix still derives valid
        versions instead of garbage tags.
        """
        result = cnv_versions_from_version_string(version_string="vv4.22.0.rhel9-102")
        assert result == ("4.22.0", "4.22"), f"Expected ('4.22.0', '4.22'), got {result!r}"

    def test_whitespace_padded_bundle_string(self) -> None:
        """Verify surrounding whitespace is stripped before deriving versions.

        User-typed CLI input can carry stray spaces; without stripping,
        both the space and a following ``v`` would survive into the tags.
        """
        result = cnv_versions_from_version_string(version_string=" v4.22.0 ")
        assert result == ("4.22.0", "4.22"), f"Expected ('4.22.0', '4.22'), got {result!r}"

    def test_uppercase_v_prefix_bundle_string(self) -> None:
        """Verify an uppercase-V prefix is stripped like a lowercase one."""
        result = cnv_versions_from_version_string(version_string="V4.22.0")
        assert result == ("4.22.0", "4.22"), f"Expected ('4.22.0', '4.22'), got {result!r}"

    def test_too_short_string(self) -> None:
        """Verify strings without a major.minor pair derive nothing."""
        result = cnv_versions_from_version_string(version_string="4")
        assert result == (None, None), f"Expected (None, None), got {result!r}"

    def test_empty_minor_string(self) -> None:
        """Verify a dangling separator (typo) derives nothing, not garbage tags."""
        result = cnv_versions_from_version_string(version_string="4.")
        assert result == (None, None), f"Expected (None, None), got {result!r}"

    def test_empty_string(self) -> None:
        """Verify an empty string derives nothing."""
        result = cnv_versions_from_version_string(version_string="")
        assert result == (None, None), f"Expected (None, None), got {result!r}"

    def test_empty_patch_component(self) -> None:
        """Verify a dangling patch separator derives only the X.Y version."""
        result = cnv_versions_from_version_string(version_string="v4.22.")
        assert result == (None, "4.22"), f"Expected (None, '4.22'), got {result!r}"
