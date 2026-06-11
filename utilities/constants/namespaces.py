"""Namespace name constants.

NamespacesNames groups well-known OpenShift and CNV namespace strings.
ADP_NAMESPACE is a module-level constant used independently of the class.
"""


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
    MACHINE_API_NAMESPACE = "machine-api-namespace"
    OPENSHIFT_VIRTUALIZATION_OS_IMAGES = "openshift-virtualization-os-images"
    WASP = "wasp"
    OPENSHIFT_KUBE_DESCHEDULER_OPERATOR = "openshift-kube-descheduler-operator"
    OPENSHIFT_NMSTATE = "openshift-nmstate"
    OPENSHIFT_FRR_K8S = "openshift-frr-k8s"
    OPENSHIFT_MTV = "openshift-mtv"
    CNV_TESTS_UTILITIES = "cnv-tests-utilities"


ADP_NAMESPACE = "openshift-adp"
