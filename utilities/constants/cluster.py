"""Cluster infrastructure constants.

Covers Kubernetes node labels (architecture, worker role, CPU model prefix, TSC
frequency, version), generic node dict keys (NODE_STR), pod security namespace labels, Kubernetes API verb strings,
environment variables (KUBECONFIG, WORKERS_TYPE), CNV test run markers, service
account names, the base network-exception dictionary, and audit-log command strings.

Not here:
- Architecture identifier strings (AMD_64, ARM_64, …) → ``architecture.py``
- CPU model exclusion lists → ``cpu_models.py``
- VM CPU/memory topology → ``virt.py``
- Networking pod specs → ``networking.py``
- Pytest/test-runner strings → ``pytest.py``
"""

from kubernetes.dynamic.exceptions import InternalServerError
from ocp_resources.resource import Resource
from urllib3.exceptions import (
    MaxRetryError,
    NewConnectionError,
    ProtocolError,
    ResponseError,
)

# Node / selector labels
KUBERNETES_ARCH_LABEL = f"{Resource.ApiGroup.KUBERNETES_IO}/arch"
NODE_STR = "node"
NODE_TYPE_WORKER_LABEL = {"node-type": "worker"}
NODE_ROLE_KUBERNETES_IO = "node-role.kubernetes.io"
WORKER_NODE_LABEL_KEY = f"{NODE_ROLE_KUBERNETES_IO}/worker"
VERSION_LABEL_KEY = f"{Resource.ApiGroup.APP_KUBERNETES_IO}/version"
CPU_MODEL_LABEL_PREFIX = f"cpu-model.node.{Resource.ApiGroup.KUBEVIRT_IO}"
TSC_FREQUENCY = "tsc-frequency"

POD_SECURITY_NAMESPACE_LABELS = {
    "pod-security.kubernetes.io/enforce": "privileged",
    "security.openshift.io/scc.podSecurityLabelSync": "false",
}

# CNV test run markers
CNV_TEST_RUN_IN_PROGRESS = "cnv-tests-run-in-progress"
CNV_TEST_RUN_IN_PROGRESS_NS = f"{CNV_TEST_RUN_IN_PROGRESS}-ns"

# Service accounts and containers
CNV_TEST_SERVICE_ACCOUNT = "cnv-tests-sa"
CNV_TESTS_CONTAINER = "CNV_TESTS_CONTAINER"
UTILITY = "utility"

# Environment variables
KUBECONFIG = "KUBECONFIG"
WORKERS_TYPE = "WORKERS_TYPE"
RHSM_SECRET_NAME = "rhsm-secret"

# Kubernetes API verb strings
GET_STR = "get"
CREATE_STR = "create"
UPDATE_STR = "update"
DELETE_STR = "delete"
VALUE_STR = "value"

# Shell commands
LS_COMMAND = "ls -1 | sort | tr '\\n' ' '"

# Audit log commands
OC_ADM_LOGS_COMMAND = "oc adm node-logs"
AUDIT_LOGS_PATH = "--path=kube-apiserver"

COUNT_FIVE = 5

BASE_EXCEPTIONS_DICT: dict[type[Exception], list[str]] = {
    NewConnectionError: [],
    ConnectionRefusedError: [],
    ProtocolError: [],
    ResponseError: [],
    MaxRetryError: [],
    InternalServerError: [],
    ConnectionResetError: [],
}
