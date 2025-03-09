import logging

import pytest
from bitmath import parse_string_unsafe
from ocp_resources.performance_profile import PerformanceProfile

from utilities.constants import AMD, INTEL
from utilities.infra import ExecCommandOnPod, exit_pytest_execution
from utilities.virt import get_nodes_gpu_info

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def virt_special_infra_sanity(
    pytestconfig,
    junitxml_plugin,
    is_psi_cluster,
    schedulable_nodes,
    gpu_nodes,
    nodes_with_supported_gpus,
    workers_utility_pods,
    sriov_workers,
    workers,
):
    """Performs verification that cluster has all required capabilities for virt special_infra marked tests."""

    def _fail_verification(_message):
        LOGGER.error(f"Special_infra cluster verification failed! {_message}")
        exit_pytest_execution(
            message=_message,
            return_code=98,
            filename="virt_special_infra_sanity_failure.txt",
            junitxml_property=junitxml_plugin,
        )

    def _verify_not_psi_cluster(_is_psi_cluster):
        if _is_psi_cluster:
            _fail_verification(_message="Cluster should be BM and not PSI")

    def _verify_cpumanager_workers(_schedulable_nodes):
        if not any([node.labels.cpumanager == "true" for node in _schedulable_nodes]):
            _fail_verification(_message="Cluster does't have CPU Manager")

    def _verify_gpu(_gpu_nodes, _nodes_with_supported_gpus):
        if not _gpu_nodes:
            _fail_verification(_message="Cluster doesn't have any GPU nodes")
        if not _nodes_with_supported_gpus:
            _fail_verification(_message="Cluster doesn't have any nodes with supported GPUs")
        if len(_nodes_with_supported_gpus) < 2:
            _fail_verification(_message="Cluster has only 1 node with GPU")

    def _verfify_no_dpdk():
        if PerformanceProfile(name="dpdk").exists:
            _fail_verification(_message="Cluster has DPDK enabled (DPDK is incomatible with NVIDIA GPU)")

    def _verify_numa(_schedulable_nodes, _workers_utility_pods):
        cat_cmd = "cat /etc/kubernetes/kubelet.conf"
        single_numa_node_cmd = f"{cat_cmd} | grep -i single-numa-node"
        topology_manager_cmd = f"{cat_cmd} | grep -w TopologyManager"
        for cmd in (single_numa_node_cmd, topology_manager_cmd):
            for node in _schedulable_nodes:
                pod_exec = ExecCommandOnPod(utility_pods=_workers_utility_pods, node=node)
                out = pod_exec.exec(command=cmd, ignore_rc=True)
                if not out:
                    _fail_verification(_message=f"Cluster does not have {cmd.split()[-1]} enabled")

    def _verify_sriov(_sriov_workers):
        if not _sriov_workers:
            _fail_verification(_message="Cluster doesn't have any SR-IOV workers")

    def _verify_evmcs_support(_schedulable_nodes):
        for node in _schedulable_nodes:
            if not any([
                label == "cpu-feature.node.kubevirt.io/vmx" and value == "true" for label, value in node.labels.items()
            ]):
                _fail_verification(_message="Cluster doens't have any node that supports VMX cpu feature")

    def _verify_hugepages_1gi(_workers):
        if not any([
            parse_string_unsafe(worker.instance.status.allocatable["hugepages-1Gi"]) >= parse_string_unsafe("1Gi")
            for worker in _workers
        ]):
            _fail_verification(_message="Cluster doesn't have hugepages-1Gi")

    if "special_infra" in pytestconfig.getoption("-m"):
        LOGGER.info("Verifying that cluster has all required capabilities for special_infra marked tests")
        _verify_not_psi_cluster(_is_psi_cluster=is_psi_cluster)
        _verify_cpumanager_workers(_schedulable_nodes=schedulable_nodes)
        _verify_gpu(_gpu_nodes=gpu_nodes, _nodes_with_supported_gpus=nodes_with_supported_gpus)
        _verfify_no_dpdk()
        _verify_numa(_schedulable_nodes=schedulable_nodes, _workers_utility_pods=workers_utility_pods)
        _verify_sriov(_sriov_workers=sriov_workers)
        _verify_evmcs_support(_schedulable_nodes=schedulable_nodes)
        _verify_hugepages_1gi(_workers=workers)


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
