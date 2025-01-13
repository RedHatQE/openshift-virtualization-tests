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
SERVICE_MESH_PORT = 8080
HTTPBIN_COMMAND = f"gunicorn -b 0.0.0.0:{SERVICE_MESH_PORT} -w 1 httpbin:app"
BRCNV = "brcnv"
