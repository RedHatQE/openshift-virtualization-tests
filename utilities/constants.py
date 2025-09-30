from kubernetes.dynamic.exceptions import InternalServerError
from ocp_resources.aaq import AAQ
from ocp_resources.api_service import APIService
from ocp_resources.cdi import CDI
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.config_map import ConfigMap
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.resource import Resource
from ocp_resources.role_binding import RoleBinding
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount
from ocp_resources.ssp import SSP
from urllib3.exceptions import (
    MaxRetryError,
    NewConnectionError,
    ProtocolError,
    ResponseError,
)

from libs.infra.images import (
    BASE_IMAGES_DIR,
    Alpine,
    Cdi,
    Centos,
    Cirros,
    Fedora,
    Rhel,
    Windows,
)
from utilities.architecture import get_cluster_architecture

# Architecture constants
KUBERNETES_ARCH_LABEL = f"{Resource.ApiGroup.KUBERNETES_IO}/arch"
AMD_64 = "amd64"
ARM_64 = "arm64"
S390X = "s390x"
X86_64 = "x86_64"

#  OS constants
OS_FLAVOR_CIRROS = "cirros"
OS_FLAVOR_WINDOWS = "win"
OS_FLAVOR_RHEL = "rhel"
OS_FLAVOR_FEDORA = "fedora"


class ArchImages:
    class X86_64:  # noqa: N801
        BASE_CIRROS_NAME = "cirros-0.4.0-x86_64-disk"
        BASE_ALPINE_NAME = "alpine-3.20.1-x86_64-disk"
        Cirros = Cirros(
            RAW_IMG=f"{BASE_CIRROS_NAME}.raw",
            RAW_IMG_GZ=f"{BASE_CIRROS_NAME}.raw.gz",
            RAW_IMG_XZ=f"{BASE_CIRROS_NAME}.raw.xz",
            QCOW2_IMG=f"{BASE_CIRROS_NAME}.qcow2",
            QCOW2_IMG_GZ=f"{BASE_CIRROS_NAME}.qcow2.gz",
            QCOW2_IMG_XZ=f"{BASE_CIRROS_NAME}.qcow2.xz",
            DISK_DEMO="cirros-registry-disk-demo",
        )

        Alpine = Alpine(
            QCOW2_IMG=f"{BASE_ALPINE_NAME}.qcow2",
        )

        Rhel = Rhel(
            RHEL7_9_IMG="rhel-79.qcow2",
            RHEL8_0_IMG="rhel-8.qcow2",
            RHEL8_9_IMG="rhel-89.qcow2",
            RHEL8_10_IMG="rhel-810.qcow2",
            RHEL9_3_IMG="rhel-93.qcow2",
            RHEL9_4_IMG="rhel-94.qcow2",
            RHEL9_6_IMG="rhel-96.qcow2",
        )
        Rhel.LATEST_RELEASE_STR = Rhel.RHEL9_6_IMG

        Windows = Windows(
            WIN10_IMG="win_10_uefi.qcow2",
            WIN10_WSL2_IMG="win_10_wsl2_uefi.qcow2",
            WIN10_ISO_IMG="Win10_22H2_English_x64.iso",
            WIN2k16_IMG="win_2k16_uefi.qcow2",
            WIN2k19_IMG="win_2k19_uefi.qcow2",
            WIN2k25_IMG="win_2k25_uefi.qcow2",
            WIN2k19_HA_IMG="win_2019_virtio.qcow2",
            WIN11_IMG="win_11.qcow2",
            WIN11_WSL2_IMG="win_11_wsl2.qcow2",
            WIN11_ISO_IMG="en-us_windows_11_business_editions_version_24h2_x64_dvd_59a1851e.iso",
            WIN19_RAW="win_2k19_uefi.raw",
            WIN2022_IMG="win_2022.qcow2",
            WIN2022_ISO_IMG="Windows_Server_2022_x64FRE_en-us.iso",
            WIN2025_ISO_IMG="windows_server_2025_x64_dvd_eval.iso",
        )
        Windows.LATEST_RELEASE_STR = Windows.WIN2k19_IMG

        Fedora = Fedora(
            FEDORA42_IMG="Fedora-Cloud-Base-Generic-42-1.1.x86_64.qcow2",
            FEDORA_CONTAINER_IMAGE="quay.io/openshift-cnv/qe-cnv-tests-fedora:41",
            DISK_DEMO="fedora-cloud-registry-disk-demo",
        )
        Fedora.LATEST_RELEASE_STR = Fedora.FEDORA42_IMG

        Centos = Centos(CENTOS_STREAM_9_IMG="CentOS-Stream-GenericCloud-9-20220107.0.x86_64.qcow2")
        Centos.LATEST_RELEASE_STR = Centos.CENTOS_STREAM_9_IMG

        Cdi = Cdi(QCOW2_IMG="cirros-qcow2.img")

    class ARM64:
        BASE_ALPINE_NAME = "alpine-3.20.1-aarch64-disk"
        Cirros = Cirros(
            RAW_IMG_XZ="cirros-0.4.0-aarch64-disk.raw.xz",
        )

        Alpine = Alpine(
            QCOW2_IMG=f"{BASE_ALPINE_NAME}.qcow2",
        )

        Rhel = Rhel(
            RHEL9_5_IMG="rhel-95-aarch64.qcow2",
            RHEL9_6_IMG="rhel-96-aarch64.qcow2",
        )
        Rhel.LATEST_RELEASE_STR = Rhel.RHEL9_6_IMG

        Windows = Windows()
        Fedora = Fedora()
        Centos = Centos()
        Cdi = Cdi()

    class S390X:
        BASE_ALPINE_NAME = "alpine-3.20.1-s390x-disk"
        Cirros = Cirros(
            # TODO: S390X does not support Cirros; this is a workaround until tests are moved to Fedora
            RAW_IMG="Fedora-Cloud-Base-Generic-41-1.4.s390x.raw",
            RAW_IMG_GZ="Fedora-Cloud-Base-Generic-41-1.4.s390x.raw.gz",
            RAW_IMG_XZ="Fedora-Cloud-Base-Generic-41-1.4.s390x.raw.xz",
            QCOW2_IMG="Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2",
            QCOW2_IMG_GZ="Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2.gz",
            QCOW2_IMG_XZ="Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2.xz",
            DISK_DEMO="fedora-cloud-registry-disk-demo",
            DIR=f"{BASE_IMAGES_DIR}/fedora-images",
            DEFAULT_DV_SIZE="10Gi",
            DEFAULT_MEMORY_SIZE="1Gi",
            OS_FLAVOR=OS_FLAVOR_FEDORA,
        )

        Alpine = Alpine(
            QCOW2_IMG=f"{BASE_ALPINE_NAME}.qcow2",
        )

        Rhel = Rhel(
            RHEL8_0_IMG="rhel-82-s390x.qcow2",
            RHEL8_9_IMG="rhel-89-s390x.qcow2",
            RHEL8_10_IMG="rhel-810-s390x.qcow2",
            RHEL9_3_IMG="rhel-93-s390x.qcow2",
            RHEL9_4_IMG="rhel-94-s390x.qcow2",
            RHEL9_6_IMG="rhel-96-s390x.qcow2",
        )
        Rhel.LATEST_RELEASE_STR = Rhel.RHEL9_6_IMG

        Fedora = Fedora(
            FEDORA42_IMG="Fedora-Cloud-Base-Generic-42-1.1.s390x.qcow2",
            FEDORA_CONTAINER_IMAGE="quay.io/openshift-cnv/qe-cnv-tests-fedora:41-s390x",
            DISK_DEMO="fedora-cloud-registry-disk-demo",
        )
        Fedora.LATEST_RELEASE_STR = Fedora.FEDORA42_IMG

        Centos = Centos(CENTOS_STREAM_9_IMG="CentOS-Stream-GenericCloud-9-latest.s390x.qcow2")
        Centos.LATEST_RELEASE_STR = Centos.CENTOS_STREAM_9_IMG

        Cdi = Cdi(
            # TODO: S390X does not support Cirros; this is a workaround until tests are moved to Fedora
            QCOW2_IMG="Fedora-qcow2.img",
            DIR=f"{BASE_IMAGES_DIR}/fedora-images",
            DEFAULT_DV_SIZE="10Gi",
        )

        Windows = Windows()


# Choose the Image class according to the architecture. Default: x86_64
Images = getattr(ArchImages, get_cluster_architecture().upper())


# Virtctl constants
VIRTCTL = "virtctl"
VIRTCTL_CLI_DOWNLOADS = f"{VIRTCTL}-clidownloads-kubevirt-hyperconverged"
#  Network constants
SRIOV = "sriov"
IP_FAMILY_POLICY_PREFER_DUAL_STACK = "PreferDualStack"
MTU_9000 = 9000
IPV4_STR = "ipv4"
IPV6_STR = "ipv6"
CLUSTER_NETWORK_ADDONS_OPERATOR = "cluster-network-addons-operator"
BRIDGE_MARKER = "bridge-marker"
KUBE_CNI_LINUX_BRIDGE_PLUGIN = "kube-cni-linux-bridge-plugin"
LINUX_BRIDGE = "linux-bridge"
OVS_BRIDGE = "ovs-bridge"
FLAT_OVERLAY_STR = "layer2"
KUBEMACPOOL_CERT_MANAGER = "kubemacpool-cert-manager"
KUBEMACPOOL_MAC_CONTROLLER_MANAGER = "kubemacpool-mac-controller-manager"
KUBEVIRT_IPAM_CONTROLLER_MANAGER = "kubevirt-ipam-controller-manager"
KUBEMACPOOL_MAC_RANGE_CONFIG = "kubemacpool-mac-range-config"
NMSTATE_HANDLER = "nmstate-handler"
ISTIO_SYSTEM_DEFAULT_NS = "istio-system"
SSH_PORT_22 = 22
PORT_80 = 80
ACTIVE_BACKUP = "active-backup"

#  Time constants
TIMEOUT_1SEC = 1
TIMEOUT_5SEC = 5
TIMEOUT_10SEC = 10
TIMEOUT_15SEC = 15
TIMEOUT_20SEC = 20
TIMEOUT_30SEC = 30
TIMEOUT_40SEC = 40
TIMEOUT_90SEC = 90
TIMEOUT_1MIN = 60
TIMEOUT_2MIN = 2 * 60
TIMEOUT_3MIN = 3 * 60
TIMEOUT_4MIN = 4 * 60
TIMEOUT_5MIN = 5 * 60
TIMEOUT_6MIN = 6 * 60
TIMEOUT_8MIN = 8 * 60
TIMEOUT_9MIN = 9 * 60
TIMEOUT_10MIN = 10 * 60
TIMEOUT_11MIN = 11 * 60
TIMEOUT_12MIN = 12 * 60
TIMEOUT_15MIN = 15 * 60
TIMEOUT_20MIN = 20 * 60
TIMEOUT_25MIN = 25 * 60
TIMEOUT_30MIN = 30 * 60
TIMEOUT_35MIN = 35 * 60
TIMEOUT_40MIN = 40 * 60
TIMEOUT_50MIN = 50 * 60
TIMEOUT_60MIN = 60 * 60
TIMEOUT_75MIN = 75 * 60
TIMEOUT_90MIN = 90 * 60
TIMEOUT_180MIN = 180 * 60
TIMEOUT_12HRS = 12 * 60 * 60

TCP_TIMEOUT_30SEC = 30.0


# OpenShift Virtualization components constants
VIRT_OPERATOR = "virt-operator"
VIRT_LAUNCHER = "virt-launcher"
VIRT_API = "virt-api"
VIRT_CONTROLLER = "virt-controller"
VIRT_HANDLER = "virt-handler"
VIRT_TEMPLATE_VALIDATOR = "virt-template-validator"
VIRT_EXPORTPROXY = "virt-exportproxy"
SSP_KUBEVIRT_HYPERCONVERGED = "ssp-kubevirt-hyperconverged"
SSP_OPERATOR = "ssp-operator"
CDI_OPERATOR = "cdi-operator"
CDI_APISERVER = "cdi-apiserver"
CDI_DEPLOYMENT = "cdi-deployment"
CDI_UPLOADPROXY = "cdi-uploadproxy"
HCO_OPERATOR = "hco-operator"
HCO_WEBHOOK = "hco-webhook"
HOSTPATH_CSI_BASIC = "hostpath-csi-basic"
HOSTPATH_PROVISIONER_CSI = "hostpath-provisioner-csi"
HOSTPATH_PROVISIONER = "hostpath-provisioner"
HOSTPATH_PROVISIONER_OPERATOR = "hostpath-provisioner-operator"
HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD = "hyperconverged-cluster-cli-download"
KUBEVIRT_HCO_NAME = "kubevirt-kubevirt-hyperconverged"
HCO_PART_OF_LABEL_VALUE = "hyperconverged-cluster"
MANAGED_BY_LABEL_VALUE_OLM = "olm"
HPP_POOL = "hpp-pool"
HCO_CATALOG_SOURCE = "hco-catalogsource"
KUBEVIRT_CONSOLE_PLUGIN = "kubevirt-console-plugin"
CNAO_OPERATOR = "cnao-operator"
HYPERCONVERGED_CLUSTER = "hyperconverged-cluster"
RESOURCE_REQUIREMENTS_KEY_HCO_CR = "resourceRequirements"

# CDI related constants
CDI_LABEL = Resource.ApiGroup.CDI_KUBEVIRT_IO
CDI_UPLOAD = "cdi-upload"
PVC = "pvc"
CDI_UPLOAD_TMP_PVC = f"cdi-upload-tmp-{PVC}"
SOURCE_POD = "source-pod"

CDI_SECRETS = [
    "cdi-apiserver-server-cert",
    "cdi-apiserver-signer",
    "cdi-uploadproxy-server-cert",
    "cdi-uploadproxy-signer",
    "cdi-uploadserver-client-cert",
    "cdi-uploadserver-client-signer",
    "cdi-uploadserver-signer",
]

CDI_CONFIGMAPS = [
    "cdi-apiserver-signer-bundle",
    "cdi-config",
    "cdi-controller-leader-election-helper",
    "cdi-insecure-registries",
    "cdi-uploadproxy-signer-bundle",
    "cdi-uploadserver-client-signer-bundle",
    "cdi-uploadserver-signer-bundle",
]
# Miscellaneous constants
UTILITY = "utility"
WORKERS_TYPE = "WORKERS_TYPE"
QUARANTINED = "quarantined"
SETUP_ERROR = "setup_error"

# Kernel Device Driver
# Compute: GPU Devices are bound to this Kernel Driver for GPU Passthrough.
# Networking: For SRIOV Node Policy, The driver type for the virtual functions
KERNEL_DRIVER = "vfio-pci"

# cloud-init constants
CLOUD_INIT_DISK_NAME = "cloudinitdisk"
CLOUD_INIT_NO_CLOUD = "cloudInitNoCloud"

# Kubemacpool constants
KMP_VM_ASSIGNMENT_LABEL = "mutatevirtualmachines.kubemacpool.io"
KMP_ENABLED_LABEL = "allocate"
KMP_DISABLED_LABEL = "ignore"

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
REMOTE_KUBECONFIG = "REMOTE_KUBECONFIG"

# commands
LS_COMMAND = "ls -1 | sort | tr '\n' ' '"

# hotplug
HOTPLUG_DISK_SERIAL = "1234567890"

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

# pyetest configuration
SANITY_TESTS_FAILURE = 99
HCO_SUBSCRIPTION = "hco-operatorhub"

# VM configuration
LIVE_MIGRATE = "LiveMigrate"
MIGRATION_POLICY_VM_LABEL = {"vm-label": "test-vm"}
ROOTDISK = "rootdisk"
DV_DISK = "dv-disk"

# Upgrade tests configuration
DEPENDENCY_SCOPE_SESSION = "session"

# hco spec
ENABLE_COMMON_BOOT_IMAGE_IMPORT = "enableCommonBootImageImport"

# Common templates constants
DATA_SOURCE_NAME = "DATA_SOURCE_NAME"
DATA_SOURCE_NAMESPACE = "DATA_SOURCE_NAMESPACE"
SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME = "dataImportCronTemplates"
COMMON_TEMPLATES_KEY_NAME = "commonTemplates"

KUBEVIRT_HYPERCONVERGED_PROMETHEUS_RULE = "kubevirt-hyperconverged-prometheus-rule"
HYPERCONVERGED_CLUSTER_OPERATOR_METRICS = "hyperconverged-cluster-operator-metrics"
KUBEVIRT_HYPERCONVERGED_OPERATOR_METRICS = "kubevirt-hyperconverged-operator-metrics"
KUBEVIRT_CLUSTER_CRITICAL = "kubevirt-cluster-critical"
KUBEVIRT_KUBEVIRT_HYPERCONVERGED = "kubevirt-kubevirt-hyperconverged"
CDI_KUBEVIRT_HYPERCONVERGED = "cdi-kubevirt-hyperconverged"
CLUSTER = "cluster"
VIRTCTL_CLIDOWNLOADS_KUBEVIRT_HYPERCONVERGED = f"{VIRTCTL}-clidownloads-kubevirt-hyperconverged"
KUBEVIRT_CONSOLE_PLUGIN_SERVICE = "kubevirt-console-plugin-service"
CREATING_VIRTUAL_MACHINE = "creating-virtual-machine"
CREATING_VIRTUAL_MACHINE_FROM_VOLUME = "creating-virtual-machine-from-volume"
UPLOAD_BOOT_SOURCE = "upload-boot-source"
GRAFANA_DASHBOARD_KUBEVIRT_TOP_CONSUMERS = "grafana-dashboard-kubevirt-top-consumers"
RHEL8_GUEST = "rhel8-guest"
RHEL9_GUEST = "rhel9-guest"
RHEL10_GUEST = "rhel10-guest"
VIRTIO = "virtio"
VIRTIO_WIN = "virtio-win"
NGINX_CONF = "nginx-conf"
HYPERCONVERGED_CLUSTER_OPERATOR = "hyperconverged-cluster-operator"
PROMETHEUS_RULES_STR = "prometheus-rules"
KUBEVIRT_UI_CONFIG = "kubevirt-ui-config"
KUBEVIRT_USER_SETTINGS = "kubevirt-user-settings"
KUBEVIRT_UI_FEATURES = "kubevirt-ui-features"
KUBEVIRT_UI_CONFIG_READER = "kubevirt-ui-config-reader"
KUBEVIRT_UI_CONFIG_READER_ROLE_BINDING = "kubevirt-ui-config-reader-rolebinding"
HCO_BEARER_AUTH = "hco-bearer-auth"
KUBEVIRT_CONSOLE_PLUGIN_NP = "kubevirt-console-plugin-np"
KUBEVIRT_APISERVER_PROXY_NP = "kubevirt-apiserver-proxy-np"
# components kind
ROLEBINDING_STR = "RoleBinding"
POD_STR = "Pod"
PROMETHEUSRULE_STR = "PrometheusRule"
ROLE_STR = "Role"
SERVICE_STR = "Service"
SERVICEMONITOR_STR = "ServiceMonitor"
PRIORITYCLASS_STR = "PriorityClass"
KUBEVIRT_STR = "KubeVirt"
NETWORKADDONSCONFIG_STR = "NetworkAddonsConfig"
CONSOLECLIDOWNLOAD_STR = "ConsoleCLIDownload"
ROUTE_STR = "Route"
CONSOLEQUICKSTART_STR = "ConsoleQuickStart"
CONFIGMAP_STR = "ConfigMap"
IMAGESTREAM_STR = "ImageStream"
DEPLOYMENT_STR = "Deployment"
CONSOLE_PLUGIN_STR = "ConsolePlugin"
KUBEVIRT_PLUGIN = "kubevirt-plugin"
CDI_STR = "CDI"
SSP_STR = "SSP"
SECRET_STR = "Secret"
KUBEVIRT_APISERVER_PROXY = "kubevirt-apiserver-proxy"
NETWORKPOLICY_STR = "NetworkPolicy"
AAQ_OPERATOR = "aaq-operator"
WINDOWS_BOOTSOURCE_PIPELINE = "windows-bootsource-pipeline"
# All hco relate objects with kind
ALL_HCO_RELATED_OBJECTS = [
    {KUBEVIRT_HYPERCONVERGED_PROMETHEUS_RULE: PROMETHEUSRULE_STR},
    {HYPERCONVERGED_CLUSTER_OPERATOR_METRICS: ROLE_STR},
    {HYPERCONVERGED_CLUSTER_OPERATOR_METRICS: ROLEBINDING_STR},
    {KUBEVIRT_HYPERCONVERGED_OPERATOR_METRICS: SERVICE_STR},
    {KUBEVIRT_HYPERCONVERGED_OPERATOR_METRICS: SERVICEMONITOR_STR},
    {KUBEVIRT_CLUSTER_CRITICAL: PRIORITYCLASS_STR},
    {KUBEVIRT_KUBEVIRT_HYPERCONVERGED: KUBEVIRT_STR},
    {CDI_KUBEVIRT_HYPERCONVERGED: CDI_STR},
    {CLUSTER: NETWORKADDONSCONFIG_STR},
    {SSP_KUBEVIRT_HYPERCONVERGED: SSP_STR},
    {VIRTCTL_CLIDOWNLOADS_KUBEVIRT_HYPERCONVERGED: CONSOLECLIDOWNLOAD_STR},
    {HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD: ROUTE_STR},
    {HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD: SERVICE_STR},
    {KUBEVIRT_CONSOLE_PLUGIN_SERVICE: SERVICE_STR},
    {f"{KUBEVIRT_APISERVER_PROXY}-{SERVICE_STR.lower()}": SERVICE_STR},
    {KUBEVIRT_APISERVER_PROXY: DEPLOYMENT_STR},
    {CREATING_VIRTUAL_MACHINE: CONSOLEQUICKSTART_STR},
    {CREATING_VIRTUAL_MACHINE_FROM_VOLUME: CONSOLEQUICKSTART_STR},
    {UPLOAD_BOOT_SOURCE: CONSOLEQUICKSTART_STR},
    {GRAFANA_DASHBOARD_KUBEVIRT_TOP_CONSUMERS: CONFIGMAP_STR},
    {RHEL8_GUEST: IMAGESTREAM_STR},
    {RHEL9_GUEST: IMAGESTREAM_STR},
    {RHEL10_GUEST: IMAGESTREAM_STR},
    {VIRTIO_WIN: CONFIGMAP_STR},
    {VIRTIO_WIN: ROLE_STR},
    {VIRTIO_WIN: ROLEBINDING_STR},
    {KUBEVIRT_CONSOLE_PLUGIN: DEPLOYMENT_STR},
    {NGINX_CONF: CONFIGMAP_STR},
    {KUBEVIRT_PLUGIN: CONSOLE_PLUGIN_STR},
    {WINDOWS_BOOTSOURCE_PIPELINE: CONSOLEQUICKSTART_STR},
    {KUBEVIRT_USER_SETTINGS: CONFIGMAP_STR},
    {KUBEVIRT_UI_FEATURES: CONFIGMAP_STR},
    {KUBEVIRT_UI_CONFIG_READER: ROLE_STR},
    {KUBEVIRT_UI_CONFIG_READER_ROLE_BINDING: ROLEBINDING_STR},
    {HCO_BEARER_AUTH: SECRET_STR},
    {KUBEVIRT_CONSOLE_PLUGIN_NP: NETWORKPOLICY_STR},
    {KUBEVIRT_APISERVER_PROXY_NP: NETWORKPOLICY_STR},
]
CNV_PODS_NO_HPP_CSI_HPP_POOL = [
    AAQ_OPERATOR,
    BRIDGE_MARKER,
    CDI_APISERVER,
    CDI_DEPLOYMENT,
    CDI_OPERATOR,
    CDI_UPLOADPROXY,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    HOSTPATH_PROVISIONER_OPERATOR,
    HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    KUBEMACPOOL_CERT_MANAGER,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    KUBEVIRT_CONSOLE_PLUGIN,
    SSP_OPERATOR,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_HANDLER,
    VIRT_OPERATOR,
    VIRT_TEMPLATE_VALIDATOR,
    VIRT_EXPORTPROXY,
    KUBEVIRT_APISERVER_PROXY,
    KUBEVIRT_IPAM_CONTROLLER_MANAGER,
]
ALL_CNV_PODS = CNV_PODS_NO_HPP_CSI_HPP_POOL + [HOSTPATH_PROVISIONER_CSI]
ALL_CNV_DEPLOYMENTS_NO_HPP_POOL = [
    AAQ_OPERATOR,
    CDI_APISERVER,
    CDI_DEPLOYMENT,
    CDI_OPERATOR,
    CDI_UPLOADPROXY,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    HOSTPATH_PROVISIONER_OPERATOR,
    HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
    KUBEMACPOOL_CERT_MANAGER,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    KUBEVIRT_CONSOLE_PLUGIN,
    SSP_OPERATOR,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_OPERATOR,
    VIRT_TEMPLATE_VALIDATOR,
    VIRT_EXPORTPROXY,
    KUBEVIRT_APISERVER_PROXY,
    KUBEVIRT_IPAM_CONTROLLER_MANAGER,
]
ALL_CNV_DEPLOYMENTS = ALL_CNV_DEPLOYMENTS_NO_HPP_POOL + [HPP_POOL]
ALL_CNV_DAEMONSETS_NO_HPP_CSI = [
    BRIDGE_MARKER,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    VIRT_HANDLER,
]
ALL_CNV_DAEMONSETS = [HOSTPATH_PROVISIONER_CSI] + ALL_CNV_DAEMONSETS_NO_HPP_CSI


CNV_OPERATORS = [
    AAQ_OPERATOR,
    CDI_OPERATOR,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HOSTPATH_PROVISIONER_OPERATOR,
    HYPERCONVERGED_CLUSTER_OPERATOR,
    "kubevirt-operator",
    SSP_OPERATOR,
    HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
]
# Node labels
NODE_TYPE_WORKER_LABEL = {"node-type": "worker"}
CPU_MODEL_LABEL_PREFIX = f"cpu-model.node.{Resource.ApiGroup.KUBEVIRT_IO}"
NODE_ROLE_KUBERNETES_IO = "node-role.kubernetes.io"
WORKER_NODE_LABEL_KEY = f"{NODE_ROLE_KUBERNETES_IO}/worker"
CDI_KUBEVIRT_HYPERCONVERGED = "cdi-kubevirt-hyperconverged"
TSC_FREQUENCY = "tsc-frequency"

# Container constants
CNV_TESTS_CONTAINER = "CNV_TESTS_CONTAINER"
DEFAULT_HCO_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.RECONCILE_COMPLETE: Resource.Condition.Status.TRUE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
    Resource.Condition.UPGRADEABLE: Resource.Condition.Status.TRUE,
}
DEFAULT_KUBEVIRT_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.CREATED: Resource.Condition.Status.TRUE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
}
DEFAULT_RESOURCE_CONDITIONS = {
    Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
    Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
    Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
}
EXPECTED_STATUS_CONDITIONS = {
    HyperConverged: DEFAULT_HCO_CONDITIONS,
    KubeVirt: DEFAULT_KUBEVIRT_CONDITIONS,
    CDI: DEFAULT_RESOURCE_CONDITIONS,
    SSP: DEFAULT_RESOURCE_CONDITIONS,
    NetworkAddonsConfig: DEFAULT_RESOURCE_CONDITIONS,
    AAQ: DEFAULT_RESOURCE_CONDITIONS,
}
BREW_REGISTERY_SOURCE = "brew.registry.redhat.io"
ICSP_FILE = "imageContentSourcePolicy.yaml"
IDMS_FILE = "imageDigestMirrorSet.yaml"
BASE_EXCEPTIONS_DICT: dict[type[Exception], list[str]] = {
    NewConnectionError: [],
    ConnectionRefusedError: [],
    ProtocolError: [],
    ResponseError: [],
    MaxRetryError: [],
    InternalServerError: [],
    ConnectionResetError: [],
}

# Container images
NET_UTIL_CONTAINER_IMAGE = "quay.io/openshift-cnv/qe-cnv-tests-net-util-container:centos-stream-9"


OC_ADM_LOGS_COMMAND = "oc adm node-logs"
AUDIT_LOGS_PATH = "--path=kube-apiserver"
CNV_TEST_SERVICE_ACCOUNT = "cnv-tests-sa"
VM_CRD = f"virtualmachines.{Resource.ApiGroup.KUBEVIRT_IO}"
VM_CLONE_CRD = f"virtualmachineclones.clone.{Resource.ApiGroup.KUBEVIRT_IO}"
VM_EXPORT_CRD = f"virtualmachineexports.export.{Resource.ApiGroup.KUBEVIRT_IO}"
ALL_CNV_CRDS = [
    f"aaqs.{Resource.ApiGroup.AAQ_KUBEVIRT_IO}",
    f"cdiconfigs.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"cdis.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"dataimportcrons.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"datasources.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"datavolumes.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"hostpathprovisioners.{Resource.ApiGroup.HOSTPATHPROVISIONER_KUBEVIRT_IO}",
    f"hyperconvergeds.{Resource.ApiGroup.HCO_KUBEVIRT_IO}",
    f"kubevirts.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"migrationpolicies.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
    f"networkaddonsconfigs.{Resource.ApiGroup.NETWORKADDONSOPERATOR_NETWORK_KUBEVIRT_IO}",
    f"objecttransfers.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"ssps.{Resource.ApiGroup.SSP_KUBEVIRT_IO}",
    f"storageprofiles.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"virtualmachineclusterinstancetypes.{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}",
    f"virtualmachineinstancetypes.{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}",
    f"virtualmachineinstancemigrations.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachineinstancepresets.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachineinstancereplicasets.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachineinstances.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"virtualmachinepools.{Resource.ApiGroup.POOL_KUBEVIRT_IO}",
    f"virtualmachinerestores.{Resource.ApiGroup.SNAPSHOT_KUBEVIRT_IO}",
    VM_CRD,
    f"virtualmachinesnapshotcontents.{Resource.ApiGroup.SNAPSHOT_KUBEVIRT_IO}",
    f"virtualmachinesnapshots.{Resource.ApiGroup.SNAPSHOT_KUBEVIRT_IO}",
    VM_CLONE_CRD,
    f"virtualmachineclusterpreferences.{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}",
    VM_EXPORT_CRD,
    f"virtualmachinepreferences.{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}",
    f"volumeuploadsources.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"volumeimportsources.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"volumeclonesources.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"openstackvolumepopulators.forklift.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
    f"ovirtvolumepopulators.forklift.{Resource.ApiGroup.CDI_KUBEVIRT_IO}",
]
PRODUCTION_CATALOG_SOURCE = "redhat-operators"
TLS_OLD_POLICY = "old"
TLS_CUSTOM_POLICY = "custom"
HOTFIX_STR = "hotfix"


class UpgradeStreams:
    X_STREAM = "x-stream"
    Y_STREAM = "y-stream"
    Z_STREAM = "z-stream"


IMAGE_CRON_STR = "image-cron"
TLS_SECURITY_PROFILE = "tlsSecurityProfile"
KUBELET_READY_CONDITION = {"KubeletReady": "True"}
CNV_PROMETHEUS_RULES = [
    f"{PROMETHEUS_RULES_STR}-{CLUSTER_NETWORK_ADDONS_OPERATOR}",
    KUBEVIRT_HYPERCONVERGED_PROMETHEUS_RULE,
    "prometheus-cdi-rules",
    "prometheus-hpp-rules",
    "prometheus-k8s-rules-cnv",
    "prometheus-kubevirt-rules",
    f"kubevirt-cnv-{PROMETHEUS_RULES_STR}",
]


class StorageClassNames:
    CEPH_RBD = "ocs-storagecluster-ceph-rbd"
    CEPH_RBD_VIRTUALIZATION = f"{CEPH_RBD}-virtualization"
    CEPHFS = "ocs-storagecluster-cephfs"
    HOSTPATH = "hostpath-provisioner"
    NFS = "nfs"
    TOPOLVM = "lvms-vg1"
    PORTWORX_CSI_DB_SHARED = "px-csi-db-shared"
    RH_INTERNAL_NFS = "rh-internal-nfs"
    TRIDENT_CSI_FSX = "trident-csi-fsx"
    TRIDENT_CSI_NFS = "trident-csi-nfs"
    IO2_CSI = "io2-csi"
    GPFS = "ibm-spectrum-scale-sample"
    OCI = "oci-bv"
    OCI_UHP = "oci-bv-uhp"
    GCP = "sp-balanced-storage"
    GCNV = "gcnv-flex"


# Namespace constants
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


# CNV supplemental-templates
CNV_SUPPLEMENTAL_TEMPLATES_URL = "https://raw.githubusercontent.com/RHsyseng/cnv-supplemental-templates/main/templates"

LINUX_AMD_64 = "linux/amd64"

EVICTIONSTRATEGY = "evictionStrategy"
CRITICAL_STR = "critical"
INFO_STR = "info"
KUBEVIRT_HYPERCONVERGED_OPERATOR_HEALTH_STATUS = "kubevirt_hyperconverged_operator_health_status"
WARNING_STR = "warning"
NONE_STRING = "none"
ACCESS_MODE = "access_mode"
VOLUME_MODE = "volume_mode"
OPERATOR_HEALTH_IMPACT_VALUES = {
    CRITICAL_STR: "2",
    WARNING_STR: "1",
    NONE_STRING: "0",
}
FIRING_STATE = "firing"
PENDING_STR = "pending"
KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS = "kubevirt_hco_hyperconverged_cr_exists"
ES_LIVE_MIGRATE_IF_POSSIBLE = "LiveMigrateIfPossible"
ES_NONE = "None"
POD_SECURITY_NAMESPACE_LABELS = {
    "pod-security.kubernetes.io/enforce": "privileged",
    "security.openshift.io/scc.podSecurityLabelSync": "false",
}
CNV_TEST_RUN_IN_PROGRESS = "cnv-tests-run-in-progress"
VERSION_LABEL_KEY = f"{Resource.ApiGroup.APP_KUBERNETES_IO}/version"
FEATURE_GATES = "featureGates"
COUNT_FIVE = 5
DATA_IMPORT_CRON_ENABLE = (
    f"metadata->annotations->{DataImportCron.ApiGroup.DATA_IMPORT_CRON_TEMPLATE_KUBEVIRT_IO}/enable"
)
UPDATE_STR = "update"
VALUE_STR = "value"
GET_STR = "get"
CREATE_STR = "create"
DELETE_STR = "delete"
WILDCARD_CRON_EXPRESSION = "* * * * *"
OUTDATED = "Outdated"

RHEL_WITH_INSTANCETYPE_AND_PREFERENCE = "rhel-with-instancetype-and-preference"
CENTOS_STREAM9_PREFERENCE = "centos.stream9"
CENTOS_STREAM10_PREFERENCE = "centos.stream10"
RHEL8_PREFERENCE = "rhel.8"
RHEL9_PREFERENCE = "rhel.9"
RHEL10_PREFERENCE = "rhel.10"
U1_SMALL = "u1.small"
PROMETHEUS_K8S = "prometheus-k8s"
INSTANCE_TYPE_STR = "instance_type"
U1_MEDIUM_STR = "u1.medium"
PREFERENCE_STR = "preference"
FLAVOR_STR = "flavor"
NONE_STR = "<none>"
OS_STR = "os"
LINUX_STR = "linux"
EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS = {
    INSTANCE_TYPE_STR: U1_MEDIUM_STR,
    PREFERENCE_STR: RHEL9_PREFERENCE,
    OS_STR: LINUX_STR,
}

# VM Console Proxy Resources
VM_CONSOLE_PROXY_CLUSTER_RESOURCES = [
    APIService,
    ClusterRole,
    ClusterRoleBinding,
]

VM_CONSOLE_PROXY_NAMESPACE_RESOURCES = [
    ServiceAccount,
    ConfigMap,
    Service,
    Deployment,
    RoleBinding,
]

ARTIFACTORY_SECRET_NAME = "cnv-tests-artifactory-secret"
CNV_TEST_RUN_IN_PROGRESS_NS = f"{CNV_TEST_RUN_IN_PROGRESS}-ns"
BASE_ARTIFACTORY_LOCATION = "artifactory/cnv-qe-server-local"

SECURITY_CONTEXT = "securityContext"

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
# Opteron - Windows image can't boot
# Penryn - does not support WSL2
EXCLUDED_CPU_MODELS = ["Opteron", "Penryn"]
# Latest windows can't boot with old cpu models
EXCLUDED_OLD_CPU_MODELS = [*EXCLUDED_CPU_MODELS, "Westmere", "SandyBridge", "Nehalem", "IvyBridge", "Skylake"]

AAQ_VIRTUAL_RESOURCES = "VirtualResources"
AAQ_VMI_POD_USAGE = "VmiPodUsage"
NODE_STR = "node"
KUBEVIRT_VIRT_OPERATOR_UP = "kubevirt_virt_operator_up"


REGEDIT_PROC_NAME = "regedit.exe"
OS_PROC_NAME = {"linux": "ping", "windows": REGEDIT_PROC_NAME}

DISK_SERIAL = "D23YZ9W6WA5DJ489"
RHSM_SECRET_NAME = "rhsm-secret"

CAPACITY = "capacity"
USED = "used"


# Tekton Tasks and Pipelines
WINDOWS_EFI_INSTALLER_STR = "windows-efi-installer"
WINDOWS_CUSTOMIZE_STR = "windows-customize"
TEKTON_AVAILABLE_PIPELINEREF = [
    WINDOWS_EFI_INSTALLER_STR,
    WINDOWS_CUSTOMIZE_STR,
]

TEKTON_AVAILABLE_TASKS = [
    "modify-data-object",
    "create-vm-from-manifest",
    "wait-for-vmi-status",
    "cleanup-vm",
    "disk-virt-sysprep",
    "disk-virt-customize",
    "modify-windows-iso-file",
    "disk-uploader",
]

# Windows versions
WIN_10 = "win10"
WIN_11 = "win11"
WIN_2K25 = "win2k25"
WIN_2K22 = "win2k22"
WIN_2K16 = "win2k16"
WIN_2K19 = "win2k19"

PUBLIC_DNS_SERVER_IP = "8.8.8.8"

BIND_IMMEDIATE_ANNOTATION = {f"{Resource.ApiGroup.CDI_KUBEVIRT_IO}/storage.bind.immediate.requested": "true"}

HCO_DEFAULT_CPU_MODEL_KEY = "defaultCPUModel"

HPP_CAPABILITIES = {
    VOLUME_MODE: DataVolume.VolumeMode.FILE,
    ACCESS_MODE: DataVolume.AccessMode.RWO,
    "snapshot": False,
    "online_resize": False,
    "wffc": True,
}


KUBEVIRT_VMI_NETWORK_RECEIVE_PACKETS_DROPPED_TOTAL = "kubevirt_vmi_network_receive_packets_dropped_total"
KUBEVIRT_VMI_NETWORK_TRANSMIT_PACKETS_DROPPED_TOTAL = "kubevirt_vmi_network_transmit_packets_dropped_total"
KUBEVIRT_VMI_MEMORY_DOMAIN_BYTES = "kubevirt_vmi_memory_domain_bytes"
KUBEVIRT_VMI_MEMORY_UNUSED_BYTES = "kubevirt_vmi_memory_unused_bytes"
KUBEVIRT_VMI_MEMORY_USABLE_BYTES = "kubevirt_vmi_memory_usable_bytes"
KUBEVIRT_VMI_MEMORY_ACTUAL_BALLOON_BYTES = "kubevirt_vmi_memory_actual_balloon_bytes"
KUBEVIRT_VMI_MEMORY_PGMAJFAULT_TOTAL = "kubevirt_vmi_memory_pgmajfault_total"
KUBEVIRT_VMI_STORAGE_FLUSH_REQUESTS_TOTAL = "kubevirt_vmi_storage_flush_requests_total"
KUBEVIRT_VMI_STORAGE_FLUSH_TIMES_SECONDS_TOTAL = "kubevirt_vmi_storage_flush_times_seconds_total"
KUBEVIRT_VMI_NETWORK_RECEIVE_BYTES_TOTAL = "kubevirt_vmi_network_receive_bytes_total"
KUBEVIRT_VMI_NETWORK_TRANSMIT_BYTES_TOTAL = "kubevirt_vmi_network_transmit_bytes_total"
KUBEVIRT_VMI_STORAGE_IOPS_WRITE_TOTAL = "kubevirt_vmi_storage_iops_write_total"
KUBEVIRT_VMI_STORAGE_IOPS_READ_TOTAL = "kubevirt_vmi_storage_iops_read_total"
KUBEVIRT_VMI_STORAGE_WRITE_TRAFFIC_BYTES_TOTAL = "kubevirt_vmi_storage_write_traffic_bytes_total"
KUBEVIRT_VMI_STORAGE_READ_TRAFFIC_BYTES_TOTAL = "kubevirt_vmi_storage_read_traffic_bytes_total"
KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL = "kubevirt_vmi_vcpu_wait_seconds_total"
KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES = "kubevirt_vmi_memory_swap_in_traffic_bytes"
KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES = "kubevirt_vmi_memory_swap_out_traffic_bytes"
KUBEVIRT_VMI_MEMORY_PGMINFAULT_TOTAL = "kubevirt_vmi_memory_pgminfault_total"

MONITORING_METRICS = [
    KUBEVIRT_VMI_MEMORY_ACTUAL_BALLOON_BYTES,
    KUBEVIRT_VMI_MEMORY_DOMAIN_BYTES,
    KUBEVIRT_VMI_MEMORY_PGMAJFAULT_TOTAL,
    KUBEVIRT_VMI_MEMORY_PGMINFAULT_TOTAL,
    KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_UNUSED_BYTES,
    KUBEVIRT_VMI_MEMORY_USABLE_BYTES,
    KUBEVIRT_VMI_NETWORK_RECEIVE_BYTES_TOTAL,
    KUBEVIRT_VMI_NETWORK_RECEIVE_PACKETS_DROPPED_TOTAL,
    KUBEVIRT_VMI_NETWORK_TRANSMIT_BYTES_TOTAL,
    KUBEVIRT_VMI_NETWORK_TRANSMIT_PACKETS_DROPPED_TOTAL,
    KUBEVIRT_VMI_STORAGE_FLUSH_REQUESTS_TOTAL,
    KUBEVIRT_VMI_STORAGE_FLUSH_TIMES_SECONDS_TOTAL,
    KUBEVIRT_VMI_STORAGE_IOPS_READ_TOTAL,
    KUBEVIRT_VMI_STORAGE_IOPS_WRITE_TOTAL,
    KUBEVIRT_VMI_STORAGE_READ_TRAFFIC_BYTES_TOTAL,
    KUBEVIRT_VMI_STORAGE_WRITE_TRAFFIC_BYTES_TOTAL,
    KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL,
]
# Common templates matrix constants
IMAGE_NAME_STR = "image_name"
IMAGE_PATH_STR = "image_path"
DV_SIZE_STR = "dv_size"
TEMPLATE_LABELS_STR = "template_labels"
OS_STR = "os"
WORKLOAD_STR = "workload"
LATEST_RELEASE_STR = "latest_released"
OS_VERSION_STR = "os_version"
DATA_SOURCE_STR = "data_source"

# OADP
ADP_NAMESPACE = "openshift-adp"
FILE_NAME_FOR_BACKUP = "file_before_backup.txt"
TEXT_TO_TEST = "text"
BACKUP_STORAGE_LOCATION = "dpa-1"

# AAQ
AAQ_NAMESPACE_LABEL = {"application-aware-quota/enable-gating": ""}
VM_CPU_CORES = 2
REQUESTS_INSTANCES_VMI_STR = "requests.instances/vmi"
REQUESTS_CPU_VMI_STR = "requests.cpu/vmi"
REQUESTS_MEMORY_VMI_STR = "requests.memory/vmi"
PODS_STR = "pods"
LIMITS_CPU_STR = "limits.cpu"
LIMITS_MEMORY_STR = "limits.memory"
REQUESTS_CPU_STR = "requests.cpu"
REQUESTS_MEMORY_STR = "requests.memory"
POD_REQUESTS_CPU = 2
POD_REQUESTS_MEMORY = "2.5Gi"
POD_LIMITS_CPU = POD_REQUESTS_CPU * 2
POD_LIMITS_MEMORY = f"{float(POD_REQUESTS_MEMORY[:-2]) * 2}Gi"
VM_MEMORY_GUEST = "2Gi"
QUOTA_FOR_POD = {
    PODS_STR: "1",
    LIMITS_CPU_STR: POD_LIMITS_CPU,
    LIMITS_MEMORY_STR: POD_LIMITS_MEMORY,
    REQUESTS_CPU_STR: POD_REQUESTS_CPU,
    REQUESTS_MEMORY_STR: POD_LIMITS_MEMORY,
}

QUOTA_FOR_ONE_VMI = {
    REQUESTS_INSTANCES_VMI_STR: "1",
    REQUESTS_CPU_VMI_STR: VM_CPU_CORES,
    REQUESTS_MEMORY_VMI_STR: VM_MEMORY_GUEST,
}

ARQ_QUOTA_HARD_SPEC = {**QUOTA_FOR_POD, **QUOTA_FOR_ONE_VMI}
