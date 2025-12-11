import ipaddress
from typing import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.namespace import Namespace
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork
from ocp_resources.utils.constants import TIMEOUT_1MINUTE

from libs.net.traffic_generator import TcpServer, VMTcpClient, is_tcp_connection
from libs.net.traffic_generator import VMTcpClient as TcpClient
from libs.net.udn import UDN_BINDING_PASST
from libs.net.vmspec import lookup_iface_status, lookup_primary_network
from libs.vm import affinity
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.ip import random_ipv4_address
from tests.network.libs.vm_factory import udn_vm
from tests.utils import register_passt_and_wait_for_sync
from utilities.constants import PUBLIC_DNS_SERVER_IP, TIMEOUT_1MIN
from utilities.infra import create_ns
from utilities.virt import migrate_vm_and_verify

IP_ADDRESS = "ipAddress"
SERVER_PORT = 5201


@pytest.fixture(scope="module")
def udn_namespace(admin_client):
    yield from create_ns(
        admin_client=admin_client,
        name="test-user-defined-network-ns",
        labels={"k8s.ovn.org/primary-user-defined-network": ""},
    )


@pytest.fixture(scope="module")
def namespaced_layer2_user_defined_network(admin_client, udn_namespace):
    with Layer2UserDefinedNetwork(
        name="layer2-udn",
        namespace=udn_namespace.name,
        role="Primary",
        subnets=[f"{random_ipv4_address(net_seed=0, host_address=0)}/24"],
        ipam={"lifecycle": "Persistent"},
        client=admin_client,
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
def vma_udn(udn_namespace, namespaced_layer2_user_defined_network, udn_affinity_label, admin_client):
    with udn_vm(
        namespace_name=udn_namespace.name,
        name="vma-udn",
        client=admin_client,
        template_labels=dict((udn_affinity_label,)),
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def vmb_udn(udn_namespace, namespaced_layer2_user_defined_network, udn_affinity_label, admin_client):
    with udn_vm(
        namespace_name=udn_namespace.name,
        name="vmb-udn",
        client=admin_client,
        template_labels=dict((udn_affinity_label,)),
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def server(vmb_udn):
    with TcpServer(vm=vmb_udn, port=SERVER_PORT) as server:
        assert server.is_running()
        yield server


@pytest.fixture(scope="class")
def client(vma_udn, vmb_udn):
    with TcpClient(
        vm=vma_udn,
        server_ip=lookup_iface_status(vm=vmb_udn, iface_name=lookup_primary_network(vm=vmb_udn).name)[IP_ADDRESS],
        server_port=SERVER_PORT,
    ) as client:
        assert client.is_running()
        yield client


@pytest.fixture(scope="class")
def passt_enabled_in_hco(
    admin_client: DynamicClient,
    hco_namespace: Namespace,
    hyperconverged_resource_scope_class: HyperConverged,
) -> Generator[None, None, None]:
    with register_passt_and_wait_for_sync(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hco_resource=hyperconverged_resource_scope_class,
    ):
        yield


@pytest.fixture(scope="class")
def passt_vm_a(
    udn_namespace: Namespace,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
    udn_affinity_label: tuple[str, str],
    admin_client: DynamicClient,
) -> Generator[BaseVirtualMachine, None, None]:
    with udn_vm(
        namespace_name=udn_namespace.name,
        name="vma-passt",
        client=admin_client,
        template_labels=dict((udn_affinity_label,)),
        binding=UDN_BINDING_PASST,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def passt_vm_b(
    udn_namespace: Namespace,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
    udn_affinity_label: tuple[str, str],
    admin_client: DynamicClient,
) -> Generator[BaseVirtualMachine, None, None]:
    with udn_vm(
        namespace_name=udn_namespace.name,
        name="vmb-passt",
        client=admin_client,
        template_labels=dict((udn_affinity_label,)),
        binding=UDN_BINDING_PASST,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def server_passt(passt_vm_b: BaseVirtualMachine) -> Generator[TcpServer, None, None]:
    with TcpServer(vm=passt_vm_b, port=SERVER_PORT) as server:
        yield server


@pytest.fixture(scope="class")
def client_passt(
    passt_vm_a: BaseVirtualMachine,
    passt_vm_b: BaseVirtualMachine,
) -> Generator[VMTcpClient, None, None]:
    with TcpClient(
        vm=passt_vm_a,
        server_ip=lookup_iface_status(vm=passt_vm_b, iface_name=lookup_primary_network(vm=passt_vm_b).name)[IP_ADDRESS],
        server_port=SERVER_PORT,
    ) as client:
        yield client


@pytest.mark.ipv4
@pytest.mark.s390x
class TestPrimaryUdn:
    @pytest.mark.polarion("CNV-11624")
    @pytest.mark.single_nic
    def test_ip_address_in_running_vm_matches_udn_subnet(self, namespaced_layer2_user_defined_network, vma_udn):
        ip = lookup_iface_status(vm=vma_udn, iface_name=lookup_primary_network(vm=vma_udn).name)[IP_ADDRESS]
        (subnet,) = namespaced_layer2_user_defined_network.subnets
        assert ipaddress.ip_address(ip) in ipaddress.ip_network(subnet), (
            f"The VM's primary network IP address ({ip}) is not in the UDN defined subnet ({subnet})"
        )

    @pytest.mark.polarion("CNV-11674")
    @pytest.mark.single_nic
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
    @pytest.mark.single_nic
    def test_vm_egress_connectivity(self, vmb_udn):
        assert lookup_iface_status(vm=vmb_udn, iface_name=lookup_primary_network(vm=vmb_udn).name)[IP_ADDRESS]
        vmb_udn.console(commands=[f"ping -c 3 {PUBLIC_DNS_SERVER_IP}"], timeout=TIMEOUT_1MINUTE)

    @pytest.mark.polarion("CNV-11418")
    @pytest.mark.single_nic
    def test_basic_connectivity_between_udn_vms(self, vma_udn, vmb_udn):
        target_vm_ip = lookup_iface_status(vm=vmb_udn, iface_name=lookup_primary_network(vm=vmb_udn).name)[IP_ADDRESS]
        vma_udn.console(commands=[f"ping -c 3 {target_vm_ip}"], timeout=TIMEOUT_1MIN)

    @pytest.mark.polarion("CNV-11427")
    @pytest.mark.single_nic
    @pytest.mark.gating
    def test_connectivity_is_preserved_during_client_live_migration(self, server, client):
        migrate_vm_and_verify(vm=client.vm)
        assert is_tcp_connection(server=server, client=client)

    @pytest.mark.polarion("CNV-12177")
    @pytest.mark.single_nic
    def test_connectivity_is_preserved_during_server_live_migration(self, server, client):
        migrate_vm_and_verify(vm=server.vm)
        assert is_tcp_connection(server=server, client=client)


@pytest.mark.ipv4
@pytest.mark.usefixtures("passt_enabled_in_hco")
class TestPrimaryUdnPasst:
    @pytest.mark.polarion("CNV-12427")
    @pytest.mark.single_nic
    def test_passt_connectivity_is_preserved_during_client_live_migration(self, server_passt, client_passt):
        migrate_vm_and_verify(vm=client_passt.vm)
        assert is_tcp_connection(server=server_passt, client=client_passt)

    @pytest.mark.polarion("CNV-12428")
    @pytest.mark.single_nic
    def test_passt_connectivity_is_preserved_during_server_live_migration(self, server_passt, client_passt):
        migrate_vm_and_verify(vm=server_passt.vm)
        assert is_tcp_connection(server=server_passt, client=client_passt)
