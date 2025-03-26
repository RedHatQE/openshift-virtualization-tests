"""
CDI Import
"""

import logging

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

from tests.storage.constants import HPP_STORAGE_CLASSES, HTTP
from tests.storage.utils import (
    clean_up_multiprocess,
    create_cirros_dv,
    create_pod_for_pvc,
    get_file_url,
    wait_for_processes_exit_successfully,
)
from utilities.constants import (
    LINUX_BRIDGE,
    OS_FLAVOR_FEDORA,
    TIMEOUT_1MIN,
    TIMEOUT_4MIN,
    Images,
)
from utilities.exceptions import ProcessWithException
from utilities.infra import NON_EXIST_URL
from utilities.network import network_device, network_nad
from utilities.storage import create_dv, sc_volume_binding_mode_is_wffc
from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)
BRIDGE_NAME = "br1-dv"
DEFAULT_DV_SIZE = Images.Cirros.DEFAULT_DV_SIZE


@pytest.fixture()
def skip_non_shared_storage(storage_class_name_scope_function):
    if storage_class_name_scope_function in HPP_STORAGE_CLASSES:
        pytest.skip("Skipping when storage is non-shared")


@pytest.fixture()
def bridge_on_node():
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=BRIDGE_NAME,
        interface_name=BRIDGE_NAME,
    ) as br:
        yield br


@pytest.fixture()
def linux_nad(namespace, bridge_on_node):
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name=f"{BRIDGE_NAME}-nad",
        interface_name=bridge_on_node.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture()
def cirros_pvc(
    data_volume_template_metadata,
):
    return PersistentVolumeClaim(
        name=data_volume_template_metadata["name"],
        namespace=data_volume_template_metadata["namespace"],
    )


@pytest.fixture()
def pvc_original_timestamp(
    cirros_pvc,
):
    return cirros_pvc.instance.metadata.creationTimestamp


@pytest.fixture()
def dv_non_exist_url(namespace, storage_class_name_scope_module):
    with create_dv(
        dv_name=f"cnv-876-{storage_class_name_scope_module}",
        namespace=namespace.name,
        url=NON_EXIST_URL,
        size=Images.Cirros.DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_module,
    ) as dv:
        yield dv


@pytest.fixture()
def dv_from_http_import(
    request,
    namespace,
    storage_class_name_scope_module,
    images_internal_http_server,
):
    with create_dv(
        dv_name=f"{request.param.get('dv_name', 'http-dv')}-{storage_class_name_scope_module}",
        namespace=namespace.name,
        url=get_file_url(
            url=images_internal_http_server[request.param.get("source", HTTP)],
            file_name=request.param["file_name"],
        ),
        content_type=request.param.get("content_type", DataVolume.ContentType.KUBEVIRT),
        cert_configmap=request.param.get("configmap_name"),
        size=request.param.get("size", DEFAULT_DV_SIZE),
        storage_class=storage_class_name_scope_module,
    ) as dv:
        yield dv


@pytest.fixture()
def running_pod_with_dv_pvc(
    storage_class_matrix__module__,
    storage_class_name_scope_module,
    dv_from_http_import,
):
    dv_from_http_import.wait_for_dv_success()
    with create_pod_for_pvc(
        pvc=dv_from_http_import.pvc,
        volume_mode=storage_class_matrix__module__[storage_class_name_scope_module]["volume_mode"],
    ) as pod:
        yield pod


@pytest.fixture(scope="module")
def cirros_dv_unprivileged(
    namespace,
    storage_class_name_scope_module,
    unprivileged_client,
):
    yield from create_cirros_dv(
        namespace=namespace.name,
        name=f"cirros-dv-{storage_class_name_scope_module}",
        storage_class=storage_class_name_scope_module,
        client=unprivileged_client,
        dv_size=Images.Cirros.DEFAULT_DV_SIZE,
    )


@pytest.fixture()
def dv_list_created_by_multiprocess(namespace, storage_class_name_scope_module, number_of_processes):
    dvs_list = []
    processes = {}
    for i in range(number_of_processes):
        dv = DataVolume(
            source="blank",
            name=f"dv-{i}",
            namespace=namespace.name,
            size=Images.Fedora.DEFAULT_DV_SIZE,
            storage_class=storage_class_name_scope_module,
            api_name="storage",
        )
        dv_process = ProcessWithException(target=dv.create)
        dv_process.start()
        processes[dv.name] = dv_process
        dvs_list.append(dv)
    wait_for_processes_exit_successfully(processes=processes, timeout=TIMEOUT_1MIN)
    yield dvs_list
    clean_up_multiprocess(processes=processes, object_list=dvs_list)


@pytest.fixture()
def vm_list_created_by_multiprocess(dv_list_created_by_multiprocess, storage_class_name_scope_module):
    vms_list = []
    processes = {}
    for dv in dv_list_created_by_multiprocess:
        if sc_volume_binding_mode_is_wffc(sc=storage_class_name_scope_module):
            dv.wait_for_status(status=DataVolume.Status.PENDING_POPULATION, timeout=TIMEOUT_1MIN)
        else:
            dv.wait_for_dv_success(timeout=TIMEOUT_1MIN)
        vm = VirtualMachineForTests(
            name=f"vm-{dv.name}",
            namespace=dv.namespace,
            os_flavor=OS_FLAVOR_FEDORA,
            data_volume=dv,
            image=Images.Fedora.FEDORA_CONTAINER_IMAGE,
            memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
        )
        vm.deploy()
        vms_list.append(vm)
    for vm in vms_list:
        vm_process = ProcessWithException(target=vm.start)
        vm_process.start()
        processes[vm.name] = vm_process

    wait_for_processes_exit_successfully(processes=processes, timeout=TIMEOUT_4MIN)
    yield vms_list
    clean_up_multiprocess(processes=processes, object_list=vms_list)
