import logging
from contextlib import contextmanager
from typing import Generator

from kubernetes.dynamic import DynamicClient
from ocp_resources.backup import Backup
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine import VirtualMachine

import shlex

from ocp_resources.storage_profile import StorageProfile

from utilities import console
from utilities.constants import (
    ADP_NAMESPACE,
    FILE_NAME_FOR_BACKUP,
    LS_COMMAND,
    OS_FLAVOR_RHEL,
    TEXT_TO_TEST,
    TIMEOUT_5MIN,
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

LOGGER = logging.getLogger(__name__)


def delete_velero_resource(resource, client):
    velero_pod = get_pod_by_name_prefix(dyn_client=client, pod_prefix="velero", namespace=ADP_NAMESPACE)
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