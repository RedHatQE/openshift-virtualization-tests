from typing import Any

import pytest_testconfig
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.virtual_machine import VirtualMachine

from utilities.architecture import get_cluster_architecture
from utilities.constants import (
    AAQ_VIRTUAL_RESOURCES,
    AAQ_VMI_POD_USAGE,
    ALL_CNV_CRDS,
    ALL_CNV_DAEMONSETS,
    ALL_CNV_DEPLOYMENTS,
    ALL_CNV_DEPLOYMENTS_NO_HPP_POOL,
    ALL_CNV_PODS,
    ALL_HCO_RELATED_OBJECTS,
    BASE_ARTIFACTORY_LOCATION,
    BREW_REGISTERY_SOURCE,
    CNV_OPERATORS,
    CNV_PODS_NO_HPP_CSI_HPP_POOL,
    CNV_PROMETHEUS_RULES,
    HCO_CATALOG_SOURCE,
    HPP_CAPABILITIES,
    IPV4_STR,
    IPV6_STR,
    KUBEVIRT_VMI_CPU_SYSTEM_USAGE_SECONDS_TOTAL_QUERY_STR,
    KUBEVIRT_VMI_CPU_USAGE_SECONDS_TOTAL_QUERY_STR,
    KUBEVIRT_VMI_CPU_USER_USAGE_SECONDS_TOTAL_QUERY_STR,
    KUBEVIRT_VMI_VCPU_DELAY_SECONDS_TOTAL_QUERY_STR,
    LINUX_BRIDGE,
    MONITORING_METRICS,
    OVS_BRIDGE,
    PRODUCTION_CATALOG_SOURCE,
    TEKTON_AVAILABLE_PIPELINEREF,
    TEKTON_AVAILABLE_TASKS,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TLS_CUSTOM_POLICY,
    TLS_OLD_POLICY,
    VM_CONSOLE_PROXY_CLUSTER_RESOURCES,
    VM_CONSOLE_PROXY_NAMESPACE_RESOURCES,
    Images,
    NamespacesNames,
    StorageClassNames,
)
from utilities.storage import HppCsiStorageClass

arch = get_cluster_architecture()
global config
global_config = pytest_testconfig.load_python(py_file=f"tests/global_config_{arch}.py", encoding="utf-8")


def _get_default_storage_class(sc_list):
    """
    Args:
        sc_list (list): storage class dict - a list of dicts

    Returns:
        tuple: (default storage class name, default storage class dict) else raises an exception.
    """
    for sc_dict in sc_list:
        for sc_name, sc_values in sc_dict.items():
            if sc_values.get("default"):
                return sc_name, sc_values
    assert False, f"No SC is marked as 'default': {sc_list}"


no_unprivileged_client = False
hco_cr_name = "kubevirt-hyperconverged"
hco_namespace = "openshift-cnv"
openshift_apiserver_namespace = "openshift-apiserver"
sriov_namespace = "openshift-sriov-network-operator"
marketplace_namespace = "openshift-marketplace"
machine_api_namespace = "openshift-machine-api"
golden_images_namespace = NamespacesNames.OPENSHIFT_VIRTUALIZATION_OS_IMAGES
hco_subscription = ""  # TODO: remove constants/HCO_SUBSCRIPTION and use this instead.
disconnected_cluster = False
linux_bridge_cni = "cnv-bridge"
bridge_tuning = "cnv-tuning"

version_explorer_url = ""
server_url = ""  # Send --tc=server_url:<url> to override servers URL
servers = {
    "https_server": f"https://{{server}}/{BASE_ARTIFACTORY_LOCATION}/",
    "registry_server": "docker://{server}",
}

cnv_registry_sources = {
    "osbs": {
        "cnv_subscription_source": HCO_CATALOG_SOURCE,
        "source_map": BREW_REGISTERY_SOURCE,
    },
    "hotfix": {
        "cnv_subscription_source": HCO_CATALOG_SOURCE,
    },
    "production": {
        "cnv_subscription_source": PRODUCTION_CATALOG_SOURCE,
    },
    "fbc": {
        "cnv_subscription_source": HCO_CATALOG_SOURCE,
        "source_map": BREW_REGISTERY_SOURCE,
    },
}

cnv_vm_resources_limits_matrix = [
    "cpu",
    "memory",
]
nic_models_matrix = [
    "virtio",
    "e1000e",
]

cnv_must_gather_matrix = [
    "cnv-gather",
    "all-images",
]

cnv_vm_resource_requests_units_matrix = [
    "cores",
    "sockets",
    "threads",
]


cnv_vmi_monitoring_metrics_matrix = MONITORING_METRICS

cnv_cpu_usage_metrics_matrix = [
    KUBEVIRT_VMI_VCPU_DELAY_SECONDS_TOTAL_QUERY_STR,
    KUBEVIRT_VMI_CPU_USER_USAGE_SECONDS_TOTAL_QUERY_STR,
    KUBEVIRT_VMI_CPU_SYSTEM_USAGE_SECONDS_TOTAL_QUERY_STR,
    KUBEVIRT_VMI_CPU_USAGE_SECONDS_TOTAL_QUERY_STR,
]

bridge_device_matrix = [LINUX_BRIDGE, OVS_BRIDGE]

storage_class_matrix = [
    {
        StorageClassNames.CEPH_RBD_VIRTUALIZATION: {
            "volume_mode": DataVolume.VolumeMode.BLOCK,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": False,
            "default": True,
        }
    },
    {HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC: HPP_CAPABILITIES},
    {HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_BLOCK: HPP_CAPABILITIES},
]

default_storage_class, default_storage_class_configuration = _get_default_storage_class(sc_list=storage_class_matrix)
default_volume_mode = default_storage_class_configuration["volume_mode"]
default_access_mode = default_storage_class_configuration["access_mode"]

storage_class_for_storage_migration_a = HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC
storage_class_for_storage_migration_b = StorageClassNames.CEPH_RBD_VIRTUALIZATION

link_aggregation_mode_matrix = [
    "active-backup",
    "balance-tlb",
    "balance-alb",
]
link_aggregation_mode_no_connectivity_matrix = [
    "balance-xor",
    "802.3ad",
]

vm_volumes_matrix = ["container_disk_vm", "data_volume_vm"]
run_strategy_matrix = [
    VirtualMachine.RunStrategy.MANUAL,
    VirtualMachine.RunStrategy.ALWAYS,
    VirtualMachine.RunStrategy.HALTED,
    VirtualMachine.RunStrategy.RERUNONFAILURE,
]

aaq_allocation_methods_matrix = [AAQ_VIRTUAL_RESOURCES, AAQ_VMI_POD_USAGE]

sysprep_source_matrix = ["ConfigMap", "Secret"]

# If the DataImportCron uses a different prefix than the DataSource name
# use data_import_cron_prefix in matrix dict to specify new prefix.
auto_update_data_source_matrix = [
    {"centos-stream9": {"template_os": "centos-stream9"}},
    {"fedora": {"template_os": "fedora"}},
    {"rhel8": {"template_os": "rhel8.4"}},
    {"rhel9": {"template_os": "rhel9.0"}},
]

data_import_cron_matrix = [
    {"centos-stream9": {"instance_type": "u1.medium", "preference": "centos.stream9"}},
    {"centos-stream10": {"instance_type": "u1.medium", "preference": "centos.stream10"}},
    {"fedora": {"instance_type": "u1.medium", "preference": "fedora"}},
    {"rhel8": {"instance_type": "u1.medium", "preference": "rhel.8"}},
    {"rhel9": {"instance_type": "u1.medium", "preference": "rhel.9"}},
    {"rhel10": {"instance_type": "u1.medium", "preference": "rhel.10"}},
]

ip_stack_version_matrix = [
    IPV4_STR,
    IPV6_STR,
]
cnv_pod_priority_class_matrix = CNV_PODS_NO_HPP_CSI_HPP_POOL
cnv_pod_matrix = ALL_CNV_PODS
cnv_crd_matrix = ALL_CNV_CRDS
cnv_crypto_policy_matrix = [TLS_OLD_POLICY, TLS_CUSTOM_POLICY]

cnv_related_object_matrix = ALL_HCO_RELATED_OBJECTS
cnv_prometheus_rules_matrix = CNV_PROMETHEUS_RULES

cnv_deployment_matrix = ALL_CNV_DEPLOYMENTS
cnv_deployment_no_hpp_matrix = ALL_CNV_DEPLOYMENTS_NO_HPP_POOL
cnv_daemonset_matrix = ALL_CNV_DAEMONSETS
pod_resource_validation_matrix = [{"cpu": 5}, {"memory": None}]
cnv_operators_matrix = CNV_OPERATORS
cnv_vm_console_proxy_cluster_resource_matrix = VM_CONSOLE_PROXY_CLUSTER_RESOURCES
cnv_vm_console_proxy_namespace_resource_matrix = VM_CONSOLE_PROXY_NAMESPACE_RESOURCES

# VM migration storm test params
vm_deploys = 1  # How many vm of each type to deploy
linux_iterations = 250  # Number of migration iterations of linux VMs
windows_iterations = 500  # Number of migration iterations of windows VMs

# RHEL container disk image matrix
cnv_rhel_container_disk_images_matrix = [
    {"rhel8": {"RHEL_CONTAINER_DISK_IMAGE": getattr(Images.Rhel, "RHEL8_REGISTRY_GUEST_IMG", None)}},
    {"rhel9": {"RHEL_CONTAINER_DISK_IMAGE": getattr(Images.Rhel, "RHEL9_REGISTRY_GUEST_IMG", None)}},
    {"rhel10": {"RHEL_CONTAINER_DISK_IMAGE": getattr(Images.Rhel, "RHEL10_REGISTRY_GUEST_IMG", None)}},
]

# Tekton resource matrix
cnv_tekton_pipelines_resource_matrix = TEKTON_AVAILABLE_PIPELINEREF
cnv_tekton_tasks_resource_matrix = TEKTON_AVAILABLE_TASKS

# Pod matrix for chaos
cnv_pod_deletion_test_matrix = [
    {
        "virt-api": {
            "pod_prefix": "virt-api",
            "resource": Deployment,
            "namespace_name": hco_namespace,
            "ratio": 0.5,
            "interval": TIMEOUT_5SEC,
            "max_duration": TIMEOUT_5MIN,
        }
    },
    {
        "apiserver": {
            "pod_prefix": "apiserver",
            "resource": Deployment,
            "namespace_name": openshift_apiserver_namespace,
            "ratio": 0.5,
            "interval": TIMEOUT_5SEC,
            "max_duration": TIMEOUT_5MIN,
        }
    },
]
os_login_param: dict[str, Any] = {}
# Network configuration
vlans = [f"{_id}" for _id in range(1000, 1020)]

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str, int]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]
