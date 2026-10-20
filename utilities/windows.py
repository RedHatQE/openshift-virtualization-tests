"""Shared Windows guest queries without VM or SSP module dependencies."""

from __future__ import annotations

import json
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from logging import LoggerAdapter, getLogger
from shlex import split
from typing import TYPE_CHECKING, Any

from pyhelper_utils.shell import run_ssh_commands

if TYPE_CHECKING:
    from rrmngmnt import Host


def get_cim_instance_json(ssh_exec: Host) -> dict[str, Any]:
    """Read selected Windows operating system properties through SSH.

    Args:
        ssh_exec: SSH connection to the Windows guest.

    Returns:
        CSName, BuildNumber, Caption, Version and OSArchitecture from the guest's
        Win32_OperatingSystem CIM instance.
    """
    return json.loads(
        s=run_ssh_commands(
            host=ssh_exec,
            commands=split(
                'powershell -c "Get-CimInstance -Class Win32_OperatingSystem | '
                'Select-Object CSName, BuildNumber, Caption, Version, OSArchitecture | ConvertTo-Json"'
            ),
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


def run_powershell_commands(
    *,
    ssh_exec: Host,
    script: str,
    input_data: str | None = None,
    timeout: int = 60,
) -> str:
    """Run PowerShell over SSH and include stderr in failure exceptions.

    Args:
        ssh_exec: Existing guest connection, including its virtctl proxy.
        script: Trusted script. Sensitive values must be passed in input_data.
            Only the last native command's exit code is propagated; check earlier
            native failures before running another native command.
        input_data: Optional data exposed as $InputData to the trusted script.
            The script and data are sent in a JSON stdin envelope without
            transport logging.
        timeout: SSH command I/O timeout in seconds.

    Returns:
        Guest stdout decoded as UTF-8. Callers can parse JSON without logging it.

    Raises:
        RuntimeError: PowerShell raises a terminating error or the last native
            command returns a nonzero exit status. The exception includes stderr;
            stdout is never included.
    """
    executor = ssh_exec.executor()
    # rrmngmnt's default logger adapter includes the authentication password.
    # Replace it on this executor only; leave shared logger configuration alone.
    executor.set_logger(logger=LoggerAdapter(logger=getLogger(name=__name__), extra={}))
    bootstrap = """
$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
try {
 $envelope=ConvertFrom-Json ([Console]::In.ReadToEnd())
 $InputData=$envelope.input_data
 $global:LASTEXITCODE=0
 & ([ScriptBlock]::Create($envelope.script))
} catch {
 [Console]::Error.WriteLine($_.Exception.Message)
 exit 1
}
exit $global:LASTEXITCODE
"""
    with executor.session(timeout=30) as session:
        command = session.command(cmd=powershell_command(script=bootstrap))
        # Read streams directly: Command.run stores stdout/stderr in attributes
        # that rrmngmnt logs, whereas execute leaves those attributes empty.
        with command.execute(timeout=timeout, get_pty=False) as (stdin, stdout, stderr):
            stdin.write(json.dumps({"script": script, "input_data": input_data}))
            stdin.flush()
            stdin.channel.shutdown_write()
            with ThreadPoolExecutor(max_workers=1) as reader:
                stderr_result = reader.submit(stderr.read)
                output = stdout.read().decode("utf-8-sig")
                error_details = stderr_result.result().decode("utf-8-sig", errors="replace").strip()
        if command.rc:
            message = f"PowerShell operation failed (exit status {command.rc})"
            if error_details:
                message += f": {error_details}"
            raise RuntimeError(message)
        return output
