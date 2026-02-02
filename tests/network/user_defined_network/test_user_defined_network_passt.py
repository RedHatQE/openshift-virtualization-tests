from typing import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from timeout_sampler import TimeoutExpiredError, retry

from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.net.udn import UDN_BINDING_PASST_PLUGIN_NAME
from libs.net.vmspec import lookup_primary_network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.vm_factory import udn_vm
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.virt import LOGGER, migrate_vm_and_verify


@retry(wait_timeout=400, sleep=10, exceptions_dict={})
def wait_for_ready_vm_with_restart(vm: BaseVirtualMachine) -> bool:
    try:
        vm.wait_for_ready_status(status=True, timeout=90)
    except TimeoutExpiredError:
        LOGGER.warning(f"For {vm.name}: Waited for Ready condition but got timeout, restarting vm")
        vm.restart()
        return False
    return True


@pytest.fixture(scope="module")
def passt_enabled_in_hco(
    hyperconverged_resource_scope_module: HyperConverged,
) -> Generator[None, None, None]:
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: {
                "metadata": {"annotations": {"hco.kubevirt.io/deployPasstNetworkBinding": "true"}}
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="module")
def passt_running_vm_pair(
    udn_namespace: Namespace,
    udn_affinity_label: tuple[str, str],
    admin_client: DynamicClient,
    passt_enabled_in_hco,
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
        # passt may not yet be registered. Try to start the VM and if it does not run in time,
        # retry by restarting the VM and waiting again
        wait_for_ready_vm_with_restart(vm=vm_a)
        wait_for_ready_vm_with_restart(vm=vm_b)
        vm_a.wait_for_agent_connected()
        vm_b.wait_for_agent_connected()
        yield vm_a, vm_b


@pytest.mark.ipv4
@pytest.mark.single_nic
@pytest.mark.polarion("CNV-12427")
def test_passt_connectivity_is_preserved_during_client_live_migration(passt_enabled_in_hco, passt_running_vm_pair):
    with client_server_active_connection(
        client_vm=passt_running_vm_pair[0],
        server_vm=passt_running_vm_pair[1],
        spec_logical_network=lookup_primary_network(vm=passt_running_vm_pair[1]).name,
    ) as (client, server):
        migrate_vm_and_verify(vm=client.vm)
        assert is_tcp_connection(server=server, client=client)


@pytest.mark.ipv4
@pytest.mark.single_nic
@pytest.mark.polarion("CNV-12428")
def test_passt_connectivity_is_preserved_during_server_live_migration(passt_enabled_in_hco, passt_running_vm_pair):
    with client_server_active_connection(
        client_vm=passt_running_vm_pair[0],
        server_vm=passt_running_vm_pair[1],
        spec_logical_network=lookup_primary_network(vm=passt_running_vm_pair[1]).name,
    ) as (client, server):
        migrate_vm_and_verify(vm=server.vm)
        assert is_tcp_connection(server=server, client=client)
