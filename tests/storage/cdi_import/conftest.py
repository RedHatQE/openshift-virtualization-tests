"""
CDI Import
"""

import gc
import logging

import pytest
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import py_config

from tests.storage.cdi_import.utils import wait_dv_and_get_importer, wait_for_multus_network_status
from tests.storage.constants import (
    HTTP,
    QUAY_FEDORA_CONTAINER_IMAGE,
)
from tests.storage.utils import (
    create_pod_for_pvc,
    get_file_url,
)
from utilities.constants import (
    LINUX_BRIDGE,
    OS_FLAVOR_FEDORA,
    REGISTRY_STR,
    TIMEOUT_1MIN,
    Images,
)
from utilities.infra import NON_EXIST_URL
from utilities.network import network_device, network_nad
from utilities.storage import create_dv, sc_volume_binding_mode_is_wffc
from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)
BRIDGE_NAME = "br1-dv"
DEFAULT_DV_SIZE = Images.Cirros.DEFAULT_DV_SIZE


@pytest.fixture()
def bridge_on_node(admin_client):
    """Create a Linux Bridge network device and yield it."""
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=BRIDGE_NAME,
        interface_name=BRIDGE_NAME,
        client=admin_client,
    ) as br:
        yield br


@pytest.fixture()
def linux_nad(admin_client, namespace, bridge_on_node):
    """Create a Linux Bridge Network Attachment Definition (NAD) and yield it."""
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name=f"{BRIDGE_NAME}-nad",
        interface_name=bridge_on_node.bridge_name,
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture()
def dv_non_exist_url(namespace, storage_class_name_scope_module):
    """Create a DV with a non-existent URL"""
    with create_dv(
        dv_name=f"cnv-876-{storage_class_name_scope_module}",
        namespace=namespace.name,
        url=NON_EXIST_URL,
        size=DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_module,
        client=namespace.client,
    ) as dv:
        yield dv


@pytest.fixture()
def dv_from_http_import(
    request,
    namespace,
    storage_class_name_scope_module,
    images_internal_http_server,
):
    """Create a DV from HTTP import with parameters from the test function."""
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
        client=namespace.client,
    ) as dv:
        dv.pvc.wait()
        yield dv


@pytest.fixture()
def running_pod_with_dv_pvc(
    storage_class_matrix__module__,
    storage_class_name_scope_module,
    dv_from_http_import,
):
    """Create a running pod with DV's PVC."""
    dv_from_http_import.wait_for_dv_success()
    with create_pod_for_pvc(
        pvc=dv_from_http_import.pvc,
        volume_mode=storage_class_matrix__module__[storage_class_name_scope_module]["volume_mode"],
    ) as pod:
        yield pod


@pytest.fixture()
def created_blank_dv_list(unprivileged_client, namespace, storage_class_name_scope_module, number_of_dvs):
    """Create a list of blank DVs."""
    dvs_list = []
    try:
        for dv_index in range(number_of_dvs):
            dv = DataVolume(
                client=unprivileged_client,
                source="blank",
                name=f"dv-{dv_index}",
                namespace=namespace.name,
                size=Images.Fedora.DEFAULT_DV_SIZE,
                storage_class=storage_class_name_scope_module,
                api_name="storage",
            )
            dv.create()
            dvs_list.append(dv)
        yield dvs_list
    finally:
        for dv in dvs_list:
            dv.clean_up()


@pytest.fixture()
def created_vm_list(unprivileged_client, created_blank_dv_list, storage_class_name_scope_module):
    """Create VMs sequentially from DVs and start them one by one."""
    vms_list = []
    try:
        for dv in created_blank_dv_list:
            if sc_volume_binding_mode_is_wffc(sc=storage_class_name_scope_module, client=unprivileged_client):
                dv.wait_for_status(status=DataVolume.Status.PENDING_POPULATION, timeout=TIMEOUT_1MIN)
            else:
                dv.wait_for_dv_success(timeout=TIMEOUT_1MIN)
            vm = VirtualMachineForTests(
                client=unprivileged_client,
                name=f"vm-{dv.name}",
                namespace=dv.namespace,
                os_flavor=OS_FLAVOR_FEDORA,
                data_volume=dv,
                image=Images.Fedora.FEDORA_CONTAINER_IMAGE,
                memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
            )
            vm.deploy(wait=True)
            vms_list.append(vm)
            vm.start()
        yield vms_list
    finally:
        for vm in vms_list:
            vm.clean_up()
        # Force garbage collection to prevent memory leaks due to paramiko/paramiko#2568
        gc.collect()


@pytest.fixture()
def dvs_and_vms_from_public_registry(unprivileged_client, namespace, storage_class_name_scope_function):
    """Create DVs from public registry and VMs from those DVs."""
    dvs = []
    vms = []
    try:
        for name in ("dv1", "dv2", "dv3"):
            dv = DataVolume(
                client=unprivileged_client,
                source=REGISTRY_STR,
                name=f"import-public-registry-quay-{name}",
                namespace=namespace.name,
                url=QUAY_FEDORA_CONTAINER_IMAGE,
                size=Images.Fedora.DEFAULT_DV_SIZE,
                storage_class=storage_class_name_scope_function,
                api_name="storage",
            )
            dv.create()
            dvs.append(dv)
            dv.pvc.wait(timeout=TIMEOUT_1MIN)

        for dv in dvs:
            vm = VirtualMachineForTests(
                client=unprivileged_client,
                name=dv.name,
                namespace=namespace.name,
                os_flavor=OS_FLAVOR_FEDORA,
                data_volume=dv,
                memory_requests=Images.Fedora.DEFAULT_MEMORY_SIZE,
            )
            vm.deploy(wait=True)
            vm.start()
            vms.append(vm)

        yield vms
    finally:
        for vm in vms:
            vm.clean_up()
        for dv in dvs:
            dv.clean_up()


@pytest.fixture()
def importer_pod_annotations(admin_client, namespace, linux_nad):
    """Create a DV with multus annotation and yield the importer pod annotations."""
    with create_dv(
        dv_name="dv-annotation",
        namespace=namespace.name,
        source=REGISTRY_STR,
        url=QUAY_FEDORA_CONTAINER_IMAGE,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        multus_annotation=linux_nad.name,
        client=namespace.client,
    ) as dv:
        importer_pod = wait_dv_and_get_importer(dv=dv, admin_client=admin_client)
        wait_for_multus_network_status(importer_pod=importer_pod)
        yield importer_pod.instance.metadata.annotations
