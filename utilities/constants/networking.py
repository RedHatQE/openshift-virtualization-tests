"""Networking configuration constants.

Covers SR-IOV identifiers, bridge types, IP family policy strings, port numbers,
KubeMacPool configuration names, bonding modes, DNS/label strings, OVS-DPDK DRA lane
values (must match cluster day-0 lane manifests), and network test pod specs
(security context, container spec).

For CNV network component deployment/pod name strings use ``components.py``.
"""

from typing import Final

SRIOV = "sriov"
IP_FAMILY_POLICY_PREFER_DUAL_STACK = "PreferDualStack"
IPV4_STR = "ipv4"
IPV6_STR = "ipv6"
LINUX_BRIDGE = "linux-bridge"
OVS_BRIDGE = "ovs-bridge"
FLAT_OVERLAY_STR = "layer2"
KUBEMACPOOL_MAC_RANGE_CONFIG = "kubemacpool-mac-range-config"
SSH_PORT_22 = 22
PORT_80 = 80
ACTIVE_BACKUP = "active-backup"
KMP_VM_ASSIGNMENT_LABEL = "mutatevirtualmachines.kubemacpool.io"
KMP_ENABLED_LABEL = "allocate"
PUBLIC_DNS_SERVER_IP = "8.8.8.8"

# ovs-dpdk
OVS_DPDK_DEVICE_CLASS_NAME: Final[str] = "ovsdpdk"
OVS_DPDK_DRA_DRIVER_NAMESPACE: Final[str] = "dra-driver-ovsdpdk"
OVS_DPDK_DRA_OPAQUE_DRIVER: Final[str] = "ovsdpdk.k8snetworkplumbingwg.io"
OVS_DPDK_OVS_PORT_CONFIG_MTU: Final[int] = 1800
OVS_DPDK_RESOURCE_CLAIM_TEMPLATE_NAME: Final[str] = "my-claim-template"
OVS_DPDK_DEVICE_REQUEST_NAME: Final[str] = "vhost1"
OVS_DPDK_NETWORK_BINDING_NAME: Final[str] = "vhostuser"
OVS_DPDK_VHOSTUSER_SIDECAR_IMAGE: Final[str] = "quay.io/kubevirt/vhostuser-network-binding-plugin:v0.1.0"
OVS_DPDK_KUBEVIRT_FEATURE_GATE_NETWORK_DEVICES_WITH_DRA: Final[str] = "NetworkDevicesWithDRA"
OVS_DPDK_KUBEVIRT_FEATURE_GATE_SIDECAR: Final[str] = "Sidecar"
OVS_DPDK_INTERFACE_NAME: Final[str] = "ovs-dpdk-iface"
OVS_DPDK_NET_SEED: Final[int] = 10
OVS_DPDK_TESTS_RELATIVE_PATH: Final[str] = "network/ovs_dpdk"

# Network test pod specs
SECURITY_CONTEXT = "securityContext"
NET_UTIL_CONTAINER_IMAGE = "quay.io/openshift-cnv/qe-net-utils:latest"

POD_SECURITY_CONTEXT_SPEC = {
    "seccompProfile": {"type": "RuntimeDefault"},
    "runAsNonRoot": True,
    "runAsUser": 1000,
    "fsGroup": 107,
}

POD_CONTAINER_SPEC = {
    "name": "runner",
    "image": NET_UTIL_CONTAINER_IMAGE,
    "command": [
        "/bin/bash",
        "-c",
        "echo ok > /tmp/healthy && sleep INF",
    ],
    SECURITY_CONTEXT: {
        "allowPrivilegeEscalation": False,
        "seccompProfile": {"type": "RuntimeDefault"},
        "runAsNonRoot": True,
        "capabilities": {"drop": ["ALL"]},
    },
}
