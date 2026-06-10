"""Miscellaneous constants with no specific thematic home.

Before adding a constant here, verify no other module fits:
- Timeouts → ``timeouts.py``
- VM runtime config → ``virt.py``
- Component names → ``components.py``
- Instance types / preferences → ``instance_types.py``
- OS matrix keys → ``os_matrix.py``
- Networking config → ``networking.py``
- Storage → ``storage.py``
- HCO configuration → ``hco.py``

Appropriate here: architecture identifiers, CPU/memory sizing, cluster infrastructure
labels, pytest configuration strings, pod/container specs, OADP file names.
"""

from kubernetes.dynamic.exceptions import InternalServerError
from ocp_resources.resource import Resource
from urllib3.exceptions import (
    MaxRetryError,
    NewConnectionError,
    ProtocolError,
    ResponseError,
)

# Architecture constants
KUBERNETES_ARCH_LABEL = f"{Resource.ApiGroup.KUBERNETES_IO}/arch"
AMD_64 = "amd64"
ARM_64 = "arm64"
S390X = "s390x"
X86_64 = "x86_64"
MULTIARCH = "multiarch"
# Supported architectures for multi-arch runs
SUPPORTED_MULTIARCH_OPTIONS = {AMD_64, ARM_64}
# Supported architectures for single-arch runs
SUPPORTED_CPU_ARCHITECTURES = {AMD_64, ARM_64, S390X}

# Miscellaneous constants
UTILITY = "utility"
WORKERS_TYPE = "WORKERS_TYPE"
DEPENDENCY_SCOPE_SESSION = "session"
QUARANTINED = "quarantined"
SETUP_ERROR = "setup_error"

# Kernel Device Driver
# Compute: GPU Devices are bound to this Kernel Driver for GPU Passthrough.
# Networking: For SRIOV Node Policy, The driver type for the virtual functions
KERNEL_DRIVER = "vfio-pci"

# SSH constants
CNV_VM_SSH_KEY_PATH = "CNV-SSH-KEY-PATH"

# CPU ARCH
INTEL = "Intel"
AMD = "AMD"

# unprivileged_client constants
UNPRIVILEGED_USER = "unprivileged-user"
UNPRIVILEGED_PASSWORD = "unprivileged-password"

# KUBECONFIG variables
KUBECONFIG = "KUBECONFIG"

# commands
LS_COMMAND = "ls -1 | sort | tr '\n' ' '"

ONE_CPU_CORE = 1
ONE_CPU_THREAD = 1
TWO_CPU_CORES = 2
TWO_CPU_SOCKETS = 2
TWO_CPU_THREADS = 2
FOUR_CPU_SOCKETS = 4
SIX_CPU_SOCKETS = 6
EIGHT_CPU_SOCKETS = 8
TEN_CPU_SOCKETS = 10

FOUR_GI_MEMORY = "4Gi"
FIVE_GI_MEMORY = "5Gi"
SIX_GI_MEMORY = "6Gi"
TEN_GI_MEMORY = "10Gi"
TWELVE_GI_MEMORY = "12Gi"

# pytest configuration
SANITY_TESTS_FAILURE = 99

POD_SECURITY_NAMESPACE_LABELS = {
    "pod-security.kubernetes.io/enforce": "privileged",
    "security.openshift.io/scc.podSecurityLabelSync": "false",
}
CNV_TEST_RUN_IN_PROGRESS = "cnv-tests-run-in-progress"
CNV_TEST_RUN_IN_PROGRESS_NS = f"{CNV_TEST_RUN_IN_PROGRESS}-ns"

VERSION_LABEL_KEY = f"{Resource.ApiGroup.APP_KUBERNETES_IO}/version"
NODE_ROLE_KUBERNETES_IO = "node-role.kubernetes.io"
WORKER_NODE_LABEL_KEY = f"{NODE_ROLE_KUBERNETES_IO}/worker"

COUNT_FIVE = 5
UPDATE_STR = "update"
VALUE_STR = "value"
GET_STR = "get"
CREATE_STR = "create"
DELETE_STR = "delete"
WILDCARD_CRON_EXPRESSION = "* * * * *"
OUTDATED = "Outdated"

PROMETHEUS_K8S = "prometheus-k8s"

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

OC_ADM_LOGS_COMMAND = "oc adm node-logs"
AUDIT_LOGS_PATH = "--path=kube-apiserver"
CNV_TEST_SERVICE_ACCOUNT = "cnv-tests-sa"

BASE_EXCEPTIONS_DICT: dict[type[Exception], list[str]] = {
    NewConnectionError: [],
    ConnectionRefusedError: [],
    ProtocolError: [],
    ResponseError: [],
    MaxRetryError: [],
    InternalServerError: [],
    ConnectionResetError: [],
}

CNV_TESTS_CONTAINER = "CNV_TESTS_CONTAINER"

CNV_SUPPLEMENTAL_TEMPLATES_URL = "https://raw.githubusercontent.com/RHsyseng/cnv-supplemental-templates/main/templates"

LINUX_AMD_64 = "linux/amd64"

# OADP
FILE_NAME_FOR_BACKUP = "file_before_backup.txt"
TEXT_TO_TEST = "text"
BACKUP_STORAGE_LOCATION = "dpa-1"

DEFAULT_FEDORA_REGISTRY_URL = "docker://quay.io/containerdisks/fedora:latest"
REGISTRY_STR = "registry"

RHSM_SECRET_NAME = "rhsm-secret"

CAPACITY = "capacity"
USED = "used"

# High performance & Numa related constants
NODE_HUGE_PAGES_1GI_KEY = "hugepages-1Gi"
