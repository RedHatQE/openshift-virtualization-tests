import logging
import re
import shlex
from collections import OrderedDict

import pytest
from ocp_resources.resource import ResourceEditor
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutSampler

from utilities.constants import LINUX_BRIDGE, TIMEOUT_30SEC
from utilities.infra import get_node_selector_dict, name_prefix
from utilities.network import (
    assert_ping_successful,
    compose_cloud_init_data_dict,
    get_vmi_ip_v4_by_name,
    network_device,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

ETH1_INTERFACE_NAME = "eth1"
BRIDGE_NAME = "br1macspoof"
MAC_ADDRESS_SPOOF = "02:00:b5:b5:b5:c9"

LOGGER = logging.getLogger(__name__)


def _networks_data(nad, ip):
    networks = OrderedDict()
    networks[nad.name] = f"{nad.name}"
    network_data_data = {
        "ethernets": {
            ETH1_INTERFACE_NAME: {"addresses": [ip]},
        }
    }
    return networks, network_data_data


def get_vm_bridge_network_mac(vm):
    return run_ssh_commands(
        host=vm.ssh_exec,
        commands=[shlex.split(f"cat /sys/class/net/{ETH1_INTERFACE_NAME}/address")],
    )[0].strip()


def set_vm_interface_network_mac(vm, mac):
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[shlex.split(f"sudo ip link set dev {ETH1_INTERFACE_NAME} address {mac}")],
    )
    LOGGER.info(f"wait for {vm.name} {ETH1_INTERFACE_NAME}  mac to be {mac}")
    for sample in TimeoutSampler(wait_timeout=TIMEOUT_30SEC, sleep=1, func=get_vm_bridge_network_mac, vm=vm):
        if sample == mac:
            return


@pytest.fixture(scope="class")
def linux_bridge_device_worker_1(nodes_available_nics, worker_node1):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"bridge-{name_prefix(worker_node1.hostname)}",
        interface_name=BRIDGE_NAME,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.hostname][-1]],
    ) as br_dev:
        yield br_dev


@pytest.fixture(scope="class")
def linux_bridge_device_worker_2(nodes_available_nics, worker_node2):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"bridge-{name_prefix(worker_node2.hostname)}",
        interface_name=BRIDGE_NAME,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[nodes_available_nics[worker_node2.hostname][-1]],
    ) as br_dev:
        yield br_dev


@pytest.fixture(scope="class")
def linux_macspoof_nad(
    namespace,
    linux_bridge_device_worker_1,
    linux_bridge_device_worker_2,
):
    with network_nad(
        namespace=namespace,
        nad_type=linux_bridge_device_worker_1.bridge_type,
        nad_name=linux_bridge_device_worker_1.bridge_name,
        interface_name=linux_bridge_device_worker_1.iface["name"],
        macspoofchk=True,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def linux_bridge_attached_vma(
    worker_node1,
    unprivileged_client,
    linux_macspoof_nad,
):
    name = "vma"
    networks, network_data_data = _networks_data(nad=linux_macspoof_nad, ip="10.200.0.1/24")
    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
    )

    with VirtualMachineForTests(
        namespace=linux_macspoof_nad.namespace,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def linux_bridge_attached_vmb(
    worker_node2,
    unprivileged_client,
    linux_macspoof_nad,
):
    name = "vmb"
    networks, network_data_data = _networks_data(nad=linux_macspoof_nad, ip="10.200.0.2/24")
    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
    )

    with VirtualMachineForTests(
        namespace=linux_macspoof_nad.namespace,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def linux_bridge_attached_running_vma(linux_bridge_attached_vma):
    return running_vm(vm=linux_bridge_attached_vma, wait_for_cloud_init=True)


@pytest.fixture(scope="class")
def linux_bridge_attached_running_vmb(linux_bridge_attached_vmb):
    return running_vm(vm=linux_bridge_attached_vmb, wait_for_cloud_init=True)


@pytest.fixture(scope="class")
def vmb_ip_address(linux_bridge_device_worker_1, linux_bridge_attached_running_vmb):
    return get_vmi_ip_v4_by_name(
        vm=linux_bridge_attached_running_vmb,
        name=linux_bridge_device_worker_1.bridge_name,
    )


@pytest.fixture(scope="class")
def ping_vmb_from_vma(vmb_ip_address, linux_bridge_attached_running_vma):
    assert_ping_successful(
        src_vm=linux_bridge_attached_running_vma,
        dst_ip=vmb_ip_address,
    )


@pytest.fixture()
def vma_interface_spoofed_mac(linux_bridge_attached_vma):
    return set_vm_interface_network_mac(vm=linux_bridge_attached_vma, mac=MAC_ADDRESS_SPOOF)


@pytest.fixture()
def stopped_vms(linux_bridge_attached_running_vma, linux_bridge_attached_running_vmb):
    vms = (linux_bridge_attached_running_vma, linux_bridge_attached_running_vmb)
    for vm in vms:
        vm.stop(wait=True)

    return vms


@pytest.fixture()
def mac_spoof_disabled_nad(linux_macspoof_nad):
    config = linux_macspoof_nad.instance.spec.config
    config = re.sub('"macspoofchk": true', '"macspoofchk": false', config)
    ResourceEditor(
        patches={
            linux_macspoof_nad: {
                "spec": {
                    "config": config,
                }
            }
        }
    ).update()


@pytest.fixture()
def vms_without_mac_spoof(
    stopped_vms,
    mac_spoof_disabled_nad,
):
    for vm in stopped_vms:
        vm.start(wait=True)

    for vm in stopped_vms:
        running_vm(vm=vm, wait_for_cloud_init=True)
