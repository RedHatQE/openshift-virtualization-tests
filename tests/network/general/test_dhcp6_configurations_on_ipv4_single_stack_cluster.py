import logging

import pytest

from utilities.constants import OS_FLAVOR_CIRROS, Images
from utilities.infra import get_node_selector_dict
from utilities.virt import CIRROS_IMAGE, VirtualMachineForTests, running_vm

DHCPV6_PORT = 547
VM_CIRROS = "vm-cirros"
LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def vm_cirros(
    worker_node1,
    unprivileged_client,
    namespace,
):
    with VirtualMachineForTests(
        name=VM_CIRROS,
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_CIRROS,
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
        image=CIRROS_IMAGE,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture(scope="module")
def fail_if_not_ipv4_single_stack_cluster(ipv4_supported_cluster, ipv6_supported_cluster):
    if not ipv4_supported_cluster or ipv6_supported_cluster:
        pytest.fail(reason="Test should only run on an IPv4 single-stack cluster")


@pytest.fixture()
def virt_launcher_pid(worker_node1_pod_executor, vm_cirros):
    """
    Find the compute container (outcome of the VM created for this test) and extract the vm_cirros virt-launcher PID.
    """
    crictl_cmd = "sudo crictl"
    compute_containers = worker_node1_pod_executor.exec(command=f"{crictl_cmd} ps --name compute -q")
    assert compute_containers, "No compute container was found!"

    for container in compute_containers.split("\n"):
        if vm_cirros.name in worker_node1_pod_executor.exec(
            command=f'{crictl_cmd} inspect {container} | grep "hostname"'
        ):
            vm_cirros_compute_container = container
            break

    return worker_node1_pod_executor.exec(
        command=f"{crictl_cmd} inspect --output go-template --template {{{{.info.pid}}}} {vm_cirros_compute_container}"
    )


@pytest.fixture()
def listening_dhcpv6_pid_in_virt_launcher_pod(worker_node1_pod_executor, virt_launcher_pid):
    """
    Enter the VMI virt-launcher Linux-network-namespace using the nsenter command.
    Find processes that listens to the network traffic.
    The ss command (socket statistics) allows showing information similar to netstat.
    https://man7.org/linux/man-pages/man8/ss.8.html
    """
    return worker_node1_pod_executor.exec(
        command=f"sudo nsenter -t {virt_launcher_pid} -n sudo ss -tunlp | grep {DHCPV6_PORT}",
        ignore_rc=True,
    )


@pytest.mark.polarion("CNV-7407")
@pytest.mark.ipv4
def test_dhcp6_disabled_on_ipv4_single_stack_cluster(
    fail_if_not_ipv4_single_stack_cluster,
    vm_cirros,
    listening_dhcpv6_pid_in_virt_launcher_pod,
):
    """
    Verify that DHCP6 is not initiated on virt-launcher pods on an IPv4 single-stack cluster.
    """
    LOGGER.info(
        f"Checking if the process {listening_dhcpv6_pid_in_virt_launcher_pod} is listening to the port {DHCPV6_PORT}"
    )
    assert not listening_dhcpv6_pid_in_virt_launcher_pod, "DHCPv6 is not disabled on this IPv4-single-stack cluster!"
