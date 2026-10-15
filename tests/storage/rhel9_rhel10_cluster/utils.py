from __future__ import annotations

from typing import TYPE_CHECKING

from pyhelper_utils.shell import run_ssh_commands

from tests.storage.constants import TEST_FILE_NAME
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5SEC

if TYPE_CHECKING:
    from utilities.virt import VirtualMachineForTests

HOTPLUG_DISK_SERIAL: str = "hotplugmig"
HOTPLUG_MOUNT_POINT: str = "/mnt/hotplug"
HOTPLUG_TEST_FILE: str = f"{HOTPLUG_MOUNT_POINT}/{TEST_FILE_NAME}"


def prepare_hotplug_disk(vm: VirtualMachineForTests, serial: str) -> None:
    """Format the hotplugged blank disk, create a mount point, and mount it."""
    device = (
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=["bash", "-c", f"lsblk -rno NAME,SERIAL | grep {serial}"],
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )[0]
        .strip()
        .split()[0]
    )
    for cmd in [
        f"sudo mkfs.ext4 /dev/{device}",
        f"sudo mkdir -p {HOTPLUG_MOUNT_POINT}",
        f"sudo mount /dev/{device} {HOTPLUG_MOUNT_POINT}",
        f"sudo chmod 777 {HOTPLUG_MOUNT_POINT}",
    ]:
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=["bash", "-c", cmd],
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )
