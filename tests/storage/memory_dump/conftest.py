import re
import shlex

import bitmath
import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

from tests.storage.memory_dump.utils import wait_for_memory_dump_status_completed
from utilities.constants import TIMEOUT_2MIN, Images
from utilities.storage import PodWithPVC, get_containers_for_pods_with_pvc, virtctl_memory_dump
from utilities.virt import running_vm, vm_instance_from_template


@pytest.fixture()
def windows_vm_for_memory_dump(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_function,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_function,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def pvc_for_windows_memory_dump(namespace, storage_class_with_filesystem_volume_mode):
    # memory_dump_size is 10Gi(Images.Windows.DEFAULT_MEMORY_SIZE + memory dump overhead size)
    memory_dump_size = (
        (bitmath.parse_string_unsafe(Images.Windows.DEFAULT_MEMORY_SIZE) + bitmath.parse_string_unsafe("2Gi"))
        .to_GiB()
        .format("{value:.2f}{unit}")[:-1]
    )
    with PersistentVolumeClaim(
        name="dump-pvc",
        namespace=namespace.name,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=memory_dump_size,
        storage_class=storage_class_with_filesystem_volume_mode,
    ) as pvc:
        yield pvc


@pytest.fixture()
def windows_vm_memory_dump(namespace, windows_vm_for_memory_dump, pvc_for_windows_memory_dump):
    status, out, err = virtctl_memory_dump(
        action="get",
        namespace=namespace.name,
        vm_name=windows_vm_for_memory_dump.name,
        claim_name=pvc_for_windows_memory_dump.name,
    )
    assert status, f"Failed to get memory dump, out: {out}, err: {err}."
    yield


@pytest.fixture()
def windows_vm_memory_dump_completed(windows_vm_for_memory_dump):
    wait_for_memory_dump_status_completed(vm=windows_vm_for_memory_dump)


@pytest.fixture()
def consumer_pod_for_verifying_windows_memory_dump(namespace, windows_vm_for_memory_dump, pvc_for_windows_memory_dump):
    with PodWithPVC(
        namespace=namespace.name,
        name="consumer-pod",
        pvc_name=pvc_for_windows_memory_dump.name,
        containers=get_containers_for_pods_with_pvc(
            volume_mode=DataVolume.VolumeMode.FILE, pvc_name=pvc_for_windows_memory_dump.name
        ),
    ) as pod:
        pod.wait_for_status(status=pod.Status.RUNNING, timeout=TIMEOUT_2MIN)

        assert re.match(
            rf"{windows_vm_for_memory_dump.name}-{pvc_for_windows_memory_dump.name}-\d*-\d*.memory.dump",
            pod.execute(command=shlex.split("bash -c 'ls -1 /pvc | grep dump'")),
            re.IGNORECASE,
        ), "Memory dump file doesn't exist"


@pytest.fixture()
def windows_vm_memory_dump_deletion(namespace, windows_vm_for_memory_dump):
    status, out, err = virtctl_memory_dump(
        action="remove",
        namespace=namespace.name,
        vm_name=windows_vm_for_memory_dump.name,
    )
    assert status, f"Failed to remove memory dump, out: {out}, err: {err}."
    yield
