"""
Connectivity over Linux_Bond on Default Interface
"""

import logging
import subprocess

import pytest
from timeout_sampler import TimeoutSampler

from tests.network.utils import wait_for_address_on_iface
from utilities.constants import TIMEOUT_10MIN
from utilities.infra import ExecCommandOnPod, get_node_selector_dict
from utilities.network import BondNodeNetworkConfigurationPolicy, assert_ping_successful
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

LOGGER = logging.getLogger(__name__)
SLEEP = 5


pytestmark = pytest.mark.usefixtures("workers_type", "skip_if_ovn_cluster")


@pytest.fixture(scope="class")
def lbodi_vma(worker_node1, namespace, unprivileged_client):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def lbodi_vmb(worker_node2, namespace, unprivileged_client):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def lbodi_running_vma(lbodi_vma):
    return running_vm(vm=lbodi_vma)


@pytest.fixture(scope="class")
def lbodi_running_vmb(lbodi_vmb):
    return running_vm(vm=lbodi_vmb)


@pytest.fixture(scope="class")
def lbodi_bond(
    index_number,
    skip_no_bond_support,
    nodes_available_nics,
    nodes_occupied_nics,
    worker_node1,
    worker_nodes_ipv4_false_secondary_nics,
):
    """
    Create BOND if setup support BOND
    """
    bond_idx = next(index_number)
    primary_port = nodes_occupied_nics[worker_node1.name][0]
    with BondNodeNetworkConfigurationPolicy(
        name=f"lbodi-bond{bond_idx}nncp",
        bond_name=f"lbodi-bond{bond_idx}",
        bond_ports=[primary_port, nodes_available_nics[worker_node1.name][-1]],
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ipv4_dhcp=True,
        ipv4_enable=True,
        primary_bond_port=primary_port,
    ) as bond:
        yield bond


@pytest.fixture(scope="class")
def lbodi_pod_with_bond(workers_utility_pods, lbodi_bond):
    """
    Returns:
        The specific pod on the worker node with the bond
    """
    for pod in workers_utility_pods:
        if pod.node.name == lbodi_bond.node_selector:
            return pod


@pytest.mark.destructive
class TestBondConnectivityWithNodesDefaultInterface:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-3432")
    def test_bond_config(
        self,
        skip_no_bond_support,
        namespace,
        lbodi_bond,
        lbodi_pod_with_bond,
    ):
        """
        Check that bond interface exists on the specific worker node,
        in Up state and has valid IP address.
        """
        bond_ip = wait_for_address_on_iface(
            worker_pod=lbodi_pod_with_bond,
            iface_name=lbodi_bond.bond_name,
        )
        # Check connectivity
        assert subprocess.check_output(["ping", "-c", "1", bond_ip])

    @pytest.mark.gating
    @pytest.mark.polarion("CNV-3433")
    def test_vm_connectivity_over_linux_bond(
        self,
        skip_when_one_node,
        skip_no_bond_support,
        namespace,
        lbodi_bond,
        lbodi_vma,
        lbodi_vmb,
        lbodi_running_vma,
        lbodi_running_vmb,
    ):
        """
        Check connectivity from each VM
        to the default interface of the other VM.
        """
        vma_ip = lbodi_running_vma.vmi.virt_launcher_pod.instance.status.podIP
        vmb_ip = lbodi_running_vmb.vmi.virt_launcher_pod.instance.status.podIP
        for vm, ip in zip(
            [lbodi_running_vma, lbodi_running_vmb],
            [vmb_ip, vma_ip],
        ):
            assert_ping_successful(src_vm=vm, dst_ip=ip)

    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-3439")
    def test_bond_and_persistence(
        self,
        skip_when_one_node,
        skip_no_bond_support,
        namespace,
        workers_utility_pods,
        lbodi_bond,
        lbodi_pod_with_bond,
    ):
        """
        Verify bond interface status and persistence after reboot
        """
        node = lbodi_bond.node_selector
        pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
        wait_for_address_on_iface(
            worker_pod=lbodi_pod_with_bond,
            iface_name=lbodi_bond.bond_name,
        )

        # REBOOT - Check persistence
        assert pod_exec.reboot, f"Fail to reboot {node}"

        LOGGER.info(f"Wait until {lbodi_bond.node_selector} reboots ...")
        samples = TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=SLEEP,
            func=pod_exec.is_connective,
        )
        for sample in samples:
            if sample:
                break

        wait_for_address_on_iface(
            worker_pod=lbodi_pod_with_bond,
            iface_name=lbodi_bond.bond_name,
        )
