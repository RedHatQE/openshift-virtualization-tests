from utilities.constants import CLUSTER_NETWORK_ADDONS_OPERATOR

DHCP_IP_RANGE_START = "10.200.3.3"
DHCP_IP_RANGE_END = "10.200.3.10"
IPV4_ADDRESS_SUBNET_PREFIX = "10.200.0"
EXPECTED_CNAO_COMP_NAMES = [
    "multus",
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    "kubemacpool",
    "bridge",
    "ovs-cni",
]
HTTPBIN_IMAGE = "quay.io/openshifttest/httpbin:1.2.2"
BRCNV = "brcnv"
