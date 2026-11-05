from __future__ import annotations

import json
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
from utilities.constants.networking import (
    OVS_DPDK_DEVICE_REQUEST_NAME,
    OVS_DPDK_INTERFACE_NAME,
    OVS_DPDK_NETWORK_BINDING_NAME,
    OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_NAME,
    OVS_DPDK_VHOSTUSER_SIDECAR_IMAGE,
)
from utilities.hco import hco_feature_gates_patch

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from libs.vm.spec import VMSpec
    from libs.vm.vm import BaseVirtualMachine

REF_VM_RESOURCE_CLAIM_NAME: Final[str] = "ovs-dpdk-reference-claim"
UNDER_TEST_VM_RESOURCE_CLAIM_NAME: Final[str] = "ovs-dpdk-under-test-claim"
OVS_DPDK_NET_SEED: Final[int] = 10
REF_VM_HOST_ADDRESS: Final[int] = 1
UNDER_TEST_VM_HOST_ADDRESS: Final[int] = 2
GUEST_OVS_DPDK_IFACE_NAME: Final[str] = "eth0"
_KUBEVIRT_JSONPATCH_ANNOTATION_KEY: Final[str] = "kubevirt.kubevirt.io/jsonpatch"
_KUBEVIRT_FEATURE_GATES_JSONPATCH_PATH: Final[str] = "/spec/configuration/developerConfiguration/featureGates/-"
_OVS_DPDK_HCO_FEATURE_GATE_NETWORK_DEVICES_WITH_DRA: Final[str] = "NetworkDevicesWithDRA"


def _kubevirt_jsonpatch_already_adds_network_devices_with_dra(patches: list[Any]) -> bool:
    return any(
        patch.get("op") == "add"
        and patch.get("path") == _KUBEVIRT_FEATURE_GATES_JSONPATCH_PATH
        and patch.get("value") == _OVS_DPDK_HCO_FEATURE_GATE_NETWORK_DEVICES_WITH_DRA
        for patch in patches
    )


def ovs_dpdk_hco_cnv_integration_patch(
    hco_resource: HyperConverged,
    existing_jsonpatch_annotation: str | None = None,
) -> dict[str, Any]:
    """Patch HCO for OVS-DPDK: vhostuser sidecar binding and ``NetworkDevicesWithDRA``.

    Enables the gate on HCO ``spec.featureGates`` (CNV 5.1+) and, when missing from the
    current ``kubevirt.kubevirt.io/jsonpatch`` annotation, adds a KubeVirt jsonpatch op so
    the gate appears on KubeVirt ``developerConfiguration.featureGates`` before DRA VMs
    are created (required by the VM admission webhook on older CNV).

    Args:
        hco_resource: HyperConverged CR whose current ``spec.featureGates`` list is preserved.
        existing_jsonpatch_annotation: Current ``kubevirt.kubevirt.io/jsonpatch`` on HyperConverged.

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

    existing_patches: list[Any] = []
    if existing_jsonpatch_annotation:
        try:
            parsed = json.loads(existing_jsonpatch_annotation)
        except json.JSONDecodeError, TypeError:
            parsed = None
        if isinstance(parsed, list):
            existing_patches = parsed

    if not _kubevirt_jsonpatch_already_adds_network_devices_with_dra(existing_patches):
        merged_jsonpatch = existing_patches + [
            {
                "op": "add",
                "path": _KUBEVIRT_FEATURE_GATES_JSONPATCH_PATH,
                "value": _OVS_DPDK_HCO_FEATURE_GATE_NETWORK_DEVICES_WITH_DRA,
            },
        ]
        patch.setdefault("metadata", {})["annotations"] = {
            _KUBEVIRT_JSONPATCH_ANNOTATION_KEY: json.dumps(merged_jsonpatch),
        }
    return patch


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
                    "exactly": {"deviceClassName": "ovsdpdk"},
                },
            ],
            "config": [
                {
                    "opaque": {
                        "driver": "ovsdpdk.k8snetworkplumbingwg.io",
                        "parameters": {
                            "apiVersion": "ovsdpdk.k8snetworkplumbingwg.io/v1alpha1",
                            "kind": "OvsPortConfig",
                        },
                    },
                },
            ],
        },
    }


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
