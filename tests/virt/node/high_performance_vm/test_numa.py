import logging

import pytest
from ocp_resources.sriov_network import SriovNetwork

from tests.utils import (
    assert_cpus_and_sriov_on_same_node,
    assert_numa_cpu_allocation,
    assert_virt_launcher_pod_cpu_manager_node_selector,
    get_numa_node_cpu_dict,
    get_vm_cpu_list,
)
from utilities.constants import SRIOV
from utilities.infra import ExecCommandOnPod
from utilities.network import sriov_network_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body

LOGGER = logging.getLogger(__name__)

pytestmark = [pytest.mark.cpu_manager, pytest.mark.numa, pytest.mark.usefixtures("fail_if_no_numa")]


@pytest.fixture(scope="module")
def fail_if_no_numa(schedulable_nodes, workers_utility_pods):
    LOGGER.info("Verify cluster has NUMA")
    cat_cmd = "cat /etc/kubernetes/kubelet.conf"
    single_numa_node_cmd = f"{cat_cmd} | grep -i single-numa-node"
    topology_manager_cmd = f"{cat_cmd} | grep -w TopologyManager"
    for cmd in (single_numa_node_cmd, topology_manager_cmd):
        for node in schedulable_nodes:
            pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
            out = pod_exec.exec(command=cmd, ignore_rc=True)
            if not out:
                pytest.fail(f"Cluster does not have {cmd.split()[-1]} enabled")


@pytest.fixture(scope="module")
def sriov_net(sriov_node_policy, namespace):
    with SriovNetwork(
        name="numa-sriov-test-net",
        namespace=sriov_node_policy.namespace,
        resource_name=sriov_node_policy.resource_name,
        network_namespace=namespace.name,
    ) as net:
        yield net


@pytest.fixture()
def vm_numa(namespace, unprivileged_client):
    name = "vm-numa"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_cores=8,
        cpu_sockets=2,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        cpu_placement=True,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.fixture()
def vm_numa_sriov(namespace, unprivileged_client, sriov_net):
    name = "vm-numa-sriov"
    networks = sriov_network_dict(namespace=namespace, network=sriov_net)
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_cores=8,
        cpu_sockets=2,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        cpu_placement=True,
        networks=networks,
        interfaces=networks.keys(),
        interfaces_types={name: SRIOV for name in networks.keys()},
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.mark.polarion("CNV-4216")
def test_numa(vm_numa):
    numa_pod = vm_numa.vmi.virt_launcher_pod.instance
    pod_limits = numa_pod.spec.containers[0].resources.limits
    pod_requests = numa_pod.spec.containers[0].resources.requests
    vm_cpu_list = get_vm_cpu_list(vm=vm_numa)
    numa_node_dict = get_numa_node_cpu_dict(vm=vm_numa)

    assert pod_limits == pod_requests, (
        f"NUMA Pod has mismatch in resources limits and requests. Limits {pod_limits}, requests {pod_requests}"
    )
    assert numa_pod.status.qosClass == "Guaranteed", (
        f"QOS Class in not Guaranteed. NUMA pod QOS Class {numa_pod.status.qosClass}"
    )
    assert_virt_launcher_pod_cpu_manager_node_selector(virt_launcher_pod=numa_pod)
    assert_numa_cpu_allocation(vm_cpus=vm_cpu_list, numa_nodes=numa_node_dict)


@pytest.mark.sriov
@pytest.mark.polarion("CNV-4309")
def test_numa_with_sriov(
    vm_numa_sriov,
    workers_utility_pods,
):
    assert_cpus_and_sriov_on_same_node(vm=vm_numa_sriov, utility_pods=workers_utility_pods)
