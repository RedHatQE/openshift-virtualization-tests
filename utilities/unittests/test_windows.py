"""Unit tests for shared Windows guest queries."""

from __future__ import annotations

from base64 import b64decode
from json import JSONDecodeError, loads
from logging import DEBUG
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from pytest import mark, raises
from rrmngmnt.ssh import RemoteExecutor
from rrmngmnt.user import User

from utilities.windows import get_cim_instance_json, powershell_command, run_powershell

if TYPE_CHECKING:
    from pytest import LogCaptureFixture


@mark.unit
class TestGetCimInstanceJson:
    def test_reads_operating_system_properties(self, mock_vm: MagicMock) -> None:
        expected = {
            "Caption": "Microsoft Windows Server 2025 Standard",
            "CSName": "test-host",
            "BuildNumber": "26100",
        }
        output = '{"Caption": "Microsoft Windows Server 2025 Standard", "CSName": "test-host", "BuildNumber": "26100"}'
        with patch("utilities.windows.run_ssh_commands", return_value=[output]) as remote_command:
            result = get_cim_instance_json(ssh_exec=mock_vm.ssh_exec)

        assert result == expected, "CIM properties were not preserved"
        remote_command.assert_called_once_with(
            host=mock_vm.ssh_exec,
            commands=["powershell", "-c", "Get-CimInstance -Class Win32_OperatingSystem | ConvertTo-Json"],
        )

    def test_rejects_invalid_json(self, mock_vm: MagicMock) -> None:
        with patch("utilities.windows.run_ssh_commands", return_value=["invalid JSON"]):
            with raises(JSONDecodeError):
                get_cim_instance_json(ssh_exec=mock_vm.ssh_exec)

    def test_propagates_transport_failure(self, mock_vm: MagicMock) -> None:
        with patch("utilities.windows.run_ssh_commands", side_effect=OSError("Connection reset")):
            with raises(OSError, match="Connection reset"):
                get_cim_instance_json(ssh_exec=mock_vm.ssh_exec)


@mark.unit
class TestPowerShellTransport:
    def test_encoding_preserves_shell_characters_and_unicode(self) -> None:
        script = "Write-Output 'à $secret `quoted`'"
        arguments = powershell_command(script=script)
        assert b64decode(arguments[-1]).decode("utf-16le") == script
        assert arguments[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand"]

    @mark.parametrize("exit_status", [0, 1])
    def test_real_executor_uses_short_bootstrap_and_never_logs_input_or_credentials(
        self, exit_status: int, caplog: LogCaptureFixture
    ) -> None:
        secret = "OFFLINE-SENSITIVE-INPUT"
        output = b'{"result":"OFFLINE-SENSITIVE-OUTPUT"}'
        host = MagicMock()
        executor = RemoteExecutor(
            user=User(name="Administrator", password="OFFLINE-AUTH-PASSWORD"), address="127.0.0.1"
        )
        host.executor.return_value = executor
        stdin, stdout, stderr = MagicMock(), MagicMock(), MagicMock()
        stdout.read.return_value = output
        stderr.read.return_value = secret.encode()
        stdout.channel.recv_exit_status.return_value = exit_status
        client = MagicMock()
        client.exec_command.return_value = stdin, stdout, stderr
        script = "Write-Output 'x'\n" * 1000
        with patch("rrmngmnt.ssh.paramiko.SSHClient", return_value=client):
            caplog.set_level(DEBUG)
            if exit_status:
                with raises(RuntimeError) as error:
                    run_powershell(ssh_exec=host, script=script, input_data=secret)
                assert secret not in str(error.value) and "SENSITIVE-OUTPUT" not in str(error.value)
            else:
                assert run_powershell(ssh_exec=host, script=script, input_data=secret) == output.decode()
        envelope = loads(stdin.write.call_args.args[0])
        assert envelope == {"script": script, "input_data": secret}
        stdin.channel.shutdown_write.assert_called_once()
        command = client.exec_command.call_args.args[0]
        assert len(command) < 2048 and secret not in command and script not in command
        assert secret not in caplog.text and "OFFLINE-AUTH-PASSWORD" not in caplog.text
        assert "OFFLINE-SENSITIVE-OUTPUT" not in caplog.text
        client.close.assert_called_once()

    def test_transport_error_propagates_and_closes_session(self) -> None:
        host = MagicMock()
        executor = host.executor.return_value
        session = executor.session.return_value.__enter__.return_value
        session.command.return_value.execute.side_effect = OSError("Connection reset")
        with raises(OSError, match="Connection reset"):
            run_powershell(ssh_exec=host, script="Get-Date")
        executor.session.return_value.__exit__.assert_called_once()
