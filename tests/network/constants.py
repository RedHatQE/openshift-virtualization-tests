from utilities.constants import CLUSTER_NETWORK_ADDONS_OPERATOR

EXPECTED_CNAO_COMP_NAMES = [
    "multus",
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    "kubemacpool",
    "bridge",
    "ovs-cni",
]
HTTPBIN_IMAGE = "quay.io/openshifttest/httpbin:1.2.2"
ISTIO_SYSTEM_DEFAULT_NS = "istio-system"
MTU_9000 = 9000
NMSTATE_HANDLER = "nmstate-handler"
KMP_DISABLED_LABEL = "ignore"
