from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Final

from ocp_resources.hyperconverged import HyperConverged

from libs.net.ip import random_cidr_addresses_by_family
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import (
    Devices,
    Interface,
    NetBinding,
    Network,
    NetworkResourceClaim,
    ResourceClaim,
)
from tests.network.libs import cloudinit
from utilities.hco import hco_feature_gates_patch

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from libs.vm.spec import VMSpec
    from libs.vm.vm import BaseVirtualMachine

REF_VM_RESOURCE_CLAIM_NAME: Final[str] = "ovs-dpdk-reference-claim"
UNDER_TEST_VM_RESOURCE_CLAIM_NAME: Final[str] = "ovs-dpdk-under-test-claim"
REF_VM_RESOURCE_CLAIM_NAME_0: Final[str] = "ovs-dpdk-reference-claim-0"
REF_VM_RESOURCE_CLAIM_NAME_1: Final[str] = "ovs-dpdk-reference-claim-1"
UNDER_TEST_VM_RESOURCE_CLAIM_NAME_0: Final[str] = "ovs-dpdk-under-test-claim-0"
UNDER_TEST_VM_RESOURCE_CLAIM_NAME_1: Final[str] = "ovs-dpdk-under-test-claim-1"
OVS_DPDK_NET_SEED: Final[int] = 10
REF_VM_HOST_ADDRESS: Final[int] = 1
REF_VM_SECOND_HOST_ADDRESS: Final[int] = 3
UNDER_TEST_VM_HOST_ADDRESS: Final[int] = 2
UNDER_TEST_VM_SECOND_HOST_ADDRESS: Final[int] = 4
GUEST_OVS_DPDK_IFACE_NAME: Final[str] = "eth0"
GUEST_OVS_DPDK_SECOND_IFACE_NAME: Final[str] = "eth1"
OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_NAME: Final[str] = "my-claim-template"
OVS_DPDK_VLAN_A: Final[int] = 100
OVS_DPDK_VLAN_B: Final[int] = 200
OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_A_NAME: Final[str] = f"my-claim-template-vlan-{OVS_DPDK_VLAN_A}"
OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_B_NAME: Final[str] = f"my-claim-template-vlan-{OVS_DPDK_VLAN_B}"
OVS_DPDK_DRA_DRIVER_NAME: Final[str] = "ovsdpdk.k8snetworkplumbingwg.io"
OVS_DPDK_PORT_CONFIG_API_VERSION: Final[str] = "ovsdpdk.k8snetworkplumbingwg.io/v1alpha1"
OVS_DPDK_PORT_CONFIG_KIND: Final[str] = "OvsPortConfig"
OVS_DPDK_DEVICE_REQUEST_NAME: Final[str] = "vhost1"
OVS_DPDK_NETWORK_BINDING_NAME: Final[str] = "vhostuser"
OVS_DPDK_VHOSTUSER_SIDECAR_IMAGE: Final[str] = "quay.io/kubevirt/vhostuser-network-binding-plugin:v0.1.0"
OVS_DPDK_INTERFACE_NAME: Final[str] = "ovs-dpdk-iface"
OVS_DPDK_SECOND_INTERFACE_NAME: Final[str] = "ovs-dpdk-iface-2"
_OVS_DPDK_HCO_FEATURE_GATE_NETWORK_DEVICES_WITH_DRA: Final[str] = "NetworkDevicesWithDRA"


def ovs_dpdk_hco_cnv_integration_patch(hco_resource: HyperConverged) -> dict[str, Any]:
    """Patch HCO for OVS-DPDK: vhostuser sidecar binding and ``NetworkDevicesWithDRA``.

    Enables the gate on HCO ``spec.featureGates`` (CNV 5.1+). HCO reconciliation propagates
    the gate to KubeVirt; the ``ovs_dpdk_enabled_in_hco`` fixture waits for KubeVirt reconcile.

    Args:
        hco_resource: HyperConverged CR whose current ``spec.featureGates`` list is preserved.

    Returns:
        Patch dict for ``ResourceEditorValidateHCOReconcile`` on the HyperConverged CR.
    """
    patch = hco_feature_gates_patch(
        hco_resource=hco_resource,
        enable=[_OVS_DPDK_HCO_FEATURE_GATE_NETWORK_DEVICES_WITH_DRA],
    )
    patch["spec"]["networking"] = {
        "networkBinding": {
            OVS_DPDK_NETWORK_BINDING_NAME: {
                "sidecarImage": OVS_DPDK_VHOSTUSER_SIDECAR_IMAGE,
            },
        },
    }
    return patch


def ovs_dpdk_resource_claim_template_spec(vlan: int | None = None) -> dict[str, Any]:
    """Build ResourceClaimSpec devices for the OVS-DPDK lane ResourceClaimTemplate.

    Args:
        vlan: When set, adds ``devices.config`` with driver ``OvsPortConfig`` for that VLAN ID.
            When omitted, the driver applies default untagged port settings.

    Returns:
        ``spec_spec`` for ``ocp_resources.resource_claim_template.ResourceClaimTemplate``.
    """
    devices = {
        "requests": [
            {
                "name": OVS_DPDK_DEVICE_REQUEST_NAME,
                "exactly": {"deviceClassName": "ovsdpdk"},
            },
        ],
    }
    if vlan is not None:
        devices["config"] = [
            {
                "opaque": {
                    "driver": OVS_DPDK_DRA_DRIVER_NAME,
                    "parameters": {
                        "apiVersion": OVS_DPDK_PORT_CONFIG_API_VERSION,
                        "kind": OVS_DPDK_PORT_CONFIG_KIND,
                        "vlan": vlan,
                    },
                },
            },
        ]
    return {"devices": devices}


@contextmanager
def ovs_dpdk_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    resource_claim_name: str,
    host_address: int,
) -> Generator[BaseVirtualMachine]:
    """Create an OVS-DPDK VM backed by a ResourceClaimTemplate-generated claim.

    Args:
        namespace: Target namespace for the VM.
        name: VM name prefix.
        client: Kubernetes dynamic client.
        resource_claim_name: Pod-local ResourceClaim name for the OVS-DPDK device.
        host_address: Host portion of the static address on the OVS-DPDK interface.

    Yields:
        BaseVirtualMachine configured with the OVS-DPDK interface and cloud-init.
    """
    spec = ovs_dpdk_vm_spec(resource_claim_name=resource_claim_name)
    with fedora_vm(
        namespace=namespace,
        name=name,
        client=client,
        spec=spec,
    ) as vm:
        ovs_dpdk_addresses = random_cidr_addresses_by_family(
            net_seed=OVS_DPDK_NET_SEED,
            host_address=host_address,
        )
        ovs_dpdk_guest_ethernet = cloudinit.EthernetDevice(
            addresses=[str(address) for address in ovs_dpdk_addresses],
        )
        vm.add_cloud_init(
            netdata=cloudinit.NetworkData(
                ethernets={GUEST_OVS_DPDK_IFACE_NAME: ovs_dpdk_guest_ethernet},
            )
        )
        yield vm


def ovs_dpdk_vm_spec(resource_claim_name: str) -> VMSpec:
    """Build a VM spec with a single RCT-backed OVS-DPDK vhost-user interface.

    Args:
        resource_claim_name: Pod-local ResourceClaim name referenced from the VM spec.

    Returns:
        VMSpec configured for OVS-DPDK vhost-user binding via ResourceClaimTemplate.
    """
    spec = base_vmspec()
    vmi_spec = spec.template.spec
    vmi_spec.networks = [
        Network(
            name=OVS_DPDK_INTERFACE_NAME,
            resourceClaim=NetworkResourceClaim(
                claimName=resource_claim_name,
                requestName=OVS_DPDK_DEVICE_REQUEST_NAME,
            ),
        ),
    ]
    vmi_spec.resourceClaims = [
        ResourceClaim(
            name=resource_claim_name,
            resourceClaimTemplateName=OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_NAME,
        ),
    ]
    vmi_spec.domain.devices = vmi_spec.domain.devices or Devices()
    vmi_spec.domain.devices.interfaces = [
        Interface(name=OVS_DPDK_INTERFACE_NAME, binding=NetBinding(name=OVS_DPDK_NETWORK_BINDING_NAME)),
    ]
    return spec


@contextmanager
def ovs_dpdk_dual_claim_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    primary_resource_claim_name: str,
    secondary_resource_claim_name: str,
    primary_host_address: int,
    secondary_host_address: int,
) -> Generator[BaseVirtualMachine]:
    """Create an OVS-DPDK VM with two RCT-generated claims on one shared guest subnet.

    Args:
        namespace: Target namespace for the VM.
        name: VM name prefix.
        client: Kubernetes dynamic client.
        primary_resource_claim_name: Pod-local ResourceClaim for the first interface.
        secondary_resource_claim_name: Pod-local ResourceClaim for the second interface.
        primary_host_address: Host portion of static addresses on the first guest interface.
        secondary_host_address: Host portion of static addresses on the second guest interface.

    Yields:
        BaseVirtualMachine with ``eth0`` and ``eth1`` sharing the same IP subnet per family.
    """
    spec = ovs_dpdk_dual_claim_vm_spec(
        primary_resource_claim_name=primary_resource_claim_name,
        secondary_resource_claim_name=secondary_resource_claim_name,
    )
    with fedora_vm(
        namespace=namespace,
        name=name,
        client=client,
        spec=spec,
    ) as vm:
        primary_addresses = random_cidr_addresses_by_family(
            net_seed=OVS_DPDK_NET_SEED,
            host_address=primary_host_address,
        )
        secondary_addresses = random_cidr_addresses_by_family(
            net_seed=OVS_DPDK_NET_SEED,
            host_address=secondary_host_address,
        )
        vm.add_cloud_init(
            netdata=cloudinit.NetworkData(
                ethernets={
                    GUEST_OVS_DPDK_IFACE_NAME: cloudinit.EthernetDevice(
                        addresses=[str(address) for address in primary_addresses],
                    ),
                    GUEST_OVS_DPDK_SECOND_IFACE_NAME: cloudinit.EthernetDevice(
                        addresses=[str(address) for address in secondary_addresses],
                    ),
                },
            )
        )
        yield vm


def ovs_dpdk_dual_claim_vm_spec(
    primary_resource_claim_name: str,
    secondary_resource_claim_name: str,
) -> VMSpec:
    """Build a VM spec with two RCT-backed OVS-DPDK vhost-user interfaces.

    Each interface uses a separate ResourceClaimTemplate-generated claim (VLAN-A and VLAN-B RCTs).

    Args:
        primary_resource_claim_name: Pod-local ResourceClaim for the first interface.
        secondary_resource_claim_name: Pod-local ResourceClaim for the second interface.

    Returns:
        VMSpec with two OVS-DPDK networks on distinct resource claims.
    """
    spec = base_vmspec()
    vmi_spec = spec.template.spec
    vmi_spec.networks = [
        Network(
            name=OVS_DPDK_INTERFACE_NAME,
            resourceClaim=NetworkResourceClaim(
                claimName=primary_resource_claim_name,
                requestName=OVS_DPDK_DEVICE_REQUEST_NAME,
            ),
        ),
        Network(
            name=OVS_DPDK_SECOND_INTERFACE_NAME,
            resourceClaim=NetworkResourceClaim(
                claimName=secondary_resource_claim_name,
                requestName=OVS_DPDK_DEVICE_REQUEST_NAME,
            ),
        ),
    ]
    vmi_spec.resourceClaims = [
        ResourceClaim(
            name=primary_resource_claim_name,
            resourceClaimTemplateName=OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_A_NAME,
        ),
        ResourceClaim(
            name=secondary_resource_claim_name,
            resourceClaimTemplateName=OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_VLAN_B_NAME,
        ),
    ]
    vmi_spec.domain.devices = vmi_spec.domain.devices or Devices()
    vmi_spec.domain.devices.interfaces = [
        Interface(name=OVS_DPDK_INTERFACE_NAME, binding=NetBinding(name=OVS_DPDK_NETWORK_BINDING_NAME)),
        Interface(
            name=OVS_DPDK_SECOND_INTERFACE_NAME,
            binding=NetBinding(name=OVS_DPDK_NETWORK_BINDING_NAME),
        ),
    ]
    return spec
