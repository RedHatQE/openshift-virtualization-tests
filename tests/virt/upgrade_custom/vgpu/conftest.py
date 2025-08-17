import pytest
from ocp_resources.data_source import DataSource
from pytest_testconfig import config as py_config

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from tests.virt.node.gpu.constants import (
    VGPU_DEVICE_NAME_STR,
)
from tests.virt.upgrade.utils import vm_from_template
from tests.virt.utils import build_node_affinity_dict, verify_gpu_device_exists_on_node
from utilities.constants import ES_NONE, TIMEOUT_30MIN
from utilities.storage import (
    create_dv,
    generate_data_source_dict,
    get_test_artifact_server_url,
)


@pytest.fixture
def vgpu_on_nodes(nodes_with_supported_gpus, supported_gpu_device):
    verify_gpu_device_exists_on_node(
        gpu_nodes=nodes_with_supported_gpus, device_name=supported_gpu_device[VGPU_DEVICE_NAME_STR]
    )


@pytest.fixture(scope="session")
def rhel_data_volume(
    admin_client,
):
    with create_dv(
        client=admin_client,
        dv_name=RHEL_LATEST_OS,
        namespace=py_config["golden_images_namespace"],
        url=f"{get_test_artifact_server_url()}{RHEL_LATEST['image_path']}",
        storage_class=py_config["default_storage_class"],
        access_modes=py_config["default_access_mode"],
        volume_mode=py_config["default_volume_mode"],
        size=RHEL_LATEST["dv_size"],
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_30MIN)
        yield dv


@pytest.fixture(scope="session")
def rhel_data_source(
    admin_client,
    rhel_data_volume,
):
    with DataSource(
        name=rhel_data_volume.name,
        namespace=rhel_data_volume.namespace,
        client=admin_client,
        source=generate_data_source_dict(dv=rhel_data_volume),
    ) as ds:
        yield ds


@pytest.fixture(scope="session")
def rhel_vm_for_upgrade_session_scope(
    unprivileged_client,
    upgrade_namespace_scope_session,
    supported_gpu_device,
    nodes_with_supported_gpus,
    rhel_data_source,
):
    with vm_from_template(
        vm_name="rhel-vgpu-gpus-spec-vm",
        client=unprivileged_client,
        namespace=upgrade_namespace_scope_session.name,
        template_labels=RHEL_LATEST_LABELS,
        data_source=rhel_data_source,
        vm_affinity=build_node_affinity_dict(values=[nodes_with_supported_gpus[0].name]),
        gpu_name=supported_gpu_device.get(VGPU_DEVICE_NAME_STR),
        eviction_strategy=ES_NONE,
    ) as vm:
        yield vm
