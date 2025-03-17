import logging

import pytest
from bitmath import parse_string_unsafe
from ocp_resources.performance_profile import PerformanceProfile

from utilities.constants import AMD, INTEL
from utilities.infra import exit_pytest_execution
from utilities.virt import get_nodes_gpu_info

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def virt_special_infra_sanity(
    request,
    junitxml_plugin,
    is_psi_cluster,
    schedulable_nodes,
    gpu_nodes,
    nodes_with_supported_gpus,
    sriov_workers,
    workers,
):
    """Performs verification that cluster has all required capabilities for virt special_infra marked tests."""

    def _verify_not_psi_cluster(_is_psi_cluster):
        LOGGER.info("Verify running on BM cluster")
        if _is_psi_cluster:
            failed_verifications_list.append("Cluster should be BM and not PSI")

    def _verify_cpumanager_workers(_schedulable_nodes):
        LOGGER.info("Verify cluster nodes have CPU Manager labels")
        if not any([node.labels.cpumanager == "true" for node in _schedulable_nodes]):
            failed_verifications_list.append("Cluster does't have CPU Manager")

    def _verify_gpu(_gpu_nodes, _nodes_with_supported_gpus):
        LOGGER.info("Verify cluster nodes have enough supported GPU cards")
        if not _gpu_nodes:
            failed_verifications_list.append("Cluster doesn't have any GPU nodes")
        if not _nodes_with_supported_gpus:
            failed_verifications_list.append("Cluster doesn't have any nodes with supported GPUs")
        if len(_nodes_with_supported_gpus) < 2:
            failed_verifications_list.append(f"Cluster has only {len(_nodes_with_supported_gpus)} node with GPU")

    def _verfify_no_dpdk():
        LOGGER.info("Verify cluster doesn't have DPDK enabled")
        if PerformanceProfile(name="dpdk").exists:
            failed_verifications_list.append("Cluster has DPDK enabled (DPDK is incomatible with NVIDIA GPU)")

    def _verify_sriov(_sriov_workers):
        LOGGER.info("Verify cluster has worker node with SR-IOV card")
        if not _sriov_workers:
            failed_verifications_list.append("Cluster does not have any SR-IOV workers")

    def _verify_evmcs_support(_schedulable_nodes):
        LOGGER.info("Verify cluster nodes support VMX cpu fixture")
        for node in _schedulable_nodes:
            if not any([
                label == "cpu-feature.node.kubevirt.io/vmx" and value == "true" for label, value in node.labels.items()
            ]):
                failed_verifications_list.append("Cluster does not have any node that supports VMX cpu feature")

    def _verify_hugepages_1gi(_workers):
        LOGGER.info("Verify cluster has 1Gi hugepages enabled")
        if not any([
            parse_string_unsafe(worker.instance.status.allocatable["hugepages-1Gi"]) >= parse_string_unsafe("1Gi")
            for worker in _workers
        ]):
            failed_verifications_list.append("Cluster does not have hugepages-1Gi")

    skip_virt_sanity_check = "--skip-virt-sanity-check"
    failed_verifications_list = []

    if not request.session.config.getoption(skip_virt_sanity_check):
        LOGGER.info("Verifying that cluster has all required capabilities for special_infra marked tests")
        if any(item.get_closest_marker("high_resource_vm") for item in request.session.items):
            _verify_not_psi_cluster(_is_psi_cluster=is_psi_cluster)
            _verify_evmcs_support(_schedulable_nodes=schedulable_nodes)
        if any(item.get_closest_marker("cpu_manager") for item in request.session.items):
            _verify_cpumanager_workers(_schedulable_nodes=schedulable_nodes)
        if any(item.get_closest_marker("gpu") for item in request.session.items):
            _verify_gpu(_gpu_nodes=gpu_nodes, _nodes_with_supported_gpus=nodes_with_supported_gpus)
            _verfify_no_dpdk()
        if any(item.get_closest_marker("sriov") for item in request.session.items):
            _verify_sriov(_sriov_workers=sriov_workers)
        if any(item.get_closest_marker("hugepages") for item in request.session.items):
            _verify_hugepages_1gi(_workers=workers)
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
