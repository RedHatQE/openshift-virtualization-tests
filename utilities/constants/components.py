"""CNV component names and Kubernetes resource kind strings.

Covers strings that identify deployed Kubernetes resources by name — operators,
deployments, daemonsets, pods, services — plus the kind strings used alongside them
(e.g. ``DEPLOYMENT_STR``, ``PROMETHEUSRULE_STR``).

Rule of thumb: if you would use the constant in ``kubectl get <kind>/<name>``, it belongs here.

Not here:
- HCO conditions, CRD lists, feature gate keys → ``hco.py``
- Networking config (bridge types, kubemacpool config map names) → ``networking.py``
- Node selector labels and infrastructure labels (including CPU model / TSC labels) → ``cluster.py``
"""

from ocp_resources.api_service import APIService
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.config_map import ConfigMap
from ocp_resources.deployment import Deployment
from ocp_resources.role_binding import RoleBinding
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount

# Operators
HCO_OPERATOR = "hco-operator"
CDI_OPERATOR = "cdi-operator"
SSP_OPERATOR = "ssp-operator"
HOSTPATH_PROVISIONER_OPERATOR = "hostpath-provisioner-operator"
CNAO_OPERATOR = "cnao-operator"
CLUSTER_NETWORK_ADDONS_OPERATOR = "cluster-network-addons-operator"
AAQ_OPERATOR = "aaq-operator"
KUBEVIRT_OPERATOR = "kubevirt-operator"
KUBEVIRT_MIGRATION_OPERATOR = "kubevirt-migration-operator"
HYPERCONVERGED_CLUSTER_OPERATOR = "hyperconverged-cluster-operator"
VIRT_OPERATOR = "virt-operator"

# Deployments / controllers
VIRT_API = "virt-api"
VIRT_CONTROLLER = "virt-controller"
VIRT_TEMPLATE_VALIDATOR = "virt-template-validator"
VIRT_EXPORTPROXY = "virt-exportproxy"
VIRT_PLATFORM_AUTOPILOT = "virt-platform-autopilot"
VIRT_SYNCHRONIZATION_CONTROLLER = "virt-synchronization-controller"
KUBEVIRT_MIGRATION_CONTROLLER = "kubevirt-migration-controller"
CDI_APISERVER = "cdi-apiserver"
CDI_DEPLOYMENT = "cdi-deployment"
CDI_UPLOADPROXY = "cdi-uploadproxy"
HCO_WEBHOOK = "hco-webhook"
KUBEMACPOOL_CERT_MANAGER = "kubemacpool-cert-manager"
KUBEMACPOOL_MAC_CONTROLLER_MANAGER = "kubemacpool-mac-controller-manager"
KUBEVIRT_IPAM_CONTROLLER_MANAGER = "kubevirt-ipam-controller-manager"
KUBEVIRT_CONSOLE_PLUGIN = "kubevirt-console-plugin"
KUBEVIRT_APISERVER_PROXY = "kubevirt-apiserver-proxy"

# DaemonSets
VIRT_HANDLER = "virt-handler"
BRIDGE_MARKER = "bridge-marker"
KUBE_CNI_LINUX_BRIDGE_PLUGIN = "kube-cni-linux-bridge-plugin"
HOSTPATH_PROVISIONER_CSI = "hostpath-provisioner-csi"

# Pods / launcher
VIRT_LAUNCHER = "virt-launcher"
HPP_POOL = "hpp-pool"

# HPP
HOSTPATH_PROVISIONER = "hostpath-provisioner"

# HCO metadata
HCO_CATALOG_SOURCE = "hco-catalogsource"
HCO_BEARER_AUTH = "hco-bearer-auth"
HCO_PART_OF_LABEL_VALUE = "hyperconverged-cluster"
MANAGED_BY_LABEL_VALUE_OLM = "olm"
KUBEVIRT_HCO_NAME = "kubevirt-kubevirt-hyperconverged"

# KubeVirt / CDI CR names
KUBEVIRT_KUBEVIRT_HYPERCONVERGED = "kubevirt-kubevirt-hyperconverged"
CDI_KUBEVIRT_HYPERCONVERGED = "cdi-kubevirt-hyperconverged"
SSP_KUBEVIRT_HYPERCONVERGED = "ssp-kubevirt-hyperconverged"
MIGCONTROLLER_KUBEVIRT_HYPERCONVERGED = "migcontroller-kubevirt-hyperconverged"
CLUSTER = "cluster"
HYPERCONVERGED_CLUSTER = "hyperconverged-cluster"
KUBEVIRT_CLUSTER_CRITICAL = "kubevirt-cluster-critical"

# Console / UI
KUBEVIRT_CONSOLE_PLUGIN_SERVICE = "kubevirt-console-plugin-service"
KUBEVIRT_CONSOLE_PLUGIN_NP = "kubevirt-console-plugin-np"
KUBEVIRT_APISERVER_PROXY_NP = "kubevirt-apiserver-proxy-np"
KUBEVIRT_PLUGIN = "kubevirt-plugin"
KUBEVIRT_UI_CONFIG = "kubevirt-ui-config"
KUBEVIRT_USER_SETTINGS = "kubevirt-user-settings"
KUBEVIRT_UI_FEATURES = "kubevirt-ui-features"
KUBEVIRT_UI_CONFIG_READER = "kubevirt-ui-config-reader"
KUBEVIRT_UI_CONFIG_READER_ROLE_BINDING = "kubevirt-ui-config-reader-rolebinding"

# Prometheus / monitoring component names
KUBEVIRT_HYPERCONVERGED_PROMETHEUS_RULE = "kubevirt-hyperconverged-prometheus-rule"
KUBEMACPOOL_PROMETHEUS_RULE = "kubemacpool-prometheus-rule"
HYPERCONVERGED_CLUSTER_OPERATOR_METRICS = "hyperconverged-cluster-operator-metrics"
KUBEVIRT_HYPERCONVERGED_OPERATOR_METRICS = "kubevirt-hyperconverged-operator-metrics"
PROMETHEUS_RULES_STR = "prometheus-rules"

# Misc resource names
HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD = "hyperconverged-cluster-cli-download"
NGINX_CONF = "nginx-conf"
WINDOWS_BOOTSOURCE_PIPELINE = "windows-bootsource-pipeline"
VIRTCTL_CLI_DOWNLOADS = "virtctl-clidownloads-kubevirt-hyperconverged"
VIRTIO_WIN = "virtio-win"
UPLOAD_BOOT_SOURCE = "upload-boot-source"
CREATING_VIRTUAL_MACHINE = "creating-virtual-machine"
CREATING_VIRTUAL_MACHINE_FROM_VOLUME = "creating-virtual-machine-from-volume"
GRAFANA_DASHBOARD_KUBEVIRT_TOP_CONSUMERS = "grafana-dashboard-kubevirt-top-consumers"
RHEL9_STR = "rhel9"
RHEL10_STR = "rhel10"
RHEL8_GUEST = "rhel8-guest"
RHEL9_GUEST = "rhel9-guest"
RHEL10_GUEST = "rhel10-guest"

# Kubernetes resource kind strings
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
CDI_STR = "CDI"
SSP_STR = "SSP"
SECRET_STR = "Secret"
NETWORKPOLICY_STR = "NetworkPolicy"
SERVICEACCOUNT_STR = "ServiceAccount"

# All HCO related objects with kind
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
    {VIRTCTL_CLI_DOWNLOADS: CONSOLECLIDOWNLOAD_STR},
    {HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD: ROUTE_STR},
    {HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD: SERVICE_STR},
    {KUBEVIRT_CONSOLE_PLUGIN_SERVICE: SERVICE_STR},
    {f"{KUBEVIRT_APISERVER_PROXY}-{SERVICE_STR.lower()}": SERVICE_STR},
    {KUBEVIRT_APISERVER_PROXY: DEPLOYMENT_STR},
    {KUBEVIRT_CONSOLE_PLUGIN: SERVICEACCOUNT_STR},
    {KUBEVIRT_APISERVER_PROXY: SERVICEACCOUNT_STR},
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
    {MIGCONTROLLER_KUBEVIRT_HYPERCONVERGED: "MigController"},
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
    KUBEVIRT_MIGRATION_OPERATOR,
    KUBEVIRT_MIGRATION_CONTROLLER,
    SSP_OPERATOR,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_HANDLER,
    VIRT_OPERATOR,
    VIRT_TEMPLATE_VALIDATOR,
    VIRT_EXPORTPROXY,
    KUBEVIRT_APISERVER_PROXY,
    KUBEVIRT_IPAM_CONTROLLER_MANAGER,
    VIRT_PLATFORM_AUTOPILOT,
    VIRT_SYNCHRONIZATION_CONTROLLER,
]
ALL_CNV_PODS = [*CNV_PODS_NO_HPP_CSI_HPP_POOL, HOSTPATH_PROVISIONER_CSI, HPP_POOL]
ALL_CNV_DEPLOYMENTS = [
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
    HPP_POOL,
    KUBEVIRT_MIGRATION_OPERATOR,
    KUBEVIRT_MIGRATION_CONTROLLER,
    VIRT_PLATFORM_AUTOPILOT,
    VIRT_SYNCHRONIZATION_CONTROLLER,
]
ALL_CNV_DAEMONSETS = [
    BRIDGE_MARKER,
    HOSTPATH_PROVISIONER_CSI,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    VIRT_HANDLER,
]

CNV_OPERATORS = [
    AAQ_OPERATOR,
    CDI_OPERATOR,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HOSTPATH_PROVISIONER_OPERATOR,
    HYPERCONVERGED_CLUSTER_OPERATOR,
    KUBEVIRT_MIGRATION_OPERATOR,
    KUBEVIRT_OPERATOR,
    SSP_OPERATOR,
    HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
    VIRT_PLATFORM_AUTOPILOT,
]

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
