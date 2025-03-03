import ipaddress

import pytest
from ocp_resources.resource import Resource
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork
from ocp_resources.utils.constants import TIMEOUT_1MINUTE

from libs.net.traffic_generator import Client, Server, is_tcp_connection
from libs.net.udn import udn_primary_network
from libs.net.vmspec import lookup_iface_status, lookup_primary_network
from libs.vm import affinity
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from utilities.constants import PUBLIC_DNS_SERVER_IP, TIMEOUT_1MIN
from utilities.infra import create_ns
from utilities.virt import migrate_vm_and_verify

IP_ADDRESS = "ipAddress"
SERVER_PORT = 5201


def udn_vm(namespace_name, name, template_labels=None):
    spec = base_vmspec()
    iface, network = udn_primary_network(name="udn-primary")
    spec.template.spec.domain.devices.interfaces = [iface]
    spec.template.spec.networks = [network]
    if template_labels:
        spec.template.metadata.labels = spec.template.metadata.labels or {}
        spec.template.metadata.labels.update(template_labels)
        # Use the first label key and first value as the anti-affinity label to use:
        label, *_ = template_labels.items()
        spec.template.spec.affinity = new_pod_anti_affinity(label=label)

    return fedora_vm(namespace=namespace_name, name=name, spec=spec)


@pytest.fixture(scope="module")
def udn_namespace():
    yield from create_ns(
        name="test-user-defined-network-ns",
        labels={"k8s.ovn.org/primary-user-defined-network": ""},
    )


@pytest.fixture(scope="module")
def namespaced_layer2_user_defined_network(udn_namespace):
    with Layer2UserDefinedNetwork(
        name="layer2-udn",
        namespace=udn_namespace.name,
        role="Primary",
        subnets=["10.10.0.0/24"],
        ipam_lifecycle="Persistent",
    ) as udn:
        udn.wait_for_condition(
            condition="NetworkAllocationSucceeded",
            status=udn.Condition.Status.TRUE,
        )
        yield udn


@pytest.fixture(scope="class")
def udn_affinity_label():
    return affinity.new_label(key_prefix="udn")


@pytest.fixture(scope="class")
def vma_udn(udn_namespace, namespaced_layer2_user_defined_network, udn_affinity_label):
    with udn_vm(namespace_name=udn_namespace.name, name="vma-udn", template_labels=dict((udn_affinity_label,))) as vm:
        vm.start(wait=True)
        vm.vmi.wait_for_condition(condition="AgentConnected", status=Resource.Condition.Status.TRUE)
        yield vm


@pytest.fixture(scope="class")
def vmb_udn_non_migratable(udn_namespace, namespaced_layer2_user_defined_network, udn_affinity_label):
    with udn_vm(namespace_name=udn_namespace.name, name="vmb-udn", template_labels=dict((udn_affinity_label,))) as vm:
        vm.start(wait=True)
        vm.vmi.wait_for_condition(condition="AgentConnected", status=Resource.Condition.Status.TRUE)
        yield vm


@pytest.fixture()
def server(vmb_udn_non_migratable):
    with Server(vm=vmb_udn_non_migratable, port=SERVER_PORT) as server:
        assert server.is_running()
        yield server


@pytest.fixture()
def client(vma_udn, vmb_udn_non_migratable):
    with Client(
        vm=vma_udn,
        server_ip=lookup_iface_status(
            vm=vmb_udn_non_migratable, iface_name=lookup_primary_network(vm=vmb_udn_non_migratable).name
        )[IP_ADDRESS],
        server_port=SERVER_PORT,
    ) as client:
        assert client.is_running()
        yield client


@pytest.mark.ipv4
class TestPrimaryUdn:
    @pytest.mark.polarion("CNV-11624")
    def test_ip_address_in_running_vm_matches_udn_subnet(self, namespaced_layer2_user_defined_network, vma_udn):
        ip = lookup_iface_status(vm=vma_udn, iface_name=lookup_primary_network(vm=vma_udn).name)[IP_ADDRESS]
        (subnet,) = namespaced_layer2_user_defined_network.subnets
        assert ipaddress.ip_address(ip) in ipaddress.ip_network(subnet), (
            f"The VM's primary network IP address ({ip}) is not in the UDN defined subnet ({subnet})"
        )

    @pytest.mark.polarion("CNV-11674")
    def test_ip_address_is_preserved_after_live_migration(self, vma_udn):
        ip_before_migration = lookup_iface_status(vm=vma_udn, iface_name=lookup_primary_network(vm=vma_udn).name)[
            IP_ADDRESS
        ]
        assert ip_before_migration
        migrate_vm_and_verify(vm=vma_udn)
        ip_after_migration = lookup_iface_status(vm=vma_udn, iface_name=lookup_primary_network(vm=vma_udn).name)[
            IP_ADDRESS
        ]
        assert ip_before_migration == ip_after_migration, (
            f"The IP address {ip_before_migration} was not preserved during live migration. "
            f"IP after migration: {ip_after_migration}."
        )

    @pytest.mark.polarion("CNV-11434")
    def test_vm_egress_connectivity(self, vmb_udn_non_migratable):
        assert lookup_iface_status(
            vm=vmb_udn_non_migratable, iface_name=lookup_primary_network(vm=vmb_udn_non_migratable).name
        )[IP_ADDRESS]
        vmb_udn_non_migratable.console(commands=[f"ping -c 3 {PUBLIC_DNS_SERVER_IP}"], timeout=TIMEOUT_1MINUTE)

    @pytest.mark.polarion("CNV-11418")
    def test_basic_connectivity_between_udn_vms(self, vma_udn, vmb_udn_non_migratable):
        target_vm_ip = lookup_iface_status(
            vm=vmb_udn_non_migratable, iface_name=lookup_primary_network(vm=vmb_udn_non_migratable).name
        )[IP_ADDRESS]
        vma_udn.console(commands=[f"ping -c 3 {target_vm_ip}"], timeout=TIMEOUT_1MIN)

    @pytest.mark.polarion("CNV-11427")
    def test_connectivity_is_preserved_after_live_migration(self, vma_udn, server, client):
        migrate_vm_and_verify(vm=vma_udn)
        assert is_tcp_connection(server=server, client=client)
