import re
import shlex

import bitmath
import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pytest_testconfig import config as py_config

from tests.storage.memory_dump.utils import wait_for_memory_dump_status_completed
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_test_artifact_server_url,
)
from utilities.constants import (
    OS_FLAVOR_WIN_CONTAINER_DISK,
    TIMEOUT_2MIN,
    U1_LARGE,
    WIN_2K22,
    WINDOWS_2K22_PREFERENCE,
    Images,
)
from utilities.os_utils import get_windows_container_disk_path
from utilities.storage import (
    PodWithPVC,
    get_containers_for_pods_with_pvc,
    virtctl_memory_dump,
)
from utilities.virt import VirtualMachineForTests, running_vm, wait_for_windows_vm


@pytest.fixture()
def windows_vm_with_vtpm_for_memory_dump(
    unprivileged_client,
    namespace,
    cpu_for_migration,
):
    artifactory_secret = get_artifactory_secret(namespace=namespace.name)
    artifactory_config_map = get_artifactory_config_map(namespace=namespace.name)

    dv = DataVolume(
        name="windows-2022-dv",
        namespace=namespace.name,
        storage_class=py_config["default_storage_class"],
        source="registry",
        url=f"{get_test_artifact_server_url(schema='registry')}/{get_windows_container_disk_path(os_value=WIN_2K22)}",
        size=Images.Windows.CONTAINER_DISK_DV_SIZE,
        client=unprivileged_client,
        api_name="storage",
        secret=artifactory_secret,
        cert_configmap=artifactory_config_map.name,
    )
    dv.to_dict()

    with VirtualMachineForTests(
        name="windows-vm-mem",
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_LARGE, client=unprivileged_client),
        vm_preference=VirtualMachineClusterPreference(name=WINDOWS_2K22_PREFERENCE, client=unprivileged_client),
        data_volume_template={"metadata": dv.res["metadata"], "spec": dv.res["spec"]},
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        wait_for_windows_vm(vm=vm, version="2022")
        yield vm

    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
    )


@pytest.fixture()
def pvc_for_windows_memory_dump(unprivileged_client, namespace, storage_class_with_filesystem_volume_mode):
    # memory_dump_size is 10Gi(Images.Windows.DEFAULT_MEMORY_SIZE + memory dump overhead size)
    memory_dump_size = (
        (bitmath.parse_string_unsafe(Images.Windows.DEFAULT_MEMORY_SIZE) + bitmath.parse_string_unsafe("2Gi"))
        .to_GiB()
        .format("{value:.2f}{unit}")[:-1]
    )
    with PersistentVolumeClaim(
        client=unprivileged_client,
        name="dump-pvc",
        namespace=namespace.name,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=memory_dump_size,
        storage_class=storage_class_with_filesystem_volume_mode,
    ) as pvc:
        yield pvc


@pytest.fixture()
def windows_vm_memory_dump(namespace, windows_vm_with_vtpm_for_memory_dump, pvc_for_windows_memory_dump):
    status, out, err = virtctl_memory_dump(
        action="get",
        namespace=namespace.name,
        vm_name=windows_vm_with_vtpm_for_memory_dump.name,
        claim_name=pvc_for_windows_memory_dump.name,
    )
    assert status, f"Failed to get memory dump, out: {out}, err: {err}."
    yield


@pytest.fixture()
def windows_vm_memory_dump_completed(windows_vm_with_vtpm_for_memory_dump):
    wait_for_memory_dump_status_completed(vm=windows_vm_with_vtpm_for_memory_dump)


@pytest.fixture()
def consumer_pod_for_verifying_windows_memory_dump(
    namespace, windows_vm_with_vtpm_for_memory_dump, pvc_for_windows_memory_dump
):
    with PodWithPVC(
        namespace=namespace.name,
        name="consumer-pod",
        pvc_name=pvc_for_windows_memory_dump.name,
        containers=get_containers_for_pods_with_pvc(
            volume_mode=DataVolume.VolumeMode.FILE, pvc_name=pvc_for_windows_memory_dump.name
        ),
        client=pvc_for_windows_memory_dump.client,
    ) as pod:
        pod.wait_for_status(status=pod.Status.RUNNING, timeout=TIMEOUT_2MIN)

        assert re.match(
            rf"{windows_vm_with_vtpm_for_memory_dump.name}-{pvc_for_windows_memory_dump.name}-\d*-\d*.memory.dump",
            pod.execute(command=shlex.split("bash -c 'ls -1 /pvc | grep dump'")),
            re.IGNORECASE,
        ), "Memory dump file doesn't exist"


@pytest.fixture()
def windows_vm_memory_dump_deletion(namespace, windows_vm_with_vtpm_for_memory_dump):
    status, out, err = virtctl_memory_dump(
        action="remove",
        namespace=namespace.name,
        vm_name=windows_vm_with_vtpm_for_memory_dump.name,
    )
    assert status, f"Failed to remove memory dump, out: {out}, err: {err}."
    yield
