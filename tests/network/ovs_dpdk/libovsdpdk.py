from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
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

GUEST_OVS_DPDK_IFACE_NAME: Final[str] = "eth0"
GUEST_OVS_DPDK_SECOND_IFACE_NAME: Final[str] = "eth1"
OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_NAME: Final[str] = "my-claim-template"
OVS_DPDK_DRA_DRIVER_NAME: Final[str] = "ovsdpdk.k8snetworkplumbingwg.io"
OVS_DPDK_PORT_CONFIG_API_VERSION: Final[str] = "ovsdpdk.k8snetworkplumbingwg.io/v1alpha1"
OVS_DPDK_PORT_CONFIG_KIND: Final[str] = "OvsPortConfig"
OVS_DPDK_DEVICE_REQUEST_NAME: Final[str] = "vhost1"
OVS_DPDK_NETWORK_BINDING_NAME: Final[str] = "vhostuser"
OVS_DPDK_VHOSTUSER_SIDECAR_IMAGE: Final[str] = "quay.io/kubevirt/vhostuser-network-binding-plugin:v0.1.0"
OVS_DPDK_INTERFACE_NAME: Final[str] = "ovs-dpdk-iface"
OVS_DPDK_SECOND_INTERFACE_NAME: Final[str] = "ovs-dpdk-iface-2"
_OVS_DPDK_HCO_FEATURE_GATE_NETWORK_DEVICES_WITH_DRA: Final[str] = "NetworkDevicesWithDRA"


@dataclass(frozen=True)
class OvsDpdkIface:
    """One OVS-DPDK vhost-user interface on a VM.

    Attributes:
        spec_name: Network and Interface name in the VM spec.
        guest_name: Guest OS interface name (cloud-init ``ethernets`` key).
        claim_name: Pod-local ResourceClaim name.
        claim_template_name: ResourceClaimTemplate for the claim (VLAN when the RCT is tagged).
        host_address: host part of the static guest address, unique per VM interface on the shared subnet.
    """

    spec_name: str
    guest_name: str
    claim_name: str
    claim_template_name: str
    host_address: int


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


def ovs_dpdk_vlan_resource_claim_template_spec(vlan: int) -> dict[str, Any]:
    """Build ResourceClaimSpec devices for a VLAN-tagged OVS-DPDK ResourceClaimTemplate.

    Args:
        vlan: VLAN ID for driver ``OvsPortConfig`` on the allocated port.

    Returns:
        ``spec_spec`` for ``ocp_resources.resource_claim_template.ResourceClaimTemplate``.
    """
    spec = ovs_dpdk_resource_claim_template_spec()
    spec["devices"]["config"] = [
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
    return spec


def ovs_dpdk_resource_claim_template_spec() -> dict[str, Any]:
    """Build ResourceClaimSpec devices for the OVS-DPDK lane ResourceClaimTemplate.

    Returns:
        ``spec_spec`` for ``ocp_resources.resource_claim_template.ResourceClaimTemplate``
        (device requests only). The OVS-DPDK driver uses default untagged port settings when
        no per-allocation ``OvsPortConfig`` is supplied.
    """
    return {
        "devices": {
            "requests": [
                {
                    "name": OVS_DPDK_DEVICE_REQUEST_NAME,
                    "exactly": {"deviceClassName": "ovsdpdk"},
                },
            ],
        },
    }


@contextmanager
def ovs_dpdk_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    ifaces: list[OvsDpdkIface],
    net_seed: int,
    runcmd: list[str] | None = None,
) -> Generator[BaseVirtualMachine]:
    """Create an OVS-DPDK VM with one or more RCT-backed vhost-user interfaces.

    Args:
        namespace: Target namespace for the VM.
        name: VM name prefix.
        client: Kubernetes dynamic client.
        ifaces: Per-interface claim and addressing wiring.
        net_seed: Subnet seed for ``random_cidr_addresses_by_family`` on each interface.
        runcmd: Optional cloud-init ``runcmd`` (e.g. ARP isolation on dual-NIC VMs).

    Yields:
        BaseVirtualMachine configured with cloud-init.
    """
    spec = ovs_dpdk_vm_spec(ifaces=ifaces)
    ethernets = {}
    for iface in ifaces:
        addresses = random_cidr_addresses_by_family(
            net_seed=net_seed,
            host_address=iface.host_address,
        )
        ethernets[iface.guest_name] = cloudinit.EthernetDevice(
            addresses=[str(address) for address in addresses],
        )
    with fedora_vm(
        namespace=namespace,
        name=name,
        client=client,
        spec=spec,
    ) as vm:
        net_data = cloudinit.NetworkData(ethernets=ethernets)
        vm.add_cloud_init(netdata=net_data, runcmd=runcmd)
        yield vm


def ovs_dpdk_vm_spec(ifaces: list[OvsDpdkIface]) -> VMSpec:
    """Build a VM spec with one or more RCT-backed OVS-DPDK vhost-user interfaces.

    Args:
        ifaces: Per-interface claim wiring; VLAN follows each entry's ``claim_template_name``.

    Returns:
        VMSpec configured for OVS-DPDK vhost-user binding via ResourceClaimTemplate.
    """
    spec = base_vmspec()
    vmi_spec = spec.template.spec
    vmi_spec.networks = [
        Network(
            name=iface.spec_name,
            resourceClaim=NetworkResourceClaim(
                claimName=iface.claim_name,
                requestName=OVS_DPDK_DEVICE_REQUEST_NAME,
            ),
        )
        for iface in ifaces
    ]
    vmi_spec.resourceClaims = [
        ResourceClaim(
            name=iface.claim_name,
            resourceClaimTemplateName=iface.claim_template_name,
        )
        for iface in ifaces
    ]
    vmi_spec.domain.devices = vmi_spec.domain.devices or Devices()
    vmi_spec.domain.devices.interfaces = [
        Interface(name=iface.spec_name, binding=NetBinding(name=OVS_DPDK_NETWORK_BINDING_NAME)) for iface in ifaces
    ]
    return spec
