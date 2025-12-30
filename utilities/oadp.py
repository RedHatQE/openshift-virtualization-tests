import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Self

from kubernetes.dynamic import DynamicClient
from ocp_resources.backup import Backup
from ocp_resources.datavolume import DataVolume
from ocp_resources.restore import Restore
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine import VirtualMachine

from utilities import console
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_http_image_url,
)
from utilities.constants import (
    ADP_NAMESPACE,
    LS_COMMAND,
    OS_FLAVOR_RHEL,
    TIMEOUT_5MIN,
    TIMEOUT_20SEC,
    Images,
)
from utilities.infra import (
    get_pod_by_name_prefix,
    unique_name,
)
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


def delete_velero_resource(resource: Backup | Restore, client: DynamicClient) -> None:
    velero_pod = get_pod_by_name_prefix(client=client, pod_prefix="velero", namespace=ADP_NAMESPACE)
    command = ["./velero", "delete", resource.kind.lower(), resource.name, "--confirm"]
    velero_pod.execute(command=command)


class VeleroBackup(Backup):
    def __init__(
        self,
        name: str,
        namespace: str = ADP_NAMESPACE,
        included_namespaces: list[str] | None = None,
        client: DynamicClient = None,
        teardown: bool = False,
        yaml_file: str | None = None,
        excluded_resources: list[str] | None = None,
        wait_complete: bool = True,
        snapshot_move_data: bool = False,
        storage_location: str | None = None,
        timeout: int = TIMEOUT_5MIN,
        **kwargs,
    ) -> None:
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

    def __enter__(self) -> "VeleroBackup":
        super().__enter__()
        if self.wait_complete:
            self.wait_for_status(
                status=self.Status.COMPLETED,
                timeout=self.timeout,
            )
        return self

    def __exit__(self, exception_type, exception_value, traceback) -> None:
        try:
            if self.teardown:
                delete_velero_resource(resource=self, client=self.client)
            else:
                LOGGER.info(f"Skipping Velero delete for {self.kind} {self.name} (teardown=False)")
        except Exception:
            LOGGER.exception(f"Failed to delete Velero {self.kind} {self.name}")
        finally:
            super().__exit__(exception_type, exception_value, traceback)


@contextmanager
def create_rhel_vm(
    storage_class: str,
    namespace: str,
    dv_name: str,
    vm_name: str,
    rhel_image: str,
    client: DynamicClient,
    wait_running: bool = True,
    volume_mode: str | None = None,
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
    finally:
        cleanup_artifactory_secret_and_config_map(
            artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
        )


class VeleroRestore(Restore):
    """
    class VeleroRestore(Restore): Context manager for managing a Velero Restore resource.

    This class extends the base Restore resource to provide optional synchronous waiting for
    restore completion and conditional cleanup (teardown) behavior when used as a context manager.

    Typical usage is within a ``with`` statement to ensure proper lifecycle handling of the restore resource.

    Behavior:
        * On context entry (``__enter__``):
            - Creates the Velero Restore resource via the base ``Restore`` class.
            - Optionally waits until the restore reaches ``COMPLETED`` status when ``wait_complete=True``.

        * On context exit (``__exit__``):
            - Deletes the Velero Restore resource if ``teardown=True``.
            - Skips deletion otherwise and logs the decision.
            - Always invokes the base class ``__exit__`` for cleanup.

    Args:
        name (str):
            Base name for the Velero Restore resource. A unique name will be  generated internally.
        namespace (str):
            Namespace where the restore resource is created.
        included_namespaces (list[str] | None):
            Namespaces included in the restore operation.
        backup_name (str | None):
            Name of the Velero Backup to restore from.
        client (DynamicClient | None):
            Kubernetes dynamic client used for API operations.
        teardown (bool):
            Whether to delete the restore resource on context exit.
        yaml_file (str | None):
            Optional YAML file used to define the restore resource.
        wait_complete (bool):
            Whether to wait for the restore to reach COMPLETED status on context entry.
        timeout (int):
            Timeout in seconds for waiting on restore completion.
        **kwargs (Any):
            Additional keyword arguments passed to the base ``Restore`` class.

    Example:
        with VeleroRestore(
            name="vm-restore",
            backup_name="vm-backup",
            client=client,
            wait_complete=True,
            teardown=True,
        ) as restore:
            # Restore is completed at this point
            pass
    """

    def __init__(
        self,
        name: str,
        namespace: str = ADP_NAMESPACE,
        included_namespaces: list[str] | None = None,
        backup_name: str | None = None,
        client: DynamicClient | None = None,
        teardown: bool = False,
        yaml_file: str | None = None,
        wait_complete: bool = True,
        timeout: int = TIMEOUT_5MIN,
        **kwargs: Any,
    ) -> None:
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

    def __enter__(self) -> Self:
        super().__enter__()
        if self.wait_complete:
            self.wait_for_status(
                status=self.Status.COMPLETED,
                timeout=self.timeout,
            )
        return self

    def __exit__(self, exception_type, exception_value, traceback) -> None:
        try:
            if self.teardown:
                delete_velero_resource(resource=self, client=self.client)
            else:
                LOGGER.info(
                    "Skipping Velero delete",
                    extra={
                        "resource_kind": self.kind,
                        "resource_name": self.name,
                        "teardown": False,
                    },
                )
        except Exception:
            LOGGER.exception(
                "Failed to delete Velero resource",
                extra={
                    "resource_kind": self.kind,
                    "resource_name": self.name,
                },
            )
        finally:
            super().__exit__(exception_type, exception_value, traceback)


def check_file_in_vm(vm: VirtualMachineForTests, file_name: str, file_content: str) -> None:
    """
    Verify that a file exists in the VM and contains the expected content.

    This function opens a console session to the given virtual machine,
    verifies that the specified file exists, and checks that its content matches the expected value.

    Args:
        vm: Virtual machine instance to check.
        file_name: Name of the file expected to exist in the VM.
        file_content: Expected content of the file.

    Raises:
        pexpect.TIMEOUT: If the expected file name or content is not observed within the configured timeout.
        pexpect.EOF: If the console session terminates unexpectedly.

    Example:
        check_file_in_vm(
            vm=rhel_vm,
            file_name="file_before_backup.txt",
            file_content="test-data",
        )
    """
    LOGGER.info(
        "Starting file verification in VM",
        extra={
            "vm_name": vm.name,
            "file_name": file_name,
        },
    )
    with console.Console(vm=vm) as vm_console:
        LOGGER.info(
            "Listing files in VM",
            extra={"vm_name": vm.name},
        )
        vm_console.sendline(LS_COMMAND)
        vm_console.expect(file_name, timeout=TIMEOUT_20SEC)
        LOGGER.info(
            "Verifying file content in VM",
            extra={
                "vm_name": vm.name,
                "file_name": file_name,
            },
        )
        vm_console.sendline(f"cat {file_name}")
        vm_console.expect(file_content, timeout=TIMEOUT_20SEC)
        LOGGER.info(
            "File verification succeeded",
            extra={
                "vm_name": vm.name,
                "file_name": file_name,
            },
        )


def is_storage_class_support_volume_mode(
    admin_client: DynamicClient, storage_class_name: str, requested_volume_mode: str
) -> bool:
    """
    Check whether a storage class supports a specific volume mode.

    This function inspects the StorageProfile associated with the given
    storage class and determines whether the requested volume mode
    (e.g. 'Filesystem' or 'Block') is listed in its claim property sets.

    Args:
        admin_client: OpenShift DynamicClient with sufficient permissions to access StorageProfile resources.
        storage_class_name: Name of the StorageClass to be checked.
        requested_volume_mode: Requested volume mode to validate (e.g. 'Filesystem' or 'Block').

    Returns:
        True if the storage class supports the requested volume mode;
        False otherwise.

    Example:
        is_storage_class_support_volume_mode(
            admin_client=admin_client,
            storage_class_name="ocs-storagecluster-ceph-rbd",
            requested_volume_mode="Block",
        )
    """
    for claim_property_set in StorageProfile(client=admin_client, name=storage_class_name).claim_property_sets:
        if claim_property_set.volumeMode == requested_volume_mode:
            return True
    return False
