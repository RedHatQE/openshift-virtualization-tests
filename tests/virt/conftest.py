import collections
import logging
import shlex

import bitmath
import pytest
from bitmath import parse_string_unsafe
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.performance_profile import PerformanceProfile
from ocp_resources.storage_profile import StorageProfile
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.gpu.constants import (
    GPU_CARDS_MAP,
    NVIDIA_VGPU_MANAGER_DS,
)
from tests.virt.node.gpu.utils import (
    wait_for_manager_pods_deployed,
)
from tests.virt.utils import (
    get_allocatable_memory_per_node,
    get_non_terminated_pods,
    get_pod_memory_requests,
    patch_hco_cr_with_mdev_permitted_hostdevices,
)
from utilities.constants import AMD, INTEL, TIMEOUT_1MIN, TIMEOUT_5SEC, NamespacesNames
from utilities.exceptions import UnsupportedGPUDeviceError
from utilities.infra import ExecCommandOnPod, exit_pytest_execution, label_nodes
from utilities.virt import get_nodes_gpu_info

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def virt_special_infra_sanity(
    request,
    admin_client,
    junitxml_plugin,
    is_psi_cluster,
    schedulable_nodes,
    gpu_nodes,
    nodes_with_supported_gpus,
    sriov_workers,
    workers,
    nodes_cpu_virt_extension,
    workers_utility_pods,
    allocatable_memory_per_node_scope_session,
):
    """Performs verification that cluster has all required capabilities based on collected tests."""

    def _verify_not_psi_cluster(_is_psi_cluster):
        LOGGER.info("Verifying tests run on BM cluster")
        if _is_psi_cluster:
            failed_verifications_list.append("Cluster should be BM and not PSI")

    def _verify_cpumanager_workers(_schedulable_nodes):
        LOGGER.info("Verifing cluster nodes have CPU Manager labels")
        if not any([node.labels.cpumanager == "true" for node in _schedulable_nodes]):
            failed_verifications_list.append("Cluster does't have CPU Manager")

    def _verify_gpu(_gpu_nodes, _nodes_with_supported_gpus):
        LOGGER.info("Verifing cluster nodes have enough supported GPU cards")
        if not _gpu_nodes:
            failed_verifications_list.append("Cluster doesn't have any GPU nodes")
        if not _nodes_with_supported_gpus:
            failed_verifications_list.append("Cluster doesn't have any nodes with supported GPUs")
        if len(_nodes_with_supported_gpus) < 2:
            failed_verifications_list.append(f"Cluster has only {len(_nodes_with_supported_gpus)} node with GPU")

    def _verfify_no_dpdk():
        LOGGER.info("Verifing cluster doesn't have DPDK enabled")
        if PerformanceProfile(name="dpdk").exists:
            failed_verifications_list.append("Cluster has DPDK enabled (DPDK is incomatible with NVIDIA GPU)")

    def _verify_sriov(_sriov_workers):
        LOGGER.info("Verifing cluster has worker node with SR-IOV card")
        if not _sriov_workers:
            failed_verifications_list.append("Cluster does not have any SR-IOV workers")

    def _verify_hw_virtualization(_schedulable_nodes, _nodes_cpu_virt_extension):
        if _nodes_cpu_virt_extension:
            LOGGER.info(f"Verifing cluster nodes support {_nodes_cpu_virt_extension.upper()} cpu fixture")
            for node in _schedulable_nodes:
                if not any([
                    label == f"cpu-feature.node.kubevirt.io/{_nodes_cpu_virt_extension}" and value == "true"
                    for label, value in node.labels.items()
                ]):
                    failed_verifications_list.append(
                        f"Cluster does not have any node that supports {_nodes_cpu_virt_extension.upper()} cpu feature"
                    )
        else:
            failed_verifications_list.append(
                "Hardware virtualization related tests are supported only on cluster with INTEL/AMD based CPUs"
            )

    def _verify_hugepages_1gi(_workers):
        LOGGER.info("Verifing cluster has 1Gi hugepages enabled")
        if not any([
            parse_string_unsafe(worker.instance.status.allocatable["hugepages-1Gi"]) >= parse_string_unsafe("1Gi")
            for worker in _workers
        ]):
            failed_verifications_list.append("Cluster does not have hugepages-1Gi")

    def _verify_rwx_default_storage():
        storage_class = py_config["default_storage_class"]
        LOGGER.info(f"Verifing default storage class {storage_class} supports RWX mode")
        access_modes = StorageProfile(name=storage_class).first_claim_property_set_access_modes()
        if not access_modes or access_modes[0] != DataVolume.AccessMode.RWX:
            failed_verifications_list.append(f"Default storage class {storage_class} doesn't support RWX mode")

    def _verify_descheduler_operator_installed():
        descheduler_deployment = Deployment(
            name="descheduler-operator",
            namespace=NamespacesNames.OPENSHIFT_KUBE_DESCHEDULER_OPERATOR,
            client=admin_client,
        )
        if not descheduler_deployment.exists or descheduler_deployment.instance.status.readyReplicas == 0:
            failed_verifications_list.append("kube-descheduler operator is not working on the cluster")

    def _verify_psi_kernel_argument(_workers_utility_pods):
        for pod in _workers_utility_pods:
            if "psi=1" not in pod.execute(command=shlex.split("cat /proc/cmdline")):
                failed_verifications_list.append(f"Node {pod.node.name} does not have psi=1 kernel argument")

    def _verify_if_1tb_memory_or_more_node(_memory_per_node):
        """
        Descheduler tests should run on nodes with less than 1Tb of memory.
        """
        upper_memory_limit = bitmath.TiB(value=1)
        for node, memory in _memory_per_node.items():
            if memory >= upper_memory_limit:
                failed_verifications_list.append(f"Cluster has node with more than 1Tb of memory: {node.name}")

    skip_virt_sanity_check = "--skip-virt-sanity-check"
    failed_verifications_list = []

    if not request.session.config.getoption(skip_virt_sanity_check):
        LOGGER.info("Verifying that cluster has all required capabilities for special_infra marked tests")
        if any(item.get_closest_marker("high_resource_vm") for item in request.session.items):
            _verify_not_psi_cluster(_is_psi_cluster=is_psi_cluster)
            _verify_hw_virtualization(
                _schedulable_nodes=schedulable_nodes, _nodes_cpu_virt_extension=nodes_cpu_virt_extension
            )
        if any(item.get_closest_marker("cpu_manager") for item in request.session.items):
            _verify_cpumanager_workers(_schedulable_nodes=schedulable_nodes)
        if any(item.get_closest_marker("gpu") for item in request.session.items):
            _verify_gpu(_gpu_nodes=gpu_nodes, _nodes_with_supported_gpus=nodes_with_supported_gpus)
            _verfify_no_dpdk()
        if any(item.get_closest_marker("sriov") for item in request.session.items):
            _verify_sriov(_sriov_workers=sriov_workers)
        if any(item.get_closest_marker("hugepages") for item in request.session.items):
            _verify_hugepages_1gi(_workers=workers)
        if any(item.get_closest_marker("rwx_default_storage") for item in request.session.items):
            _verify_rwx_default_storage()
        if any(item.get_closest_marker("descheduler") for item in request.session.items):
            _verify_descheduler_operator_installed()
            _verify_psi_kernel_argument(_workers_utility_pods=workers_utility_pods)
            _verify_if_1tb_memory_or_more_node(_memory_per_node=allocatable_memory_per_node_scope_session)
    else:
        LOGGER.warning(f"Skipping virt special infra sanity because {skip_virt_sanity_check} was passed")

    if failed_verifications_list:
        err_msg = "\n".join(failed_verifications_list)
        LOGGER.error(f"Special_infra cluster verification failed! Missing components:\n{err_msg}")
        exit_pytest_execution(
            message=err_msg,
            return_code=98,
            filename="virt_special_infra_sanity_failure.txt",
            junitxml_property=junitxml_plugin,
        )


@pytest.fixture(scope="session")
def nodes_with_supported_gpus(gpu_nodes, workers_utility_pods):
    gpu_nodes_copy = gpu_nodes.copy()
    for node in gpu_nodes:
        # Currently A30/A100 GPU is unsupported by CNV (required driver not supported)
        if "A30" in get_nodes_gpu_info(util_pods=workers_utility_pods, node=node):
            gpu_nodes_copy.remove(node)
    return gpu_nodes_copy


@pytest.fixture(scope="session")
def nodes_cpu_virt_extension(nodes_cpu_vendor):
    if nodes_cpu_vendor == INTEL:
        return "vmx"
    elif nodes_cpu_vendor == AMD:
        return "svm"
    else:
        return None


@pytest.fixture(scope="session")
def vm_cpu_flags(nodes_cpu_virt_extension):
    return (
        {
            "features": [
                {
                    "name": nodes_cpu_virt_extension,
                    "policy": "require",
                }
            ]
        }
        if nodes_cpu_virt_extension
        else None
    )


@pytest.fixture(scope="session")
def supported_gpu_device(workers_utility_pods, nodes_with_supported_gpus):
    gpu_info = get_nodes_gpu_info(util_pods=workers_utility_pods, node=nodes_with_supported_gpus[0])
    for gpu_id in GPU_CARDS_MAP:
        if gpu_id in gpu_info:
            return GPU_CARDS_MAP[gpu_id]

    raise UnsupportedGPUDeviceError("GPU device ID not in current GPU_CARDS_MAP!")


@pytest.fixture(scope="session")
def hco_cr_with_mdev_permitted_hostdevices_scope_session(hyperconverged_resource_scope_session, supported_gpu_device):
    yield from patch_hco_cr_with_mdev_permitted_hostdevices(
        hyperconverged_resource=hyperconverged_resource_scope_session, supported_gpu_device=supported_gpu_device
    )


@pytest.fixture(scope="session")
def gpu_nodes_labeled_with_vm_vgpu(nodes_with_supported_gpus):
    yield from label_nodes(nodes=nodes_with_supported_gpus, labels={"nvidia.com/gpu.workload.config": "vm-vgpu"})


@pytest.fixture(scope="session")
def vgpu_ready_nodes(admin_client, gpu_nodes_labeled_with_vm_vgpu):
    wait_for_manager_pods_deployed(admin_client=admin_client, ds_name=NVIDIA_VGPU_MANAGER_DS)
    yield gpu_nodes_labeled_with_vm_vgpu


@pytest.fixture(scope="session")
def non_existent_mdev_bus_nodes(workers_utility_pods, vgpu_ready_nodes):
    """
    Check if the mdev_bus needed for vGPU is available.

    On the Worker Node on which GPU Device exists, check if the
    mdev_bus needed for vGPU is available.
    If it's not available, this means the nvidia-vgpu-manager-daemonset
    Pod might not be in running state in the nvidia-gpu-operator namespace.
    """
    desired_bus = "mdev_bus"
    non_existent_mdev_bus_nodes = []
    for node in vgpu_ready_nodes:
        pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
        try:
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_1MIN,
                sleep=TIMEOUT_5SEC,
                func=pod_exec.exec,
                command=f"ls /sys/class | grep {desired_bus} || true",
            ):
                if sample:
                    return
        except TimeoutExpiredError:
            non_existent_mdev_bus_nodes.append(node.name)
    if non_existent_mdev_bus_nodes:
        pytest.fail(
            reason=(
                f"On these nodes: {non_existent_mdev_bus_nodes} {desired_bus} is not available."
                "Ensure that in 'nvidia-gpu-operator' namespace nvidia-vgpu-manager-daemonset Pod is Running."
            )
        )


@pytest.fixture(scope="session")
def allocatable_memory_per_node_scope_session(schedulable_nodes):
    return get_allocatable_memory_per_node(schedulable_nodes=schedulable_nodes)


@pytest.fixture(scope="class")
def allocatable_memory_per_node_scope_class(schedulable_nodes):
    return get_allocatable_memory_per_node(schedulable_nodes=schedulable_nodes)


@pytest.fixture(scope="class")
def non_terminated_pods_per_node(admin_client, schedulable_nodes):
    return {node: get_non_terminated_pods(client=admin_client, node=node) for node in schedulable_nodes}


@pytest.fixture(scope="class")
def memory_requests_per_node(schedulable_nodes, non_terminated_pods_per_node):
    memory_requests = collections.defaultdict(bitmath.Byte)
    for node in schedulable_nodes:
        for pod in non_terminated_pods_per_node[node]:
            pod_instance = pod.exists
            if pod_instance:
                memory_requests[node] += get_pod_memory_requests(pod_instance=pod_instance)
    LOGGER.info(f"memory_requests collection: {memory_requests}")
    return memory_requests


@pytest.fixture(scope="class")
def available_memory_per_node(
    schedulable_nodes,
    allocatable_memory_per_node_scope_class,
    memory_requests_per_node,
):
    return {
        node: allocatable_memory_per_node_scope_class[node] - memory_requests_per_node[node]
        for node in schedulable_nodes
    }


@pytest.fixture(scope="class")
def node_with_most_available_memory(available_memory_per_node):
    return max(available_memory_per_node, key=available_memory_per_node.get)


@pytest.fixture(scope="class")
def node_with_least_available_memory(available_memory_per_node):
    return min(available_memory_per_node, key=available_memory_per_node.get)
