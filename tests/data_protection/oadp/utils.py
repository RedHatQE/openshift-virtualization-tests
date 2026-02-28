import logging
import shlex
from contextlib import contextmanager
from typing import Generator

from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.restore import Restore
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine import VirtualMachine
from pyhelper_utils.shell import run_ssh_commands

from utilities import console
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_http_image_url,
)
from utilities.constants import (
    ADP_NAMESPACE,
    FILE_NAME_FOR_BACKUP,
    LS_COMMAND,
    OS_FLAVOR_WINDOWS,
    TEXT_TO_TEST,
    TIMEOUT_5MIN,
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
    TIMEOUT_20SEC,
    Images,
)
from utilities.infra import (
    unique_name,
)
from utilities.oadp import delete_velero_resource
from utilities.virt import VirtualMachineForTests, running_vm

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
    if vm.os_flavor == OS_FLAVOR_WINDOWS:
        check_file_in_windows_vm(vm=vm)
    else:
        with console.Console(vm=vm) as vm_console:
            vm_console.sendline(LS_COMMAND)
            vm_console.expect(FILE_NAME_FOR_BACKUP, timeout=TIMEOUT_20SEC)
            vm_console.sendline(f"cat {FILE_NAME_FOR_BACKUP}")
            vm_console.expect(TEXT_TO_TEST, timeout=TIMEOUT_20SEC)


def check_file_in_windows_vm(vm):
    """Check if file exists and contains expected content in Windows VM."""
    cmd = shlex.split(f'powershell -command "Get-Content {FILE_NAME_FOR_BACKUP}"')
    output = run_ssh_commands(host=vm.ssh_exec, commands=cmd)[0].strip()
    assert TEXT_TO_TEST in output, f"Expected '{TEXT_TO_TEST}' in file content, got '{output}'"


def is_storage_class_support_volume_mode(storage_class_name, requested_volume_mode):
    for claim_property_set in StorageProfile(name=storage_class_name).claim_property_sets:
        if claim_property_set.volumeMode == requested_volume_mode:
            return True
    return False


def wait_for_restored_dv(dv):
    dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_15SEC)
    dv.wait_for_dv_success(timeout=TIMEOUT_10SEC)


@contextmanager
def create_windows_vm(
    storage_class: str,
    namespace: str,
    dv_name: str,
    vm_name: str,
    windows_image: str,
    client: DynamicClient,
    wait_running: bool = True,
) -> Generator["VirtualMachineForTests", None, None]:
    artifactory_secret = None
    artifactory_config_map = None

    try:
        artifactory_secret = get_artifactory_secret(namespace=namespace)
        artifactory_config_map = get_artifactory_config_map(namespace=namespace)

        dv = DataVolume(
            name=dv_name,
            namespace=namespace,
            source="http",
            url=get_http_image_url(
                image_directory=Images.Windows.UEFI_WIN_DIR,
                image_name=windows_image,
            ),
            storage_class=storage_class,
            size=Images.Windows.DEFAULT_DV_SIZE,
            api_name="storage",
            secret=artifactory_secret,
            cert_configmap=artifactory_config_map.name,
        )
        dv.to_dict()
        dv_metadata = dv.res["metadata"]
        with VirtualMachineForTests(
            client=client,
            name=vm_name,
            namespace=dv_metadata["namespace"],
            os_flavor=OS_FLAVOR_WINDOWS,
            memory_guest=Images.Windows.DEFAULT_MEMORY_SIZE,
            data_volume_template={"metadata": dv_metadata, "spec": dv.res["spec"]},
            run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        ) as vm:
            if wait_running:
                running_vm(vm=vm, wait_for_interfaces=True)
            yield vm
    finally:
        cleanup_artifactory_secret_and_config_map(
            artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
        )
