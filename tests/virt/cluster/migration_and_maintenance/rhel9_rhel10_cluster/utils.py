from typing import Any, Final

from ocp_resources.resource import ResourceEditor

from tests.virt.utils import build_node_affinity_dict
from utilities.constants.cluster import RHCOS9_WORKER_LABEL
from utilities.constants.virt import REGEDIT_PROC_NAME
from utilities.virt import VirtualMachineForTests, fetch_pid_from_linux_vm, fetch_pid_from_windows_vm

RHCOS9_AFFINITY: Final[dict[str, Any]] = build_node_affinity_dict(values=[""], key=RHCOS9_WORKER_LABEL)
RHCOS10_AFFINITY: Final[dict[str, Any]] = {
    "nodeAffinity": {
        "requiredDuringSchedulingIgnoredDuringExecution": {
            "nodeSelectorTerms": [{"matchExpressions": [{"key": RHCOS9_WORKER_LABEL, "operator": "DoesNotExist"}]}]
        }
    }
}


def set_vm_affinity(vm: VirtualMachineForTests, affinity: dict[str, Any]) -> None:
    """Update the VM template node affinity in-place via a strategic merge patch.

    Args:
        vm (VirtualMachineForTests): The VM whose template affinity should be replaced.
        affinity (dict[str, Any]): Kubernetes affinity dict to apply (e.g. RHCOS9_AFFINITY or RHCOS10_AFFINITY).
    """
    ResourceEditor(patches={vm: {"spec": {"template": {"spec": {"affinity": affinity}}}}}).update()


def assert_vm_did_not_restart(vm: VirtualMachineForTests, pre_migrate_pid: int) -> None:
    """Assert that a background process PID is unchanged, proving the VM was not restarted.

    Fetches the current PID of the background process started before migration and compares
    it with the recorded pre-migration PID. A changed PID indicates the VM restarted.

    Args:
        vm (VirtualMachineForTests): The VM to inspect.
        pre_migrate_pid (int): PID recorded before migration via vm_background_process_id fixture.
    """
    if "windows" in vm.name:
        post_pid = fetch_pid_from_windows_vm(vm=vm, process_name=REGEDIT_PROC_NAME)
    else:
        post_pid = fetch_pid_from_linux_vm(vm=vm, process_name="ping")
    assert post_pid == pre_migrate_pid, f"VM restarted during migration: PID changed {pre_migrate_pid} -> {post_pid}"
