from ocp_resources.resource import Resource

from utilities.constants import (
    FLAVOR_STR,
    INSTANCE_TYPE_STR,
    NONE_STR,
    OS_STR,
    PREFERENCE_STR,
)

KUBEVIRT_SSP_TEMPLATE_VALIDATOR_REJECTED_INCREASE = "kubevirt_ssp_template_validator_rejected_increase"


KUBEVIRT_VMI_CPU_USER_USAGE_SECONDS_TOTAL_QUERY_STR = "kubevirt_vmi_cpu_user_usage_seconds_total{{name='{vm_name}'}}"
KUBEVIRT_VMI_CPU_SYSTEM_USAGE_SECONDS_TOTAL_QUERY_STR = (
    "kubevirt_vmi_cpu_system_usage_seconds_total{{name='{vm_name}'}}"
)
KUBEVIRT_VMI_CPU_USAGE_SECONDS_TOTAL_QUERY_STR = "kubevirt_vmi_cpu_usage_seconds_total{{name='{vm_name}'}}"
KUBEVIRT_VMI_VCPU_DELAY_SECONDS_TOTAL_QUERY_STR = "kubevirt_vmi_vcpu_delay_seconds_total{{name='{vm_name}'}}"

KUBEVIRT_CNAO_OPERATOR_UP = "kubevirt_cnao_operator_up"
KUBEVIRT_CNAO_CR_READY = "kubevirt_cnao_cr_ready"
KUBEVIRT_CNAO_KUBEMACPOOL_DUPLICATE_MACS = "kubevirt_cnao_kubemacpool_duplicate_macs"
KUBEVIRT_CNAO_CR_KUBEMACPOOL_DEPLOYED = "kubevirt_cnao_cr_kubemacpool_deployed"
KUBEVIRT_CNAO_KUBEMACPOOL_MANAGER_UP = "kubevirt_cnao_kubemacpool_manager_up"
KUBEVIRT_API_REQUEST_DEPRECATED_TOTAL_WITH_VERSION_VERB_AND_RESOURCE = (
    f"kubevirt_api_request_deprecated_total{{version='{Resource.ApiVersion.V1ALPHA3}',"
    f"resource='virtualmachines', verb='{'POST'}'}}"
)
CPU_USER = "cpu.user"
CPU_SYSTEM = "cpu.system"
CPU_TIME = "cpu.time"
VCPU_DELAY = "vcpu.0.delay"
VIRSH_STR = "virsh"
PROMETHEUS_STR = "prometheus"

OTHER_STR = "<other>"

INSTANCE_TYPE_LABELS = [INSTANCE_TYPE_STR, PREFERENCE_STR, FLAVOR_STR, OS_STR]

EXPECTED_NAMESPACE_INSTANCE_TYPE_LABELS = {
    INSTANCE_TYPE_STR: OTHER_STR,
    PREFERENCE_STR: OTHER_STR,
    FLAVOR_STR: NONE_STR,
    OS_STR: NONE_STR,
}
KUBEVIRT_VMI_PHASE_COUNT_STR = "kubevirt_vmi_phase_count"
KUBEVIRT_VMI_PHASE_COUNT = (
    f"{KUBEVIRT_VMI_PHASE_COUNT_STR}"
    "{{node='{node_name}', instance_type= '{instance_type}', preference='{preference}'}}"
)
KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES = "kubevirt_vmi_memory_swap_out_traffic_bytes"
KUBEVIRT_VMI_MEMORY_DOMAIN_BYTE = "kubevirt_vmi_memory_domain_bytes"
KUBEVIRT_VMI_VCPU_WAIT_SECONDS_TOTAL = "kubevirt_vmi_vcpu_wait_seconds_total"
KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES = "kubevirt_vmi_memory_swap_in_traffic_bytes"
CNV_VMI_STATUS_RUNNING_COUNT = "cnv:vmi_status_running:count"
METRIC_SUM_QUERY = "sum({metric_name}{{instance_type='{instance_type_name}', preference='{preference}'}})"
KUBEVIRT_CONSOLE_ACTIVE_CONNECTIONS_BY_VMI = "kubevirt_console_active_connections{{vmi='{vm_name}'}}"
KUBEVIRT_VNC_ACTIVE_CONNECTIONS_BY_VMI = "kubevirt_vnc_active_connections{{vmi='{vm_name}'}}"

GO_VERSION_STR = "goversion"
KUBE_VERSION_STR = "kubeversion"
KUBEVIRT_VM_CREATED_TOTAL_STR = "kubevirt_vm_created_total{{namespace='{namespace}'}}"
KUBEVIRT_VMI_FILESYSTEM_BYTES = (
    "kubevirt_vmi_filesystem_{capacity_or_used}_bytes{{kubernetes_vmi_label_kubevirt_io_domain='{vm_name}'}}"
)
KUBEVIRT_VMI_FILESYSTEM_BYTES_WITH_MOUNT_POINT = (
    "kubevirt_vmi_filesystem_{capacity_or_used}_bytes{{kubernetes_vmi_label_kubevirt_io_domain='{vm_name}', "
    "mount_point='{mountpoint}'}}"
)
KUBEVIRT_VMI_INFO = "kubevirt_vmi_info{{name='{vm_name}'}}"
KUBEVIRT_VMI_MEMORY_AVAILABLE_BYTES = (
    "kubevirt_vmi_memory_available_bytes{{kubernetes_vmi_label_kubevirt_io_domain='{vm_name}'}}"
)
KUBEVIRT_VMI_STATUS_ADDRESSES = "kubevirt_vmi_status_addresses{{name='{vm_name}'}}"
KUBEVIRT_VMI_MIGRATION_DATA_PROCESSED_BYTES = "kubevirt_vmi_migration_data_processed_bytes{{name='{vm_name}'}}"
KUBEVIRT_VMI_MIGRATION_DATA_REMAINING_BYTES = "kubevirt_vmi_migration_data_remaining_bytes{{name='{vm_name}'}}"
KUBEVIRT_VMI_MIGRATION_DISK_TRANSFER_RATE_BYTES = "kubevirt_vmi_migration_disk_transfer_rate_bytes{{name='{vm_name}'}}"
KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES = "kubevirt_vmi_migration_dirty_memory_rate_bytes{{name='{vm_name}'}}"
KUBEVIRT_VMSNAPSHOT_PERSISTENTVOLUMECLAIM_LABELS = (
    "kubevirt_vmsnapshot_persistentvolumeclaim_labels{{vm_name='{vm_name}'}}"
)
BINDING_NAME = "binding_name"
BINDING_TYPE = "binding_type"
