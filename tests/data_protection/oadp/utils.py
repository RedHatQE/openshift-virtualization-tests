import logging
import shlex
from contextlib import contextmanager

from ocp_resources.backup import Backup
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.restore import Restore
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine import VirtualMachine

from utilities import console
from utilities.constants import (
    LS_COMMAND,
    OS_FLAVOR_RHEL,
    TIMEOUT_5MIN,
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
    TIMEOUT_20SEC,
    Images,
)
from utilities.infra import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_http_image_url,
    get_pod_by_name_prefix,
    unique_name,
)
from utilities.virt import VirtualMachineForTests, running_vm

ADP_NAMESPACE = "openshift-adp"
FILE_NAME_FOR_BACKUP = "file_before_backup.txt"
LOGGER = logging.getLogger(__name__)
TEXT_TO_TEST = "text"


def delete_velero_resource(resource, client):
    velero_pod = get_pod_by_name_prefix(dyn_client=client, pod_prefix="velero", namespace=ADP_NAMESPACE)
    velero_pod.execute(
        command=shlex.split(f"bash -c 'echo  Y | ./velero  delete {resource.kind.lower()} {resource.name}'")
    )


class VeleroBackup(Backup):
    def __init__(
        self,
        name,
        namespace=ADP_NAMESPACE,
        included_namespaces=None,
        client=None,
        teardown=False,
        yaml_file=None,
        excluded_resources=None,
        wait_complete=True,
        snapshot_move_data=False,
        storage_location=None,
        timeout=TIMEOUT_5MIN,
        **kwargs,
    ):
        super().__init__(
            name=unique_name(name=name),
            namespace=namespace,
            included_namespaces=included_namespaces,
            client=client,
            teardown=teardown,
            yaml_file=yaml_file,
            excluded_resources=excluded_resources,
            storage_location=storage_location,
            snapshot_move_data=snapshot_move_data,
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


@contextmanager
def create_rhel_vm(
    storage_class,
    namespace,
    dv_name,
    vm_name,
    rhel_image,
    client=None,
    wait_running=True,
    volume_mode=None,
):
    artifactory_secret = get_artifactory_secret(namespace=namespace)
    artifactory_config_map = get_artifactory_config_map(namespace=namespace)
    dv = DataVolume(
        name=dv_name,
        namespace=namespace,
        source="http",
        url=get_http_image_url(
            image_directory=Images.Rhel.DIR,
            image_name=rhel_image,
        ),
        storage_class=storage_class,
        size=Images.Rhel.DEFAULT_DV_SIZE,
        api_name="storage",
        volume_mode=volume_mode,
        secret=artifactory_secret,
        cert_configmap=artifactory_config_map.name,
    )
    dv.to_dict()
    dv_metadata = dv.res["metadata"]
    with VirtualMachineForTests(
        client=client,
        name=vm_name,
        namespace=dv_metadata["namespace"],
        os_flavor=OS_FLAVOR_RHEL,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        data_volume_template={"metadata": dv_metadata, "spec": dv.res["spec"]},
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
    ) as vm:
        if wait_running:
            running_vm(vm=vm, wait_for_interfaces=True)
        yield vm
    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
    )


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
