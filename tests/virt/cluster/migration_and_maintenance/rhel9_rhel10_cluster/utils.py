from typing import TYPE_CHECKING, Any, Final

from ocp_resources.resource import ResourceEditor

from utilities.constants.cluster import RHCOS9_WORKER_LABEL

if TYPE_CHECKING:
    from utilities.virt import VirtualMachineForTests

RHCOS9_AFFINITY: Final[dict[str, Any]] = {
    "nodeAffinity": {
        "requiredDuringSchedulingIgnoredDuringExecution": {
            "nodeSelectorTerms": [{"matchExpressions": [{"key": RHCOS9_WORKER_LABEL, "operator": "Exists"}]}]
        }
    }
}
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
