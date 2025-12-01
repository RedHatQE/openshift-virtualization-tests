"""
SR-IOV Tests
"""

import logging
import re
import shlex

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.template import Template
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutSampler

from tests.network.libs.ip import random_ipv4_address
from utilities.constants import (
    CNV_SUPPLEMENTAL_TEMPLATES_URL,
    MTU_9000,
    SRIOV,
    TIMEOUT_10MIN,
    TIMEOUT_20SEC,
)
from utilities.infra import get_node_selector_dict
from utilities.network import (
    cloud_init_network_data,
    network_nad,
    sriov_network_dict,
)
from utilities.ssp import create_custom_template_from_url
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    running_vm,
    wait_for_vm_interfaces,
)

LOGGER = logging.getLogger(__name__)
VM_SRIOV_IFACE_NAME = "sriov1"
NODE_HUGE_PAGES_1GI_KEY = "hugepages-1Gi"


def vm_sriov_mac(mac_suffix_index):
    return f"02:00:b5:b5:b5:{mac_suffix_index:02x}"


def sriov_vm(
    mac_suffix_index,
    unprivileged_client,
    name,
    namespace,
    ip_config,
    sriov_network,
    worker=None,
):
    sriov_mac = vm_sriov_mac(mac_suffix_index=mac_suffix_index)
    network_data_data = {
        "ethernets": {
            "1": {
                "addresses": [ip_config],
                "match": {"macaddress": sriov_mac},
                "set-name": VM_SRIOV_IFACE_NAME,
            }
        }
    }
    networks = sriov_network_dict(namespace=namespace, network=sriov_network)
    cloud_init_data = cloud_init_network_data(data=network_data_data)

    vm_kwargs = {
        "namespace": namespace.name,
        "name": name,
        "body": fedora_vm_body(name=name),
        "networks": networks,
        "interfaces": networks.keys(),
        "cloud_init_data": cloud_init_data,
        "client": unprivileged_client,
        "macs": {sriov_network.name: sriov_mac},
        "interfaces_types": {name: SRIOV for name in networks.keys()},
    }

    if worker:
        vm_kwargs["node_selector"] = get_node_selector_dict(node_selector=worker.name)
    with VirtualMachineForTests(**vm_kwargs) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="module")
def sriov_network(admin_client, sriov_node_policy, namespace, sriov_namespace):
    """
    Create a SR-IOV network linked to SR-IOV policy.
    """
    with network_nad(
        client=admin_client,
        nad_type=SRIOV,
        nad_name="sriov-test-network",
        sriov_resource_name=sriov_node_policy.resource_name,
        namespace=sriov_namespace,
        sriov_network_namespace=namespace.name,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def sriov_network_vlan(admin_client, sriov_node_policy, namespace, sriov_namespace, vlan_index_number):
    """
    Create a SR-IOV VLAN network linked to SR-IOV policy.
    """
    with network_nad(
        nad_type=SRIOV,
        nad_name="sriov-test-network-vlan",
        sriov_resource_name=sriov_node_policy.resource_name,
        namespace=sriov_namespace,
        sriov_network_namespace=namespace.name,
        vlan=next(vlan_index_number),
        client=admin_client,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="class")
def sriov_vm1(index_number, sriov_workers_node1, namespace, unprivileged_client, sriov_network):
    yield from sriov_vm(
        mac_suffix_index=next(index_number),
        unprivileged_client=unprivileged_client,
        name="sriov-vm1",
        namespace=namespace,
        worker=sriov_workers_node1,
        ip_config=f"{random_ipv4_address(net_seed=0, host_address=1)}/24",
        sriov_network=sriov_network,
    )


@pytest.fixture(scope="class")
def sriov_vm2(index_number, unprivileged_client, sriov_workers_node2, namespace, sriov_network):
    yield from sriov_vm(
        mac_suffix_index=next(index_number),
        unprivileged_client=unprivileged_client,
        name="sriov-vm2",
        namespace=namespace,
        worker=sriov_workers_node2,
        ip_config=f"{random_ipv4_address(net_seed=0, host_address=2)}/24",
        sriov_network=sriov_network,
    )


@pytest.fixture(scope="class")
def sriov_vm3(
    index_number,
    sriov_workers_node1,
    namespace,
    unprivileged_client,
    sriov_network_vlan,
):
    yield from sriov_vm(
        mac_suffix_index=next(index_number),
        unprivileged_client=unprivileged_client,
        name="sriov-vm3",
        namespace=namespace,
        worker=sriov_workers_node1,
        ip_config=f"{random_ipv4_address(net_seed=1, host_address=1)}/24",
        sriov_network=sriov_network_vlan,
    )


@pytest.fixture(scope="class")
def sriov_vm4(
    index_number,
    sriov_workers_node2,
    namespace,
    unprivileged_client,
    sriov_network_vlan,
):
    yield from sriov_vm(
        mac_suffix_index=next(index_number),
        unprivileged_client=unprivileged_client,
        name="sriov-vm4",
        namespace=namespace,
        worker=sriov_workers_node2,
        ip_config=f"{random_ipv4_address(net_seed=1, host_address=2)}/24",
        sriov_network=sriov_network_vlan,
    )


@pytest.fixture(scope="class")
def vm4_interfaces(sriov_vm4):
    sampler = TimeoutSampler(wait_timeout=60, sleep=10, func=lambda: sriov_vm4.vmi.interfaces)
    for sample in sampler:
        if len(sample) == 2:
            # 2 is used to make sure that number of interfaces before reboot are 2 then proceed.
            # Later this will be compared with number of interfaces after reboot.
            return sample
        wait_for_vm_interfaces(vmi=sriov_vm4.vmi)


@pytest.fixture(params=list(range(1, 6)))
def restarted_sriov_vm4(request, sriov_vm4):
    LOGGER.info(f"Reboot number {request.param}")
    sriov_vm4.restart(wait=True)
    sriov_vm4.wait_for_agent_connected()
    wait_for_vm_interfaces(vmi=sriov_vm4.vmi)
    return sriov_vm4


def get_vm_sriov_network_mtu(vm):
    return int(
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=[shlex.split(f"cat /sys/class/net/{VM_SRIOV_IFACE_NAME}/mtu")],
        )[0]
    )


def set_vm_sriov_network_mtu(vm, mtu):
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[shlex.split(f"sudo ip link set {VM_SRIOV_IFACE_NAME} mtu {mtu}")],
    )
    LOGGER.info(f"wait for {vm.name} {VM_SRIOV_IFACE_NAME} mtu to be {mtu}")
    for sample in TimeoutSampler(wait_timeout=30, sleep=1, func=get_vm_sriov_network_mtu, vm=vm):
        if sample == mtu:
            return


@pytest.fixture()
def sriov_network_mtu_9000(sriov_vm1, sriov_vm2):
    vms = (sriov_vm1, sriov_vm2)
    default_mtu = (
        get_vm_sriov_network_mtu(vm=sriov_vm1),
        get_vm_sriov_network_mtu(vm=sriov_vm2),
    )
    for vm in vms:
        set_vm_sriov_network_mtu(vm=vm, mtu=MTU_9000)
    yield
    for vm, mtu in zip(vms, default_mtu):
        set_vm_sriov_network_mtu(vm=vm, mtu=mtu)


@pytest.fixture(scope="class")
def sriov_vm_migrate(index_number, unprivileged_client, namespace, sriov_network):
    yield from sriov_vm(
        mac_suffix_index=next(index_number),
        unprivileged_client=unprivileged_client,
        name="sriov-vm-migrate",
        namespace=namespace,
        ip_config=f"{random_ipv4_address(net_seed=0, host_address=3)}/24",
        sriov_network=sriov_network,
    )


@pytest.fixture(scope="class")
def dpdk_template(namespace, tmpdir_factory):
    template_dir = tmpdir_factory.mktemp("dpdk_template")
    with create_custom_template_from_url(
        url=f"{CNV_SUPPLEMENTAL_TEMPLATES_URL}/testpmd/resource-specs/sriov-vm1-template.yaml",
        template_name="dpdk_vm_template.yaml",
        template_dir=template_dir,
        namespace=namespace.name,
    ) as template:
        yield template


@pytest.fixture(scope="class")
def sriov_dpdk_vm1(
    dpdk_template,
    index_number,
    sriov_worker_with_allocatable_1gi_huge_pages,
    unprivileged_client,
    sriov_network,
):
    # No need to pass cloud_init_data, networks, interfaces and interfaces_types.
    # The template already contains these definitions
    with VirtualMachineForTestsFromTemplate(
        name="sriov-dpdk-vm1",
        namespace=dpdk_template.namespace,
        client=unprivileged_client,
        node_selector=get_node_selector_dict(node_selector=sriov_worker_with_allocatable_1gi_huge_pages.hostname),
        template_object=dpdk_template,
        labels=Template.generate_template_labels(
            os="rhel8.4",
            workload=Template.Workload.SERVER,
            flavor=Template.Flavor.MEDIUM,
        ),
        template_params={
            "IMAGE_URL": "docker://quay.io/openshift-cnv/qe-cnv-tests-rhel:8.4-dpdk",
            "SECONDARY_MAC": vm_sriov_mac(mac_suffix_index=next(index_number)),
            "NAMESPACE": dpdk_template.namespace,
        },
        data_volume_template_from_vm_spec=True,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_dpdk_pci_slot(sriov_dpdk_vm1):
    # Retrieve the PCI ID of the de-activated SR-IOV NIC.
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_20SEC,
        func=run_ssh_commands,
        host=sriov_dpdk_vm1.ssh_exec,
        commands=shlex.split("dpdk-devbind.py --status"),
    ):
        dpdk_result = re.search(
            r".*?Network devices using DPDK-compatible driver.*?(\d{4}(:\d{2}){2}.\d)",
            sample[0],
            re.DOTALL,
        )
        if dpdk_result:
            return dpdk_result[1]


@pytest.fixture()
def vm_dpdk_numa_cpu(sriov_dpdk_vm1):
    # Get the CPU list to send to testpmd.
    lscpu_output = run_ssh_commands(
        host=sriov_dpdk_vm1.ssh_exec,
        commands=["lscpu"],
    )[0]

    return re.search(r"NUMA node(\d) CPU\(s\):\s+(?P<numa_cpu>.*)\n.*", lscpu_output)["numa_cpu"]


@pytest.fixture()
def testpmd_output(vm_dpdk_pci_slot, vm_dpdk_numa_cpu, sriov_dpdk_vm1):
    # testpmd starts tracing traffic and waits for <Enter> to exit and output the statistics.
    # A timeout is provided to have enough runtime for traffic to be collected before sending <Enter>
    test_output = run_ssh_commands(
        host=sriov_dpdk_vm1.ssh_exec,
        commands=[
            shlex.split(f"(sleep 30; echo -ne '\n') | sudo dpdk-testpmd  -l {vm_dpdk_numa_cpu} -w {vm_dpdk_pci_slot}")
        ],
    )[0]

    return re.search(r".*?[RX|TX]-total: (\d+).*?", test_output, re.DOTALL).group(1)


@pytest.fixture(scope="session")
def sriov_worker_with_allocatable_1gi_huge_pages(sriov_workers):
    for node in sriov_workers:
        if node.instance.to_dict()["status"]["allocatable"].get(NODE_HUGE_PAGES_1GI_KEY, "").endswith("Gi"):
            return node
    raise ResourceNotFoundError(f"SRIOV worker with {NODE_HUGE_PAGES_1GI_KEY} not found")
