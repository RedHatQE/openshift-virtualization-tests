import pytest

from utilities.constants import LINUX_BRIDGE
from utilities.infra import get_node_selector_dict
from utilities.network import compose_cloud_init_data_dict, network_device, network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body


@pytest.fixture()
def linux_bridge_nad(namespace):
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name="br1-nad",
        interface_name="br1bridge",
        tuning=True,
    ) as nad:
        yield nad


@pytest.fixture()
def linux_bridge_device(worker_node1, linux_bridge_nad):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="cnv-tuning-nncp",
        interface_name=linux_bridge_nad.bridge_name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as dev:
        yield dev


@pytest.fixture()
def cnv_tuning_vm(unprivileged_client, worker_node1, linux_bridge_nad, linux_bridge_device):
    name = "tuning-vma"
    networks = {"net1": linux_bridge_nad.name}
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.1/24"]}}}

    with VirtualMachineForTests(
        namespace=linux_bridge_nad.namespace,
        name=name,
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        cloud_init_data=compose_cloud_init_data_dict(
            network_data=network_data_data,
        ),
    ) as vm:
        yield vm


@pytest.mark.polarion("CNV-7287")
@pytest.mark.ipv4
@pytest.mark.s390x
def test_vm_cnv_tuning_regression(cnv_tuning_vm):
    cnv_tuning_vm.start(wait=True)
    cnv_tuning_vm.wait_for_agent_connected()
