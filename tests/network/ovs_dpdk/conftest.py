from __future__ import annotations

import ipaddress
from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from ocp_resources.resource_claim_template import ResourceClaimTemplate

from libs.net.vmspec import wait_for_ifaces_status
from libs.vm.oper import run_vms
from tests.network.ovs_dpdk.libovsdpdk import (
    GUEST_OVS_DPDK_IFACE_NAME,
    GUEST_OVS_DPDK_SECOND_IFACE_NAME,
    OVS_DPDK_INTERFACE_NAME,
    OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_NAME,
    OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_A_NAME,
    OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_B_NAME,
    OVS_DPDK_SECOND_INTERFACE_NAME,
    OVS_DPDK_VLAN_A,
    OVS_DPDK_VLAN_B,
    REF_VM_HOST_ADDRESS,
    REF_VM_RESOURCE_CLAIM_NAME,
    REF_VM_RESOURCE_CLAIM_NAME_0,
    REF_VM_RESOURCE_CLAIM_NAME_1,
    REF_VM_SECOND_HOST_ADDRESS,
    UNDER_TEST_VM_HOST_ADDRESS,
    UNDER_TEST_VM_RESOURCE_CLAIM_NAME,
    UNDER_TEST_VM_RESOURCE_CLAIM_NAME_0,
    UNDER_TEST_VM_RESOURCE_CLAIM_NAME_1,
    UNDER_TEST_VM_SECOND_HOST_ADDRESS,
    ovs_dpdk_dual_claim_vm,
    ovs_dpdk_hco_cnv_integration_patch,
    ovs_dpdk_resource_claim_template_spec,
    ovs_dpdk_vm,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import create_ns, generate_namespace_name

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from libs.vm.vm import BaseVirtualMachine


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
    with ovs_dpdk_vm(
        namespace=ovs_dpdk_namespace.name,
        name="under-test-vm-ovs-dpdk",
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
def ovs_dpdk_vlan_primary_resource_claim_template(
    admin_client: DynamicClient,
    ovs_dpdk_namespace: Namespace,
    ovs_dpdk_enabled_in_hco: None,
) -> Generator[ResourceClaimTemplate]:
    with ResourceClaimTemplate(
        name=OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_A_NAME,
        namespace=ovs_dpdk_namespace.name,
        client=admin_client,
        spec_spec=ovs_dpdk_resource_claim_template_spec(vlan=OVS_DPDK_VLAN_A),
    ) as template:
        yield template


@pytest.fixture(scope="package")
def ovs_dpdk_vlan_secondary_resource_claim_template(
    admin_client: DynamicClient,
    ovs_dpdk_namespace: Namespace,
    ovs_dpdk_enabled_in_hco: None,
) -> Generator[ResourceClaimTemplate]:
    with ResourceClaimTemplate(
        name=OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_B_NAME,
        namespace=ovs_dpdk_namespace.name,
        client=admin_client,
        spec_spec=ovs_dpdk_resource_claim_template_spec(vlan=OVS_DPDK_VLAN_B),
    ) as template:
        yield template


@pytest.fixture(scope="package")
def ovs_dpdk_dual_claim_ref_vm(
    unprivileged_client: DynamicClient,
    ovs_dpdk_vlan_primary_resource_claim_template: ResourceClaimTemplate,
    ovs_dpdk_vlan_secondary_resource_claim_template: ResourceClaimTemplate,
    ovs_dpdk_namespace: Namespace,
) -> Generator[BaseVirtualMachine]:
    with ovs_dpdk_dual_claim_vm(
        namespace=ovs_dpdk_namespace.name,
        name="ref-vm-ovs-dpdk-dual",
        client=unprivileged_client,
        primary_resource_claim_name=REF_VM_RESOURCE_CLAIM_NAME_0,
        secondary_resource_claim_name=REF_VM_RESOURCE_CLAIM_NAME_1,
        primary_host_address=REF_VM_HOST_ADDRESS,
        secondary_host_address=REF_VM_SECOND_HOST_ADDRESS,
    ) as vm:
        yield vm


@pytest.fixture(scope="package")
def ovs_dpdk_dual_claim_under_test_vm(
    unprivileged_client: DynamicClient,
    ovs_dpdk_namespace: Namespace,
    ovs_dpdk_vlan_primary_resource_claim_template: ResourceClaimTemplate,
    ovs_dpdk_vlan_secondary_resource_claim_template: ResourceClaimTemplate,
) -> Generator[BaseVirtualMachine]:
    with ovs_dpdk_dual_claim_vm(
        namespace=ovs_dpdk_namespace.name,
        name="under-test-vm-ovs-dpdk-dual",
        client=unprivileged_client,
        primary_resource_claim_name=UNDER_TEST_VM_RESOURCE_CLAIM_NAME_0,
        secondary_resource_claim_name=UNDER_TEST_VM_RESOURCE_CLAIM_NAME_1,
        primary_host_address=UNDER_TEST_VM_HOST_ADDRESS,
        secondary_host_address=UNDER_TEST_VM_SECOND_HOST_ADDRESS,
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
