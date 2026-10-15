"""Shared Windows guest queries without VM or SSP module dependencies."""

from __future__ import annotations

from base64 import b64encode
from json import dumps, loads
from logging import LoggerAdapter, getLogger
from shlex import split
from typing import TYPE_CHECKING, Any

from pyhelper_utils.shell import run_ssh_commands

if TYPE_CHECKING:
    from rrmngmnt import Host


def get_cim_instance_json(ssh_exec: Host) -> dict[str, Any]:
    """Read Windows operating system information through SSH.

    Args:
        ssh_exec: SSH connection to the Windows guest.

    Returns:
        Properties of the guest's Win32_OperatingSystem CIM instance.
    """
    return loads(
        s=run_ssh_commands(
            host=ssh_exec,
            commands=split('powershell -c "Get-CimInstance -Class Win32_OperatingSystem | ConvertTo-Json"'),
        )[0]
    )


def powershell_command(script: str) -> list[str]:
    """Encode PowerShell scripts as UTF-16LE to preserve quoting across Windows SSH.

    Args:
        script: PowerShell program containing no credentials in its command text.

    Returns:
        Command arguments for Windows PowerShell.
    """
    return [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
        b64encode(script.encode("utf-16le")).decode(),
    ]


def run_powershell(*, ssh_exec: Host, script: str, input_data: str | None = None, timeout: int = 60) -> str:
    """Run PowerShell using the existing SSH executor with unlogged stdin and output.

    Args:
        ssh_exec: Existing guest connection, including its virtctl proxy.
        script: Trusted script. Sensitive values must be passed in input_data.
        input_data: Optional data exposed as $InputData to the trusted script.
            The script and data travel as a JSON stdin envelope, never in argv/logs.
        timeout: SSH command I/O timeout in seconds.

    Returns:
        UTF-8 stdout. Callers can parse a JSON response without logging it.

    Raises:
        RuntimeError: The guest script returns a nonzero exit status. Output is
            deliberately omitted from the exception to avoid disclosing input.
    """
    executor = ssh_exec.executor()
    # rrmngmnt's default logger adapter includes the authentication password.
    # Replace it on this executor only; leave shared logger configuration alone.
    executor.set_logger(logger=LoggerAdapter(logger=getLogger(name=__name__), extra={}))
    bootstrap = """
$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
try {
 $envelope=ConvertFrom-Json ([Console]::In.ReadToEnd())
 $InputData=$envelope.input_data
 & ([ScriptBlock]::Create($envelope.script))
} catch { [Console]::Error.WriteLine($_.Exception.GetType().Name); exit 1 }
exit 0
"""
    with executor.session(timeout=30) as session:
        command = session.command(cmd=powershell_command(script=bootstrap))
        # Read streams directly: Command.run stores stdout/stderr in attributes
        # that rrmngmnt logs, whereas execute leaves those attributes empty.
        with command.execute(timeout=timeout, get_pty=False) as (stdin, stdout, stderr):
            stdin.write(dumps({"script": script, "input_data": input_data}))
            stdin.flush()
            stdin.channel.shutdown_write()
            output = stdout.read().decode("utf-8-sig")
            stderr.read()
        if command.rc:
            raise RuntimeError(f"PowerShell operation failed (exit status {command.rc})")
        return output
