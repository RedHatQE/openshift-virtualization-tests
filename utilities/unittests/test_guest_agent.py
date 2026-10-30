"""Unit tests for shared QEMU guest-agent helpers."""

from pytest import mark, raises

from utilities.guest_agent import guest_agent_version_parser


@mark.unit
class TestGuestAgentVersionParser:
    """Test cases for guest_agent_version_parser function."""

    def test_guest_agent_version_parser_standard_format(self) -> None:
        """Test parsing of standard version format."""
        result = guest_agent_version_parser(version_string="7.4.0")
        assert result == "7.4.0", "Standard guest agent version was not preserved"

    def test_guest_agent_version_parser_with_extra_info(self) -> None:
        """Test parsing of version with extra information."""
        result = guest_agent_version_parser(version_string="7.4.0-1.el8")
        assert result == "7.4.0-1", (
            "Guest agent version should retain the release number and omit the distribution suffix"
        )

    def test_guest_agent_version_parser_four_part_version(self) -> None:
        """Test parsing of four-part version."""
        result = guest_agent_version_parser(version_string="100.0.0.0")
        assert result == "100.0.0.0", "Four-part guest agent version was not preserved"

    def test_guest_agent_version_parser_invalid_format(self) -> None:
        """Test parsing of invalid format."""
        with raises(AttributeError):
            guest_agent_version_parser(version_string="invalid")
