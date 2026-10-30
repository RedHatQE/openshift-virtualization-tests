from typing import TYPE_CHECKING

from utilities.constants.timeouts import TIMEOUT_10MIN, TIMEOUT_30MIN
from utilities.virt import (
    VirtualMachineForTests,
    get_created_migration_job,
    wait_for_migration_finished,
    wait_for_ssh_connectivity,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient


def wait_for_autopilot_rhos_migration(vm: VirtualMachineForTests, admin_client: DynamicClient) -> None:
    """Wait for the autopilot to migrate VM between different RHCOS version nodes after changing VM affinity."""
    vmim = get_created_migration_job(vm=vm, client=admin_client)
    wait_for_migration_finished(migration=vmim, timeout=TIMEOUT_30MIN if "windows" in vm.name else TIMEOUT_10MIN)
    wait_for_ssh_connectivity(vm=vm)
