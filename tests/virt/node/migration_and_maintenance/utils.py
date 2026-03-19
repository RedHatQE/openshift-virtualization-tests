from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pyhelper_utils.shell import run_ssh_commands

from utilities.constants.images import OS_FLAVOR_WINDOWS
from utilities.constants.timeouts import TCP_TIMEOUT_30SEC
from utilities.constants.virt import REGEDIT_PROC_NAME
from utilities.virt import fetch_pid_from_linux_vm, fetch_pid_from_windows_vm

if TYPE_CHECKING:
    from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)

# Allocate and continuously re-dirty memory pages without stress-ng (uses built-in PowerShell/Python).
WIN_MEM_LOAD_CMD = (
    "powershell.exe -NoProfile -WindowStyle Hidden -Command"
    ' "$a0=New-Object byte[] (1GB);$a1=New-Object byte[] (1GB);'
    ' while($true){ for($i=0;$i -lt $a0.Length;$i+=4096){$a0[$i]++;$a1[$i]++} }"'
)
RHEL_MEM_LOAD_CMD = (
    "import time; a = bytearray(2 * 1024**3); "
    'exec("while True: [a.__setitem__(i, (a[i]+1)%256) for i in range(0, len(a), 4096)]; time.sleep(0.5)")'
)


def assert_expected_migration_mode(vm: VirtualMachineForTests, expected_mode: str) -> None:
    migration_state = vm.vmi.instance.status.migrationState
    assert migration_state.mode == expected_mode, (
        f"Migration mode is not {expected_mode}! VMI MigrationState {migration_state}"
    )


def assert_same_pid_after_migration(orig_pid: str, vm: VirtualMachineForTests) -> None:
    if vm.os_flavor == OS_FLAVOR_WINDOWS:
        new_pid = fetch_pid_from_windows_vm(vm=vm, process_name=REGEDIT_PROC_NAME)
    else:
        new_pid = fetch_pid_from_linux_vm(vm=vm, process_name="ping")
    assert new_pid == orig_pid, f"PID mismatch after migration! orig_pid: {orig_pid}; new_pid: {new_pid}"


def start_memory_pressure_on_vm(vm: VirtualMachineForTests) -> None:
    """Continuously dirty memory pages to prevent pre-copy migration convergence.

    Kills any leftover stress processes before spawning new ones, since
    previous processes may be degraded after migration.

    This function requires no external tools — uses built-in PowerShell on Windows
    and Python on Linux.

    Args:
        vm: Target VM to stress.
    """
    is_windows = vm.os_flavor == OS_FLAVOR_WINDOWS

    LOGGER.info(f"Killing leftover memory pressure processes on VM {vm.name}")
    if is_windows:
        kill_cmd = ["powershell", "Stop-Process", "-Name", "powershell", "-Force"]
    else:
        kill_cmd = ["pkill", "-f", "python3 -c.*bytearray"]
    run_ssh_commands(host=vm.ssh_exec, commands=kill_cmd, tcp_timeout=TCP_TIMEOUT_30SEC, check_rc=False)

    if is_windows:
        cmd = [
            "powershell",
            "Invoke-WmiMethod",
            "-Class",
            "Win32_Process",
            "-Name",
            "Create",
            "-ArgumentList",
            f"'{WIN_MEM_LOAD_CMD}'",
        ]
    else:
        cmd = [
            "/bin/bash",
            "-c",
            f"nohup python3 -c '{RHEL_MEM_LOAD_CMD}' >/dev/null 2>&1 &",
        ]
    run_ssh_commands(host=vm.ssh_exec, commands=cmd, tcp_timeout=TCP_TIMEOUT_30SEC)
    LOGGER.info(f"Started 2GB memory pressure on VM {vm.name}")
