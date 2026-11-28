"""Unit tests for shared QEMU guest-agent helpers."""

from pytest import mark, raises

from utilities.guest_agent import guest_agent_version_parser


@mark.unit
class TestGuestAgentVersionParser:
    @mark.parametrize(
        "version_string,expected,message",
        [
            ("7.4.0", "7.4.0", "Standard guest agent version was not preserved"),
            ("7.4.0-1.el8", "7.4.0-1", "Release number or distribution suffix was parsed incorrectly"),
            ("100.0.0.0", "100.0.0.0", "Four-part guest agent version was not preserved"),
            ("7.4.0.12", "7.4.0.12", "Dot-separated build number was not preserved"),
            ("7.4.0-12", "7.4.0-12", "Hyphen-separated build number was not preserved"),
            ("7.4.0|12", "7.4.0", "Pipe must not be included as a build separator"),
            ("qemu-guest-agent-9.1.0-4.el9.x86_64", "9.1.0-4", "Linux RPM version was parsed incorrectly"),
        ],
    )
    def test_parses_supported_version(self, version_string: str, expected: str, message: str) -> None:
        assert guest_agent_version_parser(version_string=version_string) == expected, message

    @mark.parametrize("version_string", ["invalid", ""])
    def test_rejects_invalid_format(self, version_string: str) -> None:
        with raises(ValueError, match="No supported QEMU guest-agent version found"):
            guest_agent_version_parser(version_string=version_string)
