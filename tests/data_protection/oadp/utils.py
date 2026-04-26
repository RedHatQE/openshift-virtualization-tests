from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.template import Template
from pyhelper_utils.shell import run_ssh_commands

from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
)
from utilities.constants import (
    TEXT_TO_TEST,
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
    TIMEOUT_60MIN,
)
from utilities.virt import VirtualMachineForTests, VirtualMachineForTestsFromTemplate, running_vm

FILE_PATH_FOR_WINDOWS_BACKUP = "C:/oadp_file_before_backup.txt"

OADP_DPA_NAME = "dpa"
OADP_VELERO_IMAGE_FQIN_OVERRIDE = "quay.io/sseago/velero:csi-quick-poll"


def wait_for_restored_dv(dv: DataVolume) -> None:
    dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_15SEC)
    dv.wait_for_dv_success(timeout=TIMEOUT_10SEC)


def write_file_windows_vm_for_oadp(vm: VirtualMachineForTests) -> None:
    """Write test data to marker file on Windows VM for OADP backup verification."""
    value = TEXT_TO_TEST.replace("'", "''")
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Set-Content -LiteralPath '{FILE_PATH_FOR_WINDOWS_BACKUP}' -Value '{value}' -Encoding ascii",
    ]
    run_ssh_commands(host=vm.ssh_exec, commands=cmd)


@contextmanager
def create_windows_vm_from_dv_template(
    storage_class: str,
    namespace: str,
    dv_name: str,
    vm_name: str,
    image_url: str,
    dv_size: str,
    template_labels: dict[str, Any],
    client: DynamicClient,
    cpu_model: str | None = None,
    wait_running: bool = True,
    dv_wait_timeout: int = TIMEOUT_60MIN,
) -> Generator[VirtualMachineForTests, None, None]:
    """
    Create Windows VM from template with HTTP DataVolume.

    Args:
        storage_class: Storage class for the DataVolume.
        namespace: Target namespace.
        dv_name: DataVolume name.
        vm_name: VirtualMachine name.
        image_url: HTTP URL to Windows image.
        dv_size: DataVolume size.
        template_labels: Labels to identify the Windows template.
        client: Kubernetes dynamic client.
        cpu_model: CPU model for the VM.
        wait_running: Wait for VM to reach Running state.
        dv_wait_timeout: DataVolume import timeout.

    Yields:
        VirtualMachineForTests instance.
    """
    artifactory_secret = None
    artifactory_config_map = None

    try:
        artifactory_secret = get_artifactory_secret(namespace=namespace)
        artifactory_config_map = get_artifactory_config_map(namespace=namespace)

        dv = DataVolume(
            name=dv_name,
            namespace=namespace,
            storage_class=storage_class,
            source="http",
            url=image_url,
            size=dv_size,
            client=client,
            api_name="storage",
            secret=artifactory_secret,
            cert_configmap=artifactory_config_map.name,
        )
        dv.to_dict()
        with VirtualMachineForTestsFromTemplate(
            name=vm_name,
            namespace=namespace,
            client=client,
            labels=Template.generate_template_labels(**template_labels),
            cpu_model=cpu_model,
            data_volume_template={"metadata": dv.res["metadata"], "spec": dv.res["spec"]},
        ) as vm:
            if wait_running:
                running_vm(vm=vm, dv_wait_timeout=dv_wait_timeout)
            yield vm
    finally:
        cleanup_artifactory_secret_and_config_map(
            artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
        )
