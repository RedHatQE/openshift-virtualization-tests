"""Unit tests for shared Windows guest queries."""

from __future__ import annotations

import json
from base64 import b64decode
from logging import DEBUG
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from pytest import mark, raises
from rrmngmnt.ssh import RemoteExecutor
from rrmngmnt.user import User

from utilities.constants.timeouts import TCP_TIMEOUT_30SEC, TIMEOUT_1MIN
from utilities.windows import LOGGER as WINDOWS_LOGGER
from utilities.windows import (
    get_ga_version,
    get_reg_product_name,
    get_windows_os_info,
    get_windows_os_properties,
    get_windows_timezone,
    powershell_command,
    run_powershell_commands,
)

if TYPE_CHECKING:
    from pytest import LogCaptureFixture


@mark.unit
class TestGetWindowsOsProperties:
    @mark.parametrize("version", ["2019", "2022", "2025"])
    def test_reads_operating_system_properties(self, mock_vm: MagicMock, version: str) -> None:
        expected = {
            "Caption": f"Microsoft Windows Server {version} Standard",
            "CSName": "test-host",
        }
        output = json.dumps(expected)
        with patch("utilities.windows.run_ssh_commands", return_value=[output]) as remote_command:
            result = get_windows_os_properties(ssh_exec=mock_vm.ssh_exec)

        assert result == expected, "CIM properties were not preserved"
        remote_command.assert_called_once_with(
            host=mock_vm.ssh_exec,
            commands=powershell_command(
                script=(
                    "Get-CimInstance -Class Win32_OperatingSystem | "
                    "Select-Object CSName, BuildNumber, Caption, Version, OSArchitecture | ConvertTo-Json"
                ),
            ),
        )

    def test_rejects_invalid_json(self, mock_vm: MagicMock) -> None:
        with patch("utilities.windows.run_ssh_commands", return_value=["invalid JSON"]):
            with raises(json.JSONDecodeError):
                get_windows_os_properties(ssh_exec=mock_vm.ssh_exec)

    def test_propagates_transport_failure(self, mock_vm: MagicMock) -> None:
        with patch("utilities.windows.run_ssh_commands", side_effect=OSError("Connection reset")):
            with raises(OSError, match="Connection reset"):
                get_windows_os_properties(ssh_exec=mock_vm.ssh_exec)


@mark.unit
class TestPowerShellTransport:
    def test_encoding_preserves_shell_characters_and_unicode(self) -> None:
        script = "Write-Output 'à $secret `quoted`'"
        arguments = powershell_command(script=script)
        assert b64decode(arguments[-1]).decode("utf-16le") == script, "PowerShell encoding changed the script contents"
        assert arguments[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand"], (
            "PowerShell command must use non-interactive encoded execution without loading a profile"
        )

    @mark.parametrize("exit_status", [0, 1, 7])
    def test_real_executor_uses_short_bootstrap_and_never_logs_input_or_credentials(
        self, exit_status: int, caplog: LogCaptureFixture, mock_vm: MagicMock
    ) -> None:
        secret = "OFFLINE-SENSITIVE-INPUT"
        output = '{"result":"OFFLINE-SENSITIVE-OUTPUT àè漢字"}'.encode()
        host = MagicMock()
        executor = RemoteExecutor(user=User(name=mock_vm.username, password=mock_vm.password), address="127.0.0.1")
        host.executor.return_value = executor
        stdin, stdout, stderr = MagicMock(), MagicMock(), MagicMock()
        stdout.read.return_value = output
        stderr.read.return_value = f"Native command failed: {secret}".encode()
        stdout.channel.recv_exit_status.return_value = exit_status
        client = MagicMock()
        client.exec_command.return_value = stdin, stdout, stderr
        script = "Write-Output 'x'\n" * 1000 + f"cmd /c exit {exit_status}"
        caplog.set_level(DEBUG, logger="utilities.windows")
        # The shared fixture replaces logger handlers; capture the guest logger directly.
        with (
            patch("rrmngmnt.ssh.paramiko.SSHClient", return_value=client),
            patch.object(target=WINDOWS_LOGGER, attribute="handlers", new=[caplog.handler]),
        ):
            if exit_status:
                with raises(RuntimeError, match=f"exit status {exit_status}") as error:
                    run_powershell_commands(ssh_exec=host, script=script, input_data=secret)
                assert "Native command failed" in str(error.value), "PowerShell failure omitted stderr details"
                assert secret not in str(error.value) and "SENSITIVE-OUTPUT" not in str(error.value), (
                    "PowerShell failure exposed sensitive input or output in the exception"
                )
            else:
                assert run_powershell_commands(ssh_exec=host, script=script, input_data=secret) == output.decode(), (
                    "PowerShell runner did not return the guest output unchanged"
                )
        envelope = json.loads(stdin.write.call_args.args[0])
        assert envelope == {"script": script, "input_data": secret}, (
            "SSH stdin must contain the complete script and input data in a JSON envelope"
        )
        stdin.channel.shutdown_write.assert_called_once()
        command = client.exec_command.call_args.args[0]
        assert len(command) < 2048 and secret not in command and script not in command, (
            "SSH command must contain only a short bootstrap without the script or sensitive input"
        )
        assert secret not in caplog.text and mock_vm.password not in caplog.text, (
            "PowerShell execution logged sensitive input or the authentication password"
        )
        assert "OFFLINE-SENSITIVE-OUTPUT" not in caplog.text, "PowerShell execution logged sensitive guest output"
        assert "127.0.0.1" in caplog.text and str(TIMEOUT_1MIN) in caplog.text, (
            "PowerShell operation context was not logged"
        )
        if exit_status:
            assert "127.0.0.1" in str(error.value), "PowerShell failure omitted the guest identifier"
        client.close.assert_called_once()

    @mark.parametrize(
        "error_output,expected_details,input_data",
        [
            (b"Access is denied", "Access is denied", None),
            (b"\xff", "\ufffd", None),
            (b"", "", None),
            (
                b"Failure: sensitive-input; retry sensitive-input",
                "Failure: [REDACTED]; retry [REDACTED]",
                "sensitive-input",
            ),
            ("Failure: sègreto".encode(), "Failure: [REDACTED]", "sègreto"),
            (b"Access is denied", "Access is denied", ""),
        ],
    )
    @mark.parametrize("stdout_output", [b"", b"\xff"])
    def test_includes_error_details(
        self,
        mock_vm: MagicMock,
        error_output: bytes,
        expected_details: str,
        input_data: str | None,
        stdout_output: bytes,
    ) -> None:
        executor = mock_vm.ssh_exec.executor.return_value
        executor.address = "test-guest"
        command = executor.session.return_value.__enter__.return_value.command.return_value
        stdin, stdout, stderr = MagicMock(), MagicMock(), MagicMock()
        stdout.read.return_value = stdout_output
        stderr.read.return_value = error_output
        command.execute.return_value.__enter__.return_value = stdin, stdout, stderr
        command.rc = 1

        with raises(RuntimeError) as error:
            run_powershell_commands(ssh_exec=mock_vm.ssh_exec, script="Get-Date", input_data=input_data)

        expected_message = "PowerShell operation failed on guest test-guest (exit status 1)"
        if expected_details:
            expected_message += f": {expected_details}"
        assert str(error.value) == expected_message, "PowerShell failure details were not reported"

    @mark.parametrize(
        "stdout_output,expected_output,error_type",
        [
            (b'{"result":"ok"}', '{"result":"ok"}', None),
            (b'\xef\xbb\xbf{"result":"ok"}', '{"result":"ok"}', None),
            (b"\xff", None, UnicodeDecodeError),
        ],
    )
    def test_decodes_successful_output(
        self, mock_vm: MagicMock, stdout_output: bytes, expected_output: str | None, error_type: type[Exception] | None
    ) -> None:
        command = (
            mock_vm.ssh_exec.executor.return_value.session.return_value.__enter__.return_value.command.return_value
        )
        stdin, stdout, stderr = MagicMock(), MagicMock(), MagicMock()
        stdout.read.return_value = stdout_output
        stderr.read.return_value = b""
        command.execute.return_value.__enter__.return_value = stdin, stdout, stderr
        command.rc = 0

        if error_type:
            with raises(error_type):
                run_powershell_commands(ssh_exec=mock_vm.ssh_exec, script="Get-Date")
        else:
            result = run_powershell_commands(ssh_exec=mock_vm.ssh_exec, script="Get-Date")
            assert result == expected_output, "Successful PowerShell output was not decoded with UTF-8 BOM handling"

    def test_transport_error_propagates_and_closes_session(self) -> None:
        host = MagicMock()
        executor = host.executor.return_value
        session = executor.session.return_value.__enter__.return_value
        session.command.return_value.execute.side_effect = OSError("Connection reset")
        with raises(OSError, match="Connection reset"):
            run_powershell_commands(ssh_exec=host, script="Get-Date")
        executor.session.return_value.__exit__.assert_called_once()


@mark.unit
class TestGetWindowsTimezone:
    """Test cases for get_windows_timezone function"""

    @mark.parametrize(
        "get_standard_name,expected,script",
        [
            (False, "UTC", "Get-TimeZone"),
            (True, "StandardName: UTC", 'Get-TimeZone | findstr "StandardName"'),
        ],
    )
    @patch("utilities.windows.run_ssh_commands")
    def test_get_windows_timezone(
        self, mock_run_ssh: MagicMock, get_standard_name: bool, expected: str, script: str
    ) -> None:
        mock_ssh_exec = MagicMock()
        mock_run_ssh.return_value = [expected]
        result = get_windows_timezone(ssh_exec=mock_ssh_exec, get_standard_name=get_standard_name)
        assert result == expected, "Windows timezone should match the SSH command output"
        mock_run_ssh.assert_called_once_with(
            host=mock_ssh_exec, commands=powershell_command(script=script), tcp_timeout=TCP_TIMEOUT_30SEC
        )


@mark.unit
class TestGetGaVersion:
    """Test cases for get_ga_version function"""

    @patch("utilities.windows.run_ssh_commands")
    def test_get_ga_version_success(self, mock_run_ssh: MagicMock) -> None:
        """Test successful extraction of GA version"""
        mock_ssh_exec = MagicMock()
        mock_run_ssh.return_value = ["7.4.0  "]

        result = get_ga_version(mock_ssh_exec)

        assert result == "7.4.0", "Guest agent version should have trailing whitespace removed"
        mock_run_ssh.assert_called_once_with(
            host=mock_ssh_exec,
            commands=powershell_command(
                script="(Get-Item 'C:\\Program Files\\Qemu-ga\\qemu-ga.exe').VersionInfo.FileVersion"
            ),
            tcp_timeout=TCP_TIMEOUT_30SEC,
        )


@mark.unit
class TestGetRegProductName:
    """Test cases for get_reg_product_name function"""

    @patch("utilities.windows.run_ssh_commands")
    def test_get_reg_product_name_success(self, mock_run_ssh: MagicMock) -> None:
        """Test successful extraction of registry product name"""
        mock_ssh_exec = MagicMock()
        mock_run_ssh.return_value = ["REG_SZ    Microsoft Windows Server 2019\r\n"]

        result = get_reg_product_name(mock_ssh_exec)

        assert result == "REG_SZ    Microsoft Windows Server 2019\r\n", (
            "Windows registry product name output was not preserved"
        )
        mock_run_ssh.assert_called_once()


@mark.unit
class TestGetWindowsOsInfo:
    """Test cases for get_windows_os_info function"""

    @mark.parametrize(
        "caption,product_name,version",
        [
            ("invalid", "REG_SZ    Windows Server 2019 Standard\r\n", "10.0.19042"),
            ("2019", "REG_SZ    Windows Server 2019 Standard\r\n", "10.0.19042"),
            ("Microsoft Windows Server 2019", "invalid", "10.0.19042"),
            ("Microsoft Windows Server 2019", "REG_SZ    Windows Server 2019 Standard\r\n", "invalid"),
        ],
    )
    def test_rejects_unsupported_os_info_format(
        self, mock_vm: MagicMock, caption: str, product_name: str, version: str
    ) -> None:
        with (
            patch("utilities.windows.get_windows_os_properties", return_value={"Caption": caption, "Version": version}),
            patch("utilities.windows.get_reg_product_name", return_value=product_name),
        ):
            with raises(ValueError, match="Unsupported Windows OS version or registry product name format"):
                get_windows_os_info(ssh_exec=mock_vm.ssh_exec)

    @patch("utilities.windows.get_windows_timezone")
    @patch("utilities.windows.get_reg_product_name")
    @patch("utilities.windows.get_ga_version")
    @patch("utilities.windows.get_windows_os_properties")
    @patch("utilities.windows.guest_agent_version_parser")
    def test_get_windows_os_info_success(
        self, mock_parser: MagicMock, mock_cim: MagicMock, mock_ga: MagicMock, mock_reg: MagicMock, mock_tz: MagicMock
    ) -> None:
        """Test successful extraction of Windows OS info"""
        mock_ssh_exec = MagicMock()

        mock_cim.return_value = {
            "CSName": "test-host",
            "BuildNumber": "19042",
            "Caption": "Microsoft Windows Server 2019",
            "Version": "10.0.19042",
            "OSArchitecture": "64-bit",
        }
        mock_ga.return_value = "7.4.0"
        mock_parser.return_value = "7.4.0"
        mock_reg.return_value = "REG_SZ    Windows Server 2019 Standard\r\n"
        mock_tz.return_value = "UTC"

        result = get_windows_os_info(mock_ssh_exec)
        mock_parser.assert_called_once_with(version_string="7.4.0")

        expected = {
            "guestAgentVersion": "7.4.0",
            "hostname": "test-host",
            "os": {
                "name": "Microsoft Windows",
                "kernelRelease": "19042",
                "version": "Microsoft Windows Server 2019",
                "prettyName": "Windows Server 2019 Standard",
                "versionId": "2019",
                "kernelVersion": "10.0",
                "machine": "x86_64",
                "id": "mswindows",
            },
            "timezone": "UTC",
        }
        assert result == expected, (
            "Windows OS information should match the expected guest agent, OS and timezone values"
        )
