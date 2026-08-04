import logging
from typing import TYPE_CHECKING

from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.restore import Restore
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from utilities import console
from utilities.constants import (
    ADP_NAMESPACE,
    FILE_NAME_FOR_BACKUP,
    LS_COMMAND,
    TEXT_TO_TEST,
    TIMEOUT_5MIN,
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
    TIMEOUT_20SEC,
    VELERO_BACKUP_HOOK_ANNOTATIONS,
)
from utilities.infra import (
    unique_name,
)
from utilities.oadp import delete_velero_resource

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)


class VeleroRestore(Restore):
    def __init__(
        self,
        name,
        namespace=ADP_NAMESPACE,
        included_namespaces=None,
        backup_name=None,
        client=None,
        teardown=False,
        yaml_file=None,
        wait_complete=True,
        timeout=TIMEOUT_5MIN,
        **kwargs,
    ):
        super().__init__(
            name=unique_name(name=name),
            namespace=namespace,
            included_namespaces=included_namespaces,
            backup_name=backup_name,
            client=client,
            teardown=teardown,
            yaml_file=yaml_file,
            **kwargs,
        )
        self.wait_complete = wait_complete
        self.timeout = timeout

    def __enter__(self):
        super().__enter__()
        if self.wait_complete:
            self.wait_for_status(
                status=self.Status.COMPLETED,
                timeout=self.timeout,
            )
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        delete_velero_resource(resource=self, client=self.client)


def check_file_in_vm(vm):
    with console.Console(vm=vm) as vm_console:
        vm_console.sendline(LS_COMMAND)
        vm_console.expect(FILE_NAME_FOR_BACKUP, timeout=TIMEOUT_20SEC)
        vm_console.sendline(f"cat {FILE_NAME_FOR_BACKUP}")
        vm_console.expect(TEXT_TO_TEST, timeout=TIMEOUT_20SEC)


def is_storage_class_support_volume_mode(storage_class_name, requested_volume_mode):
    for claim_property_set in StorageProfile(name=storage_class_name).claim_property_sets:
        if claim_property_set.volumeMode == requested_volume_mode:
            return True
    return False


def wait_for_restored_dv(dv):
    dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_15SEC)
    dv.wait_for_dv_success(timeout=TIMEOUT_10SEC)


def assert_velero_backup_hooks_not_injected(vm: VirtualMachineForTests, admin_client: DynamicClient) -> None:
    """Assert virt-launcher has no Velero freeze/unfreeze hook annotations.

    Absence of these annotations means Velero will not execute filesystem
    freeze/unfreeze during backup.

    Args:
        vm: VirtualMachine whose virt-launcher pod is checked.
        admin_client: Privileged client used to access the virt-launcher pod.

    Raises:
        AssertionError: If any Velero hook annotations are found on the virt-launcher pod.
    """
    virt_launcher_pod = VirtualMachineInstance(
        client=admin_client,
        name=vm.name,
        namespace=vm.namespace,
    ).virt_launcher_pod
    pod_annotations = virt_launcher_pod.instance.metadata.annotations or {}
    present_hook_annotations = [
        annotation_key for annotation_key in VELERO_BACKUP_HOOK_ANNOTATIONS if annotation_key in pod_annotations
    ]
    assert not present_hook_annotations, (
        f"VM {vm.name} virt-launcher pod has Velero hook annotations {present_hook_annotations} "
        f"but backup hooks should be disabled"
    )
