import os
from typing import Any

from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.template import Template
from ocp_resources.virtual_machine import VirtualMachine

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
    DATA_SOURCE_NAME,
    FLAVOR_STR,
    HCO_CATALOG_SOURCE,
    INSTANCE_TYPE_STR,
    IPV4_STR,
    IPV6_STR,
    LINUX_BRIDGE,
    OVS_BRIDGE,
    PREFERENCE_STR,
    PRODUCTION_CATALOG_SOURCE,
    TEKTON_AVAILABLE_PIPELINEREF,
    TEKTON_AVAILABLE_TASKS,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TLS_CUSTOM_POLICY,
    TLS_OLD_POLICY,
    VM_CONSOLE_PROXY_CLUSTER_RESOURCES,
    VM_CONSOLE_PROXY_NAMESPACE_RESOURCES,
    WIN_2K22,
    WIN_2K25,
    WIN_10,
    WIN_11,
    Images,
    NamespacesNames,
    StorageClassNames,
)
from utilities.infra import get_latest_os_dict_list

global config


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


bridge_device_matrix = [LINUX_BRIDGE, OVS_BRIDGE]

# storage_class_matrix can be overwritten to include hostpath-csi-pvc-block and hostpath-csi-basic along with ocs,
# via command line argument. Example usage can be found in README.md.
storage_class_matrix = [
    {
        StorageClassNames.CEPH_RBD_VIRTUALIZATION: {
            "volume_mode": DataVolume.VolumeMode.BLOCK,
            "access_mode": DataVolume.AccessMode.RWX,
            "default": True,
        }
    },
]

default_storage_class, default_storage_class_configuration = _get_default_storage_class(sc_list=storage_class_matrix)
default_volume_mode = default_storage_class_configuration["volume_mode"]
default_access_mode = default_storage_class_configuration["access_mode"]

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

IMAGE_NAME_STR = "image_name"
IMAGE_PATH_STR = "image_path"
DV_SIZE_STR = "dv_size"
TEMPLATE_LABELS_STR = "template_labels"
OS_STR = "os"
WORKLOAD_STR = "workload"
LATEST_RELEASE_STR = "latest_released"
OS_VERSION_STR = "os_version"

rhel_os_matrix = [
    {
        "rhel-7-8": {
            OS_VERSION_STR: "7.8",
            IMAGE_NAME_STR: Images.Rhel.RHEL7_8_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_8_IMG),
            DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: "rhel7.8",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-7-9": {
            OS_VERSION_STR: "7.9",
            IMAGE_NAME_STR: Images.Rhel.RHEL7_9_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL7_9_IMG),
            DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: "rhel7.9",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-8-8": {
            OS_VERSION_STR: "8.8",
            IMAGE_NAME_STR: Images.Rhel.RHEL8_8_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_8_IMG),
            DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: "rhel8.8",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-8-10": {
            OS_VERSION_STR: "8.10",
            IMAGE_NAME_STR: Images.Rhel.RHEL8_10_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL8_10_IMG),
            DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: "rhel8.10",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-9-4": {
            OS_VERSION_STR: "9.4",
            IMAGE_NAME_STR: Images.Rhel.RHEL9_4_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL9_4_IMG),
            DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: "rhel9.4",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-9-5": {
            OS_VERSION_STR: "9.5",
            IMAGE_NAME_STR: Images.Rhel.RHEL9_5_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL9_5_IMG),
            DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
            LATEST_RELEASE_STR: True,
            TEMPLATE_LABELS_STR: {
                OS_STR: "rhel9.5",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.TINY,
            },
        }
    },
]

windows_os_matrix = [
    {
        "win-10": {
            OS_VERSION_STR: "10",
            IMAGE_NAME_STR: Images.Windows.WIN10_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Windows.UEFI_WIN_DIR, Images.Windows.WIN10_IMG),
            DV_SIZE_STR: Images.Windows.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: WIN_10,
                WORKLOAD_STR: Template.Workload.DESKTOP,
                FLAVOR_STR: Template.Flavor.MEDIUM,
            },
        }
    },
    {
        "win-2016": {
            OS_VERSION_STR: "2016",
            IMAGE_NAME_STR: Images.Windows.WIN2k16_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Windows.UEFI_WIN_DIR, Images.Windows.WIN2k16_IMG),
            DV_SIZE_STR: Images.Windows.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: "win2k16",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.MEDIUM,
            },
        }
    },
    {
        "win-2019": {
            OS_VERSION_STR: "2019",
            IMAGE_NAME_STR: Images.Windows.WIN2k19_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Windows.UEFI_WIN_DIR, Images.Windows.WIN2k19_IMG),
            DV_SIZE_STR: Images.Windows.DEFAULT_DV_SIZE,
            LATEST_RELEASE_STR: True,
            TEMPLATE_LABELS_STR: {
                OS_STR: "win2k19",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.MEDIUM,
            },
        }
    },
    {
        "win-11": {
            OS_VERSION_STR: "11",
            IMAGE_NAME_STR: Images.Windows.WIN11_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Windows.DIR, Images.Windows.WIN11_IMG),
            DV_SIZE_STR: Images.Windows.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: WIN_11,
                WORKLOAD_STR: Template.Workload.DESKTOP,
                FLAVOR_STR: Template.Flavor.MEDIUM,
            },
        }
    },
    {
        "win-2022": {
            OS_VERSION_STR: "2022",
            IMAGE_NAME_STR: Images.Windows.WIN2022_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Windows.DIR, Images.Windows.WIN2022_IMG),
            DV_SIZE_STR: Images.Windows.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: WIN_2K22,
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.MEDIUM,
            },
        }
    },
    {
        "win-2025": {
            OS_VERSION_STR: "2025",
            IMAGE_NAME_STR: Images.Windows.WIN2k25_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Windows.UEFI_WIN_DIR, Images.Windows.WIN2k25_IMG),
            DV_SIZE_STR: Images.Windows.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: WIN_2K25,
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.MEDIUM,
            },
        }
    },
]

fedora_os_matrix = [
    {
        "fedora-41": {
            IMAGE_NAME_STR: Images.Fedora.FEDORA41_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Fedora.DIR, Images.Fedora.FEDORA41_IMG),
            DV_SIZE_STR: Images.Fedora.DEFAULT_DV_SIZE,
            LATEST_RELEASE_STR: True,
            TEMPLATE_LABELS_STR: {
                OS_STR: "fedora41",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.SMALL,
            },
        }
    },
]

centos_os_matrix = [
    {
        "centos-stream-9": {
            IMAGE_NAME_STR: Images.CentOS.CENTOS_STREAM_9_IMG,
            IMAGE_PATH_STR: os.path.join(Images.CentOS.DIR, Images.CentOS.CENTOS_STREAM_9_IMG),
            DV_SIZE_STR: Images.CentOS.DEFAULT_DV_SIZE,
            LATEST_RELEASE_STR: True,
            TEMPLATE_LABELS_STR: {
                OS_STR: "centos-stream9",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.TINY,
            },
        }
    },
]

instance_type_rhel_os_matrix = [
    {
        "rhel-10": {
            OS_VERSION_STR: "10",
            DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
            INSTANCE_TYPE_STR: "u1.medium",
            PREFERENCE_STR: "rhel.10",
            DATA_SOURCE_NAME: "rhel10-beta",
            LATEST_RELEASE_STR: True,
        }
    },
]

(
    latest_rhel_os_dict,
    latest_windows_os_dict,
    latest_fedora_os_dict,
    latest_centos_os_dict,
) = get_latest_os_dict_list(os_list=[rhel_os_matrix, windows_os_matrix, fedora_os_matrix, centos_os_matrix])

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
    {"rhel8": {"RHEL_CONTAINER_DISK_IMAGE": Images.Rhel.RHEL8_REGISTRY_GUEST_IMG}},
    {"rhel9": {"RHEL_CONTAINER_DISK_IMAGE": Images.Rhel.RHEL9_REGISTRY_GUEST_IMG}},
    {"rhel10": {"RHEL_CONTAINER_DISK_IMAGE": Images.Rhel.RHEL10_REGISTRY_GUEST_IMG}},
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
