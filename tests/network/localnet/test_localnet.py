import pytest
from ocp_resources.resource import Resource

from libs.net import netattachdef
from libs.net.nodenetworkconfigurationpolicy import (
    OVN,
    BridgeMappings,
    DesiredState,
    NodeNetworkConfigurationPolicy,
)
from libs.net.vmspec import IP_ADDRESS, lookup_iface_status
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Interface, Multus, Network
from libs.vm.vm import cloudinitdisk_storage
from utilities.constants import TIMEOUT_1MIN, WORKER_NODE_LABEL_KEY
from utilities.infra import create_ns
from utilities.network import cloud_init_network_data

LABEL = {"test": "localnet"}
TOPOLOGY = "localnet"
NETWORK_NAME = "localnet-network"


def localnet_vm(namespace, name, network, cidr):
    spec = base_vmspec()
    spec.template.metadata.labels = LABEL

    vmi_spec = spec.template.spec
    vmi_spec.domain.devices.interfaces = [Interface(name=NETWORK_NAME, bridge={})]
    vmi_spec.networks = [Network(name=NETWORK_NAME, multus=Multus(networkName=network))]

    vmi_spec.affinity = new_pod_anti_affinity(label=next(iter(LABEL.items())))
    vmi_spec.affinity.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution[0].namespaceSelector = {}

    cloud_init_data = cloud_init_network_data(data={"ethernets": {"enp1s0": {"addresses": [cidr]}}})
    cloud_init_data["userData"] = {"users": []}  # Prevents cloud-init from overriding the default OS user credentials
    disk, volume = cloudinitdisk_storage(data=cloud_init_data)
    vmi_spec.domain.devices.disks = vmi_spec.domain.devices.disks or []
    vmi_spec.volumes = vmi_spec.volumes or []
    vmi_spec.domain.devices.disks.append(disk)
    vmi_spec.volumes.append(volume)

    return fedora_vm(namespace=namespace, name=name, spec=spec)


@pytest.fixture(scope="module")
def nncp():
    desired_state = DesiredState(
        ovn=OVN([
            BridgeMappings(
                localnet=NETWORK_NAME,
                bridge="br-ex",
                state="present",
            )
        ])
    )

    with NodeNetworkConfigurationPolicy(
        name="test-localnet-nncp",
        desired_state=desired_state,
        node_selector={WORKER_NODE_LABEL_KEY: ""},
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp


@pytest.fixture(scope="module")
def ns1():
    yield from create_ns(
        name="test-localnet-ns1",
    )


@pytest.fixture(scope="module")
def ns2():
    yield from create_ns(
        name="test-localnet-ns2",
    )


@pytest.fixture(scope="module")
def vlan_id(vlan_index_number):
    return next(vlan_index_number)


@pytest.fixture(scope="module")
def nad1(ns1, vlan_id):
    name = "test-localnet-nad1"
    with netattachdef.NetworkAttachmentDefinition(
        namespace=ns1.name,
        name=name,
        config=netattachdef.NetConfig(
            NETWORK_NAME,
            [
                netattachdef.CNIPluginOvnK8sConfig(
                    topology=TOPOLOGY,
                    netAttachDefName=f"{ns1.name}/{name}",
                    vlanID=vlan_id,
                )
            ],
        ),
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def nad2(ns2, vlan_id):
    name = "test-localnet-nad2"
    with netattachdef.NetworkAttachmentDefinition(
        namespace=ns2.name,
        name=name,
        config=netattachdef.NetConfig(
            NETWORK_NAME,
            [
                netattachdef.CNIPluginOvnK8sConfig(
                    topology=TOPOLOGY,
                    netAttachDefName=f"{ns2.name}/{name}",
                    vlanID=vlan_id,
                )
            ],
        ),
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def vm1(nad1):
    with localnet_vm(namespace=nad1.namespace, name="test-vm1", network=nad1.name, cidr="10.0.0.1/24") as vm:
        vm.start(wait=True)
        vm.vmi.wait_for_condition(
            condition=Resource.Condition.Type.AGENT_CONNECTED, status=Resource.Condition.Status.TRUE
        )
        yield vm


@pytest.fixture(scope="module")
def vm2(nad2):
    with localnet_vm(namespace=nad2.namespace, name="test-vm2", network=nad2.name, cidr="10.0.0.2/24") as vm:
        vm.start(wait=True)
        vm.vmi.wait_for_condition(
            condition=Resource.Condition.Type.AGENT_CONNECTED, status=Resource.Condition.Status.TRUE
        )
        yield vm


@pytest.mark.polarion("CNV-10804")
def test_connectivity_between_localnet_vms(nncp, vm1, vm2):
    target_vm_ip = lookup_iface_status(vm=vm2, iface_name=NETWORK_NAME)[IP_ADDRESS]
    vm1.console(commands=[f"ping -c 3 {target_vm_ip}"], timeout=TIMEOUT_1MIN)
