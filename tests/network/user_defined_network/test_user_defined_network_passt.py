from typing import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.namespace import Namespace
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork

from libs.net.traffic_generator import is_tcp_connection
from libs.net.udn import UDN_BINDING_PASST_PLUGIN_NAME
from libs.net.vmspec import lookup_primary_network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.vm_factory import udn_vm
from tests.network.localnet.liblocalnet import client_server_active_connection
from tests.utils import register_passt_and_wait_for_sync
from utilities.virt import migrate_vm_and_verify


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
def passt_running_vm_pair(
    udn_namespace: Namespace,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
    udn_affinity_label: tuple[str, str],
    admin_client: DynamicClient,
) -> Generator[tuple[BaseVirtualMachine, BaseVirtualMachine], None, None]:
    with (
        udn_vm(
            namespace_name=udn_namespace.name,
            name="vma-passt",
            client=admin_client,
            template_labels=dict((udn_affinity_label,)),
            binding=UDN_BINDING_PASST_PLUGIN_NAME,
        ) as vm_a,
        udn_vm(
            namespace_name=udn_namespace.name,
            name="vmb-passt",
            client=admin_client,
            template_labels=dict((udn_affinity_label,)),
            binding=UDN_BINDING_PASST_PLUGIN_NAME,
        ) as vm_b,
    ):
        vm_a.start(wait=False)
        vm_b.start(wait=False)
        vm_a.wait_for_agent_connected()
        vm_b.wait_for_agent_connected()
        yield vm_a, vm_b


@pytest.mark.ipv4
@pytest.mark.usefixtures("passt_enabled_in_hco")
class TestPrimaryUdnPasst:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-12427")
    @pytest.mark.single_nic
    def test_passt_connectivity_is_preserved_during_client_live_migration(self, passt_running_vm_pair):
        with client_server_active_connection(
            client_vm=passt_running_vm_pair[0],
            server_vm=passt_running_vm_pair[1],
            spec_logical_network=lookup_primary_network(vm=passt_running_vm_pair[1]).name,
        ) as client_server_vms:
            client_vm, server_vm = client_server_vms
            migrate_vm_and_verify(vm=client_vm.vm)
            assert is_tcp_connection(server=server_vm, client=client_vm)

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-12428")
    @pytest.mark.single_nic
    def test_passt_connectivity_is_preserved_during_server_live_migration(self, passt_running_vm_pair):
        with client_server_active_connection(
            client_vm=passt_running_vm_pair[0],
            server_vm=passt_running_vm_pair[1],
            spec_logical_network=lookup_primary_network(vm=passt_running_vm_pair[1]).name,
        ) as client_server_vms:
            client_vm, server_vm = client_server_vms
            migrate_vm_and_verify(vm=server_vm.vm)
            assert is_tcp_connection(server=server_vm, client=client_vm)
