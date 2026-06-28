"""Networking configuration constants.

Covers SR-IOV identifiers, bridge types, IP family policy strings, port numbers,
KubeMacPool configuration names, bonding modes, DNS/label strings, and network
test pod specs (security context, container spec).

For CNV network component deployment/pod name strings use ``components.py``.
"""

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
