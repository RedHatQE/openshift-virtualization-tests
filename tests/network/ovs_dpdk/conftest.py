import ipaddress
from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from ocp_resources.resource_claim_template import ResourceClaimTemplate

from libs.net.traffic_generator import TcpServer, VMTcpClient, active_tcp_connections
from libs.net.vmspec import wait_for_ifaces_status
from libs.vm.oper import run_vms
from libs.vm.vm import BaseVirtualMachine
from tests.network.ovs_dpdk.lib_helpers import (
    GUEST_OVS_DPDK_IFACE_NAME,
    REF_VM_HOST_ADDRESS,
    REF_VM_RESOURCE_CLAIM_NAME,
    UNDER_TEST_VM_HOST_ADDRESS,
    UNDER_TEST_VM_RESOURCE_CLAIM_NAME,
    ovs_dpdk_hco_cnv_integration_patch,
    ovs_dpdk_rct_vm,
    ovs_dpdk_resource_claim_template_spec,
    verify_baseline_connectivity,
)
from utilities.constants.networking import (
    OVS_DPDK_INTERFACE_NAME,
    OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_NAME,
    OVS_DPDK_TESTS_RELATIVE_PATH,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import create_ns, generate_namespace_name
from utilities.virt import migrate_vm_and_verify


@pytest.fixture(scope="package")
def ovs_dpdk_enabled_in_hco(
    admin_client: DynamicClient,
    hyperconverged_resource_scope_package: HyperConverged,
) -> Generator[None]:
    with ResourceEditorValidateHCOReconcile(
        admin_client=admin_client,
        patches={
            hyperconverged_resource_scope_package: ovs_dpdk_hco_cnv_integration_patch(),
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
        name=generate_namespace_name(file_path=OVS_DPDK_TESTS_RELATIVE_PATH),
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
    with ovs_dpdk_rct_vm(
        namespace=ovs_dpdk_namespace.name,
        name="ref-vm",
        client=unprivileged_client,
        resource_claim_name=REF_VM_RESOURCE_CLAIM_NAME,
        host_address=REF_VM_HOST_ADDRESS,
    ) as vm:
        yield vm


@pytest.fixture(scope="package")
def ovs_dpdk_under_test_vm(
    unprivileged_client: DynamicClient,
    ovs_dpdk_namespace: Namespace,
    ovs_dpdk_resource_claim_template: ResourceClaimTemplate,
) -> Generator[BaseVirtualMachine]:
    with ovs_dpdk_rct_vm(
        namespace=ovs_dpdk_namespace.name,
        name="under-test-vm",
        client=unprivileged_client,
        resource_claim_name=UNDER_TEST_VM_RESOURCE_CLAIM_NAME,
        host_address=UNDER_TEST_VM_HOST_ADDRESS,
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


@pytest.fixture(scope="package")
def ovs_dpdk_baseline_connectivity(
    under_test_ref_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> None:
    under_test_vm, ref_vm = under_test_ref_running_vms
    verify_baseline_connectivity(client_vm=under_test_vm, ref_vm=ref_vm)


@pytest.fixture(scope="module")
def ovs_dpdk_live_migration_active_tcp_by_family(
    admin_client: DynamicClient,
    ovs_dpdk_baseline_connectivity: None,
    under_test_ref_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> Generator[dict[int, tuple[VMTcpClient, TcpServer]]]:
    under_test_vm, ref_vm = under_test_ref_running_vms
    with active_tcp_connections(
        client_vm=under_test_vm,
        server_vm=ref_vm,
        iface_name=OVS_DPDK_INTERFACE_NAME,
    ) as connections:
        active_tcp_by_family = {
            ipaddress.ip_address(address=client.server_ip).version: (client, server) for client, server in connections
        }
        migrate_vm_and_verify(vm=under_test_vm, client=admin_client)
        yield active_tcp_by_family


@pytest.fixture
def ip_family(request: pytest.FixtureRequest) -> int:
    return request.param
