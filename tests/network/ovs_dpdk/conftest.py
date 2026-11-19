from __future__ import annotations

import ipaddress
from collections.abc import Generator
from typing import TYPE_CHECKING, Final

import pytest
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from ocp_resources.resource_claim_template import ResourceClaimTemplate

from libs.net.traffic_generator import active_tcp_connections
from libs.net.vmspec import wait_for_ifaces_status
from libs.vm.oper import run_vms
from tests.network.libs.connectivity import ARP_ISOLATION_SYSCTL_CMD
from tests.network.ovs_dpdk.libovsdpdk import (
    GUEST_OVS_DPDK_IFACE_NAME,
    GUEST_OVS_DPDK_SECOND_IFACE_NAME,
    OVS_DPDK_INTERFACE_NAME,
    OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_NAME,
    OVS_DPDK_SECOND_INTERFACE_NAME,
    OvsDpdkIface,
    ovs_dpdk_hco_cnv_integration_patch,
    ovs_dpdk_resource_claim_template_spec,
    ovs_dpdk_vlan_resource_claim_template_spec,
    ovs_dpdk_vm,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import create_ns, generate_namespace_name
from utilities.virt import migrate_vm_and_verify

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from libs.net.traffic_generator import TcpServer, VMTcpClient
    from libs.vm.vm import BaseVirtualMachine

OVS_DPDK_NET_SEED: Final[int] = 10
REF_VM_RESOURCE_CLAIM_NAME: Final[str] = "ovs-dpdk-reference-claim"
UNDER_TEST_VM_RESOURCE_CLAIM_NAME: Final[str] = "ovs-dpdk-under-test-claim"
REF_VM_RESOURCE_CLAIM_NAME_0: Final[str] = "ovs-dpdk-reference-claim-0"
REF_VM_RESOURCE_CLAIM_NAME_1: Final[str] = "ovs-dpdk-reference-claim-1"
UNDER_TEST_VM_RESOURCE_CLAIM_NAME_0: Final[str] = "ovs-dpdk-under-test-claim-0"
UNDER_TEST_VM_RESOURCE_CLAIM_NAME_1: Final[str] = "ovs-dpdk-under-test-claim-1"
REF_VM_HOST_ADDRESS: Final[int] = 1
UNDER_TEST_VM_HOST_ADDRESS: Final[int] = 2
REF_DUAL_CLAIM_VLAN_A_HOST_ADDRESS: Final[int] = 3
REF_DUAL_CLAIM_VLAN_B_HOST_ADDRESS: Final[int] = 5
UNDER_TEST_DUAL_CLAIM_VLAN_A_HOST_ADDRESS: Final[int] = 4
UNDER_TEST_DUAL_CLAIM_VLAN_B_HOST_ADDRESS: Final[int] = 6
OVS_DPDK_VLAN_A: Final[int] = 100
OVS_DPDK_VLAN_B: Final[int] = 200
OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_A_NAME: Final[str] = f"my-claim-template-vlan-{OVS_DPDK_VLAN_A}"
OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_B_NAME: Final[str] = f"my-claim-template-vlan-{OVS_DPDK_VLAN_B}"


@pytest.fixture(scope="package")
def ovs_dpdk_enabled_in_hco(
    admin_client: DynamicClient,
    hyperconverged_resource_scope_package: HyperConverged,
) -> Generator[None]:
    with ResourceEditorValidateHCOReconcile(
        admin_client=admin_client,
        patches={
            hyperconverged_resource_scope_package: ovs_dpdk_hco_cnv_integration_patch(
                hco_resource=hyperconverged_resource_scope_package,
            ),
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="package")
def ovs_dpdk_namespace(
    admin_client: DynamicClient,
    unprivileged_client: DynamicClient,
) -> Generator[Namespace]:
    yield from create_ns(
        unprivileged_client=unprivileged_client,
        admin_client=admin_client,
        name=generate_namespace_name(file_path="network/ovs_dpdk"),
    )


@pytest.fixture(scope="package")
def ovs_dpdk_resource_claim_template(
    admin_client: DynamicClient,
    ovs_dpdk_namespace: Namespace,
    ovs_dpdk_enabled_in_hco: None,
) -> Generator[ResourceClaimTemplate]:
    with ResourceClaimTemplate(
        name=OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_NAME,
        namespace=ovs_dpdk_namespace.name,
        client=admin_client,
        spec_spec=ovs_dpdk_resource_claim_template_spec(),
    ) as template:
        yield template


@pytest.fixture(scope="package")
def ovs_dpdk_ref_vm(
    unprivileged_client: DynamicClient,
    ovs_dpdk_resource_claim_template: ResourceClaimTemplate,
    ovs_dpdk_namespace: Namespace,
) -> Generator[BaseVirtualMachine]:
    with ovs_dpdk_vm(
        namespace=ovs_dpdk_namespace.name,
        name="ref-vm-ovs-dpdk",
        client=unprivileged_client,
        net_seed=OVS_DPDK_NET_SEED,
        ifaces=[
            OvsDpdkIface(
                spec_name=OVS_DPDK_INTERFACE_NAME,
                guest_name=GUEST_OVS_DPDK_IFACE_NAME,
                claim_name=REF_VM_RESOURCE_CLAIM_NAME,
                claim_template_name=ovs_dpdk_resource_claim_template.name,
                host_address=REF_VM_HOST_ADDRESS,
            ),
        ],
    ) as vm:
        yield vm


@pytest.fixture(scope="package")
def ovs_dpdk_under_test_vm(
    unprivileged_client: DynamicClient,
    ovs_dpdk_namespace: Namespace,
    ovs_dpdk_resource_claim_template: ResourceClaimTemplate,
) -> Generator[BaseVirtualMachine]:
    with ovs_dpdk_vm(
        namespace=ovs_dpdk_namespace.name,
        name="under-test-vm-ovs-dpdk",
        client=unprivileged_client,
        net_seed=OVS_DPDK_NET_SEED,
        ifaces=[
            OvsDpdkIface(
                spec_name=OVS_DPDK_INTERFACE_NAME,
                guest_name=GUEST_OVS_DPDK_IFACE_NAME,
                claim_name=UNDER_TEST_VM_RESOURCE_CLAIM_NAME,
                claim_template_name=ovs_dpdk_resource_claim_template.name,
                host_address=UNDER_TEST_VM_HOST_ADDRESS,
            ),
        ],
    ) as vm:
        yield vm


@pytest.fixture(scope="package")
def under_test_ref_running_vms(
    ovs_dpdk_ref_vm: BaseVirtualMachine,
    ovs_dpdk_under_test_vm: BaseVirtualMachine,
) -> tuple[BaseVirtualMachine, BaseVirtualMachine]:
    run_vms(vms=(ovs_dpdk_under_test_vm, ovs_dpdk_ref_vm))
    for vm in (ovs_dpdk_under_test_vm, ovs_dpdk_ref_vm):
        cloud_init_addresses = vm.cloud_init_network_data.ethernets[GUEST_OVS_DPDK_IFACE_NAME].addresses or []
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                OVS_DPDK_INTERFACE_NAME: [
                    str(ipaddress.ip_interface(address=address).ip) for address in cloud_init_addresses
                ],
            },
        )
    return ovs_dpdk_under_test_vm, ovs_dpdk_ref_vm


@pytest.fixture(scope="module")
def ovs_dpdk_active_tcp_by_family(
    under_test_ref_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> Generator[dict[int, tuple[VMTcpClient, TcpServer]]]:
    """
    Start continuous TCP connections from the under-test VM to the reference VM, one per
    IP family enabled on the OVS-DPDK interface.

    The fixture owns the connections: traffic keeps flowing until the requesting test
    module is torn down. Each connection is verified running before the fixture yields
    (the iperf3 client and server retry their startup), so dependents can assume the
    connections are live.

    Yields:
        dict[int, tuple[VMTcpClient, TcpServer]]: Active connections keyed by IP version (4 or 6).
    """
    under_test_vm, ref_vm = under_test_ref_running_vms
    with active_tcp_connections(
        client_vm=under_test_vm,
        server_vm=ref_vm,
        iface_name=OVS_DPDK_INTERFACE_NAME,
    ) as connections:
        connections_by_family = {
            ipaddress.ip_address(address=client.server_ip).version: (client, server) for client, server in connections
        }
        yield connections_by_family


@pytest.fixture(scope="module")
def ovs_dpdk_under_test_migrated_vm(
    admin_client: DynamicClient,
    under_test_ref_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
    ovs_dpdk_active_tcp_by_family: dict[int, tuple[VMTcpClient, TcpServer]],
) -> BaseVirtualMachine:
    """
    Live-migrate the shared under-test VM while its TCP connections to the reference VM
    are active, and wait for the migration to complete.

    Depends on the active connections to guarantee they were established before the
    migration starts, so their post-migration liveness proves preservation. Module scope
    ensures the migration runs only once even if there is more than one connection (one
    per configured IP-family).

    Returns:
        BaseVirtualMachine: The migrated under-test VM.
    """
    under_test_vm = under_test_ref_running_vms[0]
    migrate_vm_and_verify(vm=under_test_vm, client=admin_client)
    return under_test_vm


@pytest.fixture(scope="package")
def ovs_dpdk_vlan_a_resource_claim_template(
    admin_client: DynamicClient,
    ovs_dpdk_namespace: Namespace,
    ovs_dpdk_enabled_in_hco: None,
) -> Generator[ResourceClaimTemplate]:
    with ResourceClaimTemplate(
        name=OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_A_NAME,
        namespace=ovs_dpdk_namespace.name,
        client=admin_client,
        spec_spec=ovs_dpdk_vlan_resource_claim_template_spec(vlan=OVS_DPDK_VLAN_A),
    ) as template:
        yield template


@pytest.fixture(scope="package")
def ovs_dpdk_vlan_b_resource_claim_template(
    admin_client: DynamicClient,
    ovs_dpdk_namespace: Namespace,
    ovs_dpdk_enabled_in_hco: None,
) -> Generator[ResourceClaimTemplate]:
    with ResourceClaimTemplate(
        name=OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_B_NAME,
        namespace=ovs_dpdk_namespace.name,
        client=admin_client,
        spec_spec=ovs_dpdk_vlan_resource_claim_template_spec(vlan=OVS_DPDK_VLAN_B),
    ) as template:
        yield template


@pytest.fixture(scope="package")
def ovs_dpdk_dual_claim_ref_vm(
    unprivileged_client: DynamicClient,
    ovs_dpdk_vlan_a_resource_claim_template: ResourceClaimTemplate,
    ovs_dpdk_vlan_b_resource_claim_template: ResourceClaimTemplate,
    ovs_dpdk_namespace: Namespace,
) -> Generator[BaseVirtualMachine]:
    with ovs_dpdk_vm(
        namespace=ovs_dpdk_namespace.name,
        name="ref-vm-ovs-dpdk-dual",
        client=unprivileged_client,
        net_seed=OVS_DPDK_NET_SEED,
        ifaces=[
            OvsDpdkIface(
                spec_name=OVS_DPDK_INTERFACE_NAME,
                guest_name=GUEST_OVS_DPDK_IFACE_NAME,
                claim_name=REF_VM_RESOURCE_CLAIM_NAME_0,
                claim_template_name=ovs_dpdk_vlan_a_resource_claim_template.name,
                host_address=REF_DUAL_CLAIM_VLAN_A_HOST_ADDRESS,
            ),
            OvsDpdkIface(
                spec_name=OVS_DPDK_SECOND_INTERFACE_NAME,
                guest_name=GUEST_OVS_DPDK_SECOND_IFACE_NAME,
                claim_name=REF_VM_RESOURCE_CLAIM_NAME_1,
                claim_template_name=ovs_dpdk_vlan_b_resource_claim_template.name,
                host_address=REF_DUAL_CLAIM_VLAN_B_HOST_ADDRESS,
            ),
        ],
        runcmd=ARP_ISOLATION_SYSCTL_CMD,
    ) as vm:
        yield vm


@pytest.fixture(scope="package")
def ovs_dpdk_dual_claim_under_test_vm(
    unprivileged_client: DynamicClient,
    ovs_dpdk_namespace: Namespace,
    ovs_dpdk_vlan_a_resource_claim_template: ResourceClaimTemplate,
    ovs_dpdk_vlan_b_resource_claim_template: ResourceClaimTemplate,
) -> Generator[BaseVirtualMachine]:
    with ovs_dpdk_vm(
        namespace=ovs_dpdk_namespace.name,
        name="under-test-vm-ovs-dpdk-dual",
        client=unprivileged_client,
        net_seed=OVS_DPDK_NET_SEED,
        ifaces=[
            OvsDpdkIface(
                spec_name=OVS_DPDK_INTERFACE_NAME,
                guest_name=GUEST_OVS_DPDK_IFACE_NAME,
                claim_name=UNDER_TEST_VM_RESOURCE_CLAIM_NAME_0,
                claim_template_name=ovs_dpdk_vlan_a_resource_claim_template.name,
                host_address=UNDER_TEST_DUAL_CLAIM_VLAN_A_HOST_ADDRESS,
            ),
            OvsDpdkIface(
                spec_name=OVS_DPDK_SECOND_INTERFACE_NAME,
                guest_name=GUEST_OVS_DPDK_SECOND_IFACE_NAME,
                claim_name=UNDER_TEST_VM_RESOURCE_CLAIM_NAME_1,
                claim_template_name=ovs_dpdk_vlan_b_resource_claim_template.name,
                host_address=UNDER_TEST_DUAL_CLAIM_VLAN_B_HOST_ADDRESS,
            ),
        ],
        runcmd=ARP_ISOLATION_SYSCTL_CMD,
    ) as vm:
        yield vm


@pytest.fixture(scope="package")
def under_test_ref_dual_claim_running_vms(
    ovs_dpdk_dual_claim_ref_vm: BaseVirtualMachine,
    ovs_dpdk_dual_claim_under_test_vm: BaseVirtualMachine,
) -> tuple[BaseVirtualMachine, BaseVirtualMachine]:
    run_vms(vms=(ovs_dpdk_dual_claim_under_test_vm, ovs_dpdk_dual_claim_ref_vm))
    for vm in (ovs_dpdk_dual_claim_under_test_vm, ovs_dpdk_dual_claim_ref_vm):
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                OVS_DPDK_INTERFACE_NAME: [
                    str(ipaddress.ip_interface(address=address).ip)
                    for address in (vm.cloud_init_network_data.ethernets[GUEST_OVS_DPDK_IFACE_NAME].addresses or [])
                ],
                OVS_DPDK_SECOND_INTERFACE_NAME: [
                    str(ipaddress.ip_interface(address=address).ip)
                    for address in (
                        vm.cloud_init_network_data.ethernets[GUEST_OVS_DPDK_SECOND_IFACE_NAME].addresses or []
                    )
                ],
            },
        )
    return ovs_dpdk_dual_claim_under_test_vm, ovs_dpdk_dual_claim_ref_vm
