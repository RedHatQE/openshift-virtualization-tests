import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.kubevirt import KubeVirt
from pytest_testconfig import config as py_config

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
from tests.virt.node.gpu.constants import (
    GPU_WORKLOAD_CONFIG_LABEL,
    MDEV_NAME_STR,
    VGPU_CONFIG_LABEL,
    VGPU_DEVICE_NAME_STR,
)
from tests.virt.node.gpu.utils import (
    verify_mdev_bus_available,
    vgpu_node_labels_applied,
    wait_for_nvidia_vgpu_manager,
)
from tests.virt.upgrade.utils import vm_from_template
from tests.virt.utils import build_node_affinity_dict, verify_gpu_device_exists_on_node
from utilities.artifactory import get_test_artifact_server_url
from utilities.constants import ES_NONE, TIMEOUT_30MIN
from utilities.constants.hco import DISABLE_MDEV_CONFIGURATION, FEATURE_GATES
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import label_nodes
from utilities.storage import (
    create_dv,
    generate_data_source_dict,
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


@pytest.fixture(scope="session")
def hco_with_disable_mdev_configuration_session_scope(hyperconverged_resource_scope_session):
    """
    Enable disableMDevConfiguration feature gate in HCO.

    This fixture must run before any vGPU node labeling to ensure CNV
    does not configure mediated devices (vGPU configuration is handled
    by NVIDIA GPU Operator).
    """
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_session: {"spec": {FEATURE_GATES: {DISABLE_MDEV_CONFIGURATION: True}}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="session")
def gpu_nodes_labeled_with_vgpu_config_session_scope(
    hco_with_disable_mdev_configuration_session_scope,
    nodes_with_supported_gpus,
    supported_gpu_device,
):
    yield from label_nodes(
        nodes=nodes_with_supported_gpus,
        labels={VGPU_CONFIG_LABEL: supported_gpu_device[MDEV_NAME_STR].split()[-1]},
    )


@pytest.fixture(scope="session")
def gpu_nodes_labeled_with_vm_vgpu_session_scope(
    nodes_with_supported_gpus, gpu_nodes_labeled_with_vgpu_config_session_scope
):
    yield from label_nodes(nodes=nodes_with_supported_gpus, labels={GPU_WORKLOAD_CONFIG_LABEL: "vm-vgpu"})


@pytest.fixture(scope="session")
def nvidia_vgpu_manager_ready_session_scope(
    nvidia_vgpu_manager_ds,
    gpu_nodes_labeled_with_vm_vgpu_session_scope,
):
    """Wait until nvidia-vgpu-manager DaemonSet is ready on all vGPU nodes."""
    wait_for_nvidia_vgpu_manager(
        nvidia_vgpu_manager_ds=nvidia_vgpu_manager_ds,
        nodes_with_supported_gpus=gpu_nodes_labeled_with_vm_vgpu_session_scope,
    )
    yield nvidia_vgpu_manager_ds


@pytest.fixture(scope="session")
def vgpu_ready_nodes_session_scope(
    gpu_nodes,
    nodes_with_supported_gpus,
    gpu_nodes_labeled_with_vm_vgpu_session_scope,
    nvidia_vgpu_manager_ready_session_scope,
    nvidia_sandbox_validator_ds,
    nvidia_vgpu_device_manager_ds,
):
    with vgpu_node_labels_applied(
        gpu_nodes=gpu_nodes,
        nodes_with_supported_gpus=nodes_with_supported_gpus,
        labeled_nodes=gpu_nodes_labeled_with_vm_vgpu_session_scope,
        sandbox_validator_ds=nvidia_sandbox_validator_ds,
        vgpu_device_manager_ds=nvidia_vgpu_device_manager_ds,
    ) as nodes:
        yield nodes


@pytest.fixture(scope="session")
def non_existent_mdev_bus_nodes_session_scope(workers_utility_pods, vgpu_ready_nodes_session_scope):
    """Verify mdev_bus is available on all vGPU nodes."""
    verify_mdev_bus_available(
        workers_utility_pods=workers_utility_pods,
        vgpu_nodes=vgpu_ready_nodes_session_scope,
    )
    yield vgpu_ready_nodes_session_scope
