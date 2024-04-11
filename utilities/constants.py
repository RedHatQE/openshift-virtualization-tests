from ocp_resources.resource import Resource

KUBELET_READY_CONDITION = {"KubeletReady": "True"}
IMAGE_CRON_STR = "image-cron"
TIMEOUT_1MIN = 1 * 60
TIMEOUT_2MIN = 2 * 60
TIMEOUT_5SEC = 5
CNV_TEST_SERVICE_ACCOUNT = "cnv-tests-sa"
NODE_ROLE_KUBERNETES_IO = "node-role.kubernetes.io"
WORKER_NODE_LABEL_KEY = f"{NODE_ROLE_KUBERNETES_IO}/worker"
WORKERS_TYPE = "WORKERS_TYPE"
POD_SECURITY_NAMESPACE_LABELS = {
    "pod-security.kubernetes.io/enforce": "privileged",
    "security.openshift.io/scc.podSecurityLabelSync": "false",
}
HYPERCONVERGED_NAME = "kubevirt-hyperconverged"
AMD_64 = "amd64"
VIRTCTL = "virtctl"
VIRTCTL_CLI_DOWNLOADS = f"{VIRTCTL}-clidownloads-kubevirt-hyperconverged"


class NamespacesNames:
    OPENSHIFT = "openshift"
    OPENSHIFT_MONITORING = "openshift-monitoring"
    OPENSHIFT_CONFIG = "openshift-config"
    OPENSHIFT_APISERVER = "openshift-apiserver"
    OPENSHIFT_STORAGE = "openshift-storage"
    OPENSHIFT_CLUSTER_STORAGE_OPERATOR = "openshift-cluster-storage-operator"
    CHAOS = "chaos"
    DEFAULT = "default"
    NVIDIA_GPU_OPERATOR = "nvidia-gpu-operator"
    OPENSHIFT_MARKETPLACE = "openshift-marketplace"


class StorageClassNames:
    CEPH_RBD = "ocs-storagecluster-ceph-rbd"
    CEPH_RBD_VIRTUALIZATION = f"{CEPH_RBD}-virtualization"


DEFAULT_HCO_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.RECONCILE_COMPLETE: Resource.Condition.Status.TRUE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
    Resource.Condition.UPGRADEABLE: Resource.Condition.Status.TRUE,
}
