import logging
from collections.abc import Generator
from contextlib import contextmanager
from re import escape
from shlex import quote
from typing import Any, Self

from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.backup import Backup
from ocp_resources.datavolume import DataVolume
from ocp_resources.exceptions import ResourceTeardownError
from ocp_resources.restore import Restore
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine import VirtualMachine

from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_http_image_url,
)
from utilities.console import Console
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
    """
    Delete a Velero resource using the Velero CLI inside the Velero pod.

    Args:
        resource (Backup | Restore):
            The Velero resource to delete.
        client (DynamicClient):
            Kubernetes dynamic client used to locate the Velero pod.

    Raises:
        ResourceNotFoundError:
            If the Velero pod or resource cannot be found.
    """

    command = ["./velero", "delete", resource.kind.lower(), resource.name, "--confirm"]

    try:
        velero_pod = get_pod_by_name_prefix(client=client, pod_prefix="velero", namespace=ADP_NAMESPACE)

        LOGGER.info(f"Deleting Velero resource: kind={resource.kind} name={resource.name} command={' '.join(command)}")

        velero_pod.execute(command=command)

    except ResourceNotFoundError:
        LOGGER.error(
            f"Failed to delete Velero resource: kind={resource.kind} name={resource.name} command={' '.join(command)}",
            exc_info=True,
        )

        raise


def _velero_teardown(resource, exception_type, exception_value, traceback):
    teardown_error = None

    if resource.teardown:
        try:
            delete_velero_resource(resource=resource, client=resource.client)
        except Exception as error:
            LOGGER.error(
                f"Failed to delete Velero resource during teardown: kind={resource.kind} name={resource.name}",
                exc_info=True,
            )
            teardown_error = error

    else:
        LOGGER.info(f"Skipping Velero delete: kind={resource.kind} name={resource.name} teardown=False")

    if teardown_error is not None and exception_type is None:
        raise ResourceTeardownError(resource=resource) from teardown_error


class VeleroBackup(Backup):
    def __init__(
        self,
        name: str,
        client: DynamicClient,
        namespace: str = ADP_NAMESPACE,
        included_namespaces: list[str] | None = None,
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
        _velero_teardown(
            resource=self, exception_type=exception_type, exception_value=exception_value, traceback=traceback
        )
        return super().__exit__(exception_type, exception_value, traceback)


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
    Context manager for managing a Velero Restore resource.

    Args:
        wait_complete (bool):
            Whether to wait for the Restore to reach COMPLETED status on context entry.
    """

    def __init__(
        self,
        name: str,
        namespace: str = ADP_NAMESPACE,
        teardown: bool = True,
        wait_complete: bool = True,
        timeout: int = TIMEOUT_5MIN,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=unique_name(name=name),
            namespace=namespace,
            teardown=teardown,
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
        _velero_teardown(
            resource=self, exception_type=exception_type, exception_value=exception_value, traceback=traceback
        )
        return super().__exit__(exception_type, exception_value, traceback)


def check_file_in_running_vm(vm: VirtualMachineForTests, file_name: str, file_content: str) -> None:
    """
    Verify that a file exists in a running VM and contains the expected content.
    VM must be running before calling this function.

    This function opens a console session to the given virtual machine,
    verifies that the specified file exists, and checks that its content matches the expected value.

    Args:
        vm: Virtual machine instance to check.
        file_name: Name of the file expected to exist in the VM.
        file_content: Expected content of the file.
    """
    LOGGER.info(f"Starting file verification in VM: vm={vm.name}, file={file_name}")

    with Console(vm=vm) as vm_console:
        LOGGER.info(f"Listing files in VM: vm={vm.name}")
        vm_console.sendline(LS_COMMAND)
        vm_console.expect(pattern=escape(file_name), timeout=TIMEOUT_20SEC)
        LOGGER.info(f"Verifying file content in VM: vm={vm.name}, file={file_name}")
        vm_console.sendline(f"cat {quote(file_name)}")
        vm_console.expect(pattern=escape(file_content), timeout=TIMEOUT_20SEC)
        LOGGER.info(f"File verification succeeded: vm={vm.name}, file={file_name}")


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
    """
    profile = StorageProfile(client=admin_client, name=storage_class_name)

    claim_property_sets = profile.claim_property_sets
    if not claim_property_sets:
        return False

    return any(prop.volumeMode == requested_volume_mode for prop in claim_property_sets)
