from ocp_resources.resource import Resource

from utilities.constants import (
    TIMEOUT_10SEC,
    WORKER_NODE_LABEL_KEY,
)

NODE_KUBELET_STOP = "node_kubelet_stop"
NODE_SHUTDOWN = "node_shutdown"

NODE_ACTIONS_DICT = {
    NODE_KUBELET_STOP: "sudo systemctl stop kubelet.service",
    NODE_SHUTDOWN: "sudo shutdown -h now",
}
NODE_HEALTH_DETECTION_OPERATOR = "node-health-check-operator"
REMEDIATION_OPERATOR_NAMESPACE = "openshift-workload-availability"

# constants for NodeHealthCheck CR
SELECTOR_MATCH_EXPRESSIONS = [{"key": WORKER_NODE_LABEL_KEY, "operator": "Exists"}]


UNHEALTHY_CONDITIONS = [
    {"type": Resource.Status.READY, "status": Resource.Condition.Status.FALSE, "duration": f"{TIMEOUT_10SEC}s"},
    {"type": Resource.Status.READY, "status": Resource.Condition.Status.UNKNOWN, "duration": f"{TIMEOUT_10SEC}s"},
]
