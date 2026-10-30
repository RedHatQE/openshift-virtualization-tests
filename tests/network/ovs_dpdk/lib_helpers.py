from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Final

from libs.net.ip import filter_link_local_addresses, random_cidr_addresses_by_family
from libs.net.vmspec import lookup_iface_status
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import (
    Devices,
    Interface,
    NetBinding,
    Network,
    NetworkResourceClaim,
    VMResourceClaim,
)
from tests.network.libs import cloudinit
from tests.network.libs.connectivity import poll_tcp_connectivity
from utilities.constants.networking import (
    OVS_DPDK_DEVICE_CLASS_NAME,
    OVS_DPDK_DEVICE_REQUEST_NAME,
    OVS_DPDK_DRA_DRIVER_NAME,
    OVS_DPDK_INTERFACE_NAME,
    OVS_DPDK_KUBEVIRT_FEATURE_GATE_NETWORK_DEVICES_WITH_DRA,
    OVS_DPDK_KUBEVIRT_FEATURE_GATE_SIDECAR,
    OVS_DPDK_NET_SEED,
    OVS_DPDK_NETWORK_BINDING_NAME,
    OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_NAME,
    OVS_DPDK_VHOSTUSER_SIDECAR_IMAGE,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from libs.vm.spec import VMSpec
    from libs.vm.vm import BaseVirtualMachine

REF_VM_RESOURCE_CLAIM_NAME: Final[str] = "ovs-dpdk-reference-claim"
UNDER_TEST_VM_RESOURCE_CLAIM_NAME: Final[str] = "ovs-dpdk-under-test-claim"
REF_VM_HOST_ADDRESS: Final[int] = 1
UNDER_TEST_VM_HOST_ADDRESS: Final[int] = 2
GUEST_OVS_DPDK_IFACE_NAME: Final[str] = "eth0"
_KUBEVIRT_JSONPATCH_ANNOTATION_KEY: Final[str] = "kubevirt.kubevirt.io/jsonpatch"
_KUBEVIRT_FEATURE_GATES_JSONPATCH_PATH: Final[str] = "/spec/configuration/developerConfiguration/featureGates/-"


def ovs_dpdk_hco_cnv_integration_patch() -> dict[str, Any]:
    """Patch HCO for OVS-DPDK: vhostuser sidecar binding and KubeVirt gates Sidecar + NetworkDevicesWithDRA.

    Returns:
        Patch dict for ``ResourceEditorValidateHCOReconcile`` on the HyperConverged CR.
    """
    kubevirt_feature_gate_patches = [
        {
            "op": "add",
            "path": _KUBEVIRT_FEATURE_GATES_JSONPATCH_PATH,
            "value": OVS_DPDK_KUBEVIRT_FEATURE_GATE_NETWORK_DEVICES_WITH_DRA,
        },
        {
            "op": "add",
            "path": _KUBEVIRT_FEATURE_GATES_JSONPATCH_PATH,
            "value": OVS_DPDK_KUBEVIRT_FEATURE_GATE_SIDECAR,
        },
    ]
    return {
        "spec": {
            "networking": {
                "networkBinding": {
                    OVS_DPDK_NETWORK_BINDING_NAME: {
                        "sidecarImage": OVS_DPDK_VHOSTUSER_SIDECAR_IMAGE,
                    },
                },
            },
        },
        "metadata": {
            "annotations": {
                _KUBEVIRT_JSONPATCH_ANNOTATION_KEY: json.dumps(kubevirt_feature_gate_patches),
            },
        },
    }


def ovs_dpdk_resource_claim_template_spec() -> dict[str, Any]:
    """Build ResourceClaimSpec devices for the OVS-DPDK lane ResourceClaimTemplate.

    Returns:
        ``spec_spec`` for ``ocp_resources.resource_claim_template.ResourceClaimTemplate``
        (device requests and OvsPortConfig), matching the cluster day-0 lane manifest.
    """
    return {
        "devices": {
            "requests": [
                {
                    "name": OVS_DPDK_DEVICE_REQUEST_NAME,
                    "exactly": {"deviceClassName": OVS_DPDK_DEVICE_CLASS_NAME},
                },
            ],
            "config": [
                {
                    "opaque": {
                        "driver": OVS_DPDK_DRA_DRIVER_NAME,
                        "parameters": {
                            "apiVersion": "ovsdpdk.k8snetworkplumbingwg.io/v1alpha1",
                            "kind": "OvsPortConfig",
                        },
                    },
                },
            ],
        },
    }


def ovs_dpdk_rct_vm_spec(resource_claim_name: str) -> VMSpec:
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
        VMResourceClaim(
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
def ovs_dpdk_rct_vm(
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
    spec = ovs_dpdk_rct_vm_spec(resource_claim_name=resource_claim_name)
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


def verify_baseline_connectivity(client_vm: BaseVirtualMachine, ref_vm: BaseVirtualMachine) -> None:
    """Poll until TCP connectivity works successfully on every OVS-DPDK address on the reference VM.

    Args:
        client_vm: VM that initiates connectivity checks toward the reference VM.
        ref_vm: Reference VM that receives traffic on the OVS-DPDK interface.
    """
    ref_iface = lookup_iface_status(vm=ref_vm, iface_name=OVS_DPDK_INTERFACE_NAME)
    for server_ip in filter_link_local_addresses(ip_addresses=ref_iface.ipAddresses):
        poll_tcp_connectivity(
            client_vm=client_vm,
            server_vm=ref_vm,
            server_ip=str(server_ip),
        )
