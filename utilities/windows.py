"""Shared Windows guest queries without VM or SSP module dependencies."""

from __future__ import annotations

import json
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from logging import LoggerAdapter, getLogger
from re import search
from shlex import split
from typing import TYPE_CHECKING, Any, cast

from pyhelper_utils.shell import run_ssh_commands

from utilities.constants.timeouts import TCP_TIMEOUT_30SEC
from utilities.data_utils import guest_agent_version_parser

if TYPE_CHECKING:
    from re import Match

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


def get_windows_timezone(ssh_exec: Host, get_standard_name: bool = False) -> str:
    """Read the Windows guest's timezone through SSH.

    Args:
        ssh_exec: SSH connection to the Windows guest.
        get_standard_name: Return only the line containing StandardName.

    Returns:
        PowerShell timezone output, optionally filtered to StandardName.
    """
    standard_name_cmd = '| findstr "StandardName"' if get_standard_name else ""
    timezone_cmd = split(f'powershell -command "Get-TimeZone {standard_name_cmd}"')
    return run_ssh_commands(host=ssh_exec, commands=[timezone_cmd], tcp_timeout=TCP_TIMEOUT_30SEC)[0]


def get_ga_version(ssh_exec: Host) -> str:
    """Read the Windows QEMU guest agent executable's file version.

    Args:
        ssh_exec: SSH connection to the Windows guest.

    Returns:
        File version with surrounding whitespace removed.
    """
    return run_ssh_commands(
        host=ssh_exec,
        commands=[
            "powershell",
            "-Command",
            "(Get-Item",
            "'C:\\Program Files\\Qemu-ga\\qemu-ga.exe').VersionInfo.FileVersion",
        ],
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )[0].strip()


def get_reg_product_name(ssh_exec: Host) -> str:
    """Read the Windows ProductName registry value through SSH.

    Args:
        ssh_exec: SSH connection to the Windows guest.

    Returns:
        Unmodified REG QUERY output containing ProductName.
    """
    return run_ssh_commands(
        host=ssh_exec,
        commands=split(
            'REG QUERY "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion" /v "ProductName"'
        ),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )[0]


def get_windows_os_info(ssh_exec: Host) -> dict[str, Any]:
    """Collect Windows guest information for comparison with guest-agent data.

    Args:
        ssh_exec: SSH connection to the Windows guest.

    Returns:
        Guest agent version, hostname, OS properties and timezone.
    """
    cim_instance_json = get_cim_instance_json(ssh_exec=ssh_exec)
    return {
        "guestAgentVersion": guest_agent_version_parser(version_string=get_ga_version(ssh_exec=ssh_exec)),
        "hostname": cim_instance_json["CSName"],
        "os": {
            "name": "Microsoft Windows",
            "kernelRelease": cim_instance_json["BuildNumber"],
            "version": cast("Match[str]", search(pattern=r"(.+\d+)", string=cim_instance_json["Caption"])).group(1),
            "prettyName": cast(
                "Match[str]",
                search(pattern=r"REG_SZ\s+(.+)\r\n", string=get_reg_product_name(ssh_exec=ssh_exec)),
            ).group(1),
            "versionId": cast("Match[str]", search(pattern=r"\D+(\d+)", string=cim_instance_json["Caption"])).group(1),
            "kernelVersion": cast(
                "Match[str]", search(pattern=r"(\d+\.\d+)\.", string=cim_instance_json["Version"])
            ).group(1),
            "machine": "x86_64" if "64" in cim_instance_json["OSArchitecture"] else "x86",
            "id": "mswindows",
        },
        "timezone": get_windows_timezone(ssh_exec=ssh_exec),
    }


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
