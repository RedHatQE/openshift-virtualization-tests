KUBEVIRT_SSP_TEMPLATE_VALIDATOR_REJECTED_INCREASE = "kubevirt_ssp_template_validator_rejected_increase"

KUBEVIRT_CONSOLE_ACTIVE_CONNECTIONS_BY_VMI = "kubevirt_console_active_connections{{vmi='{vm_name}'}}"
KUBEVIRT_VNC_ACTIVE_CONNECTIONS_BY_VMI = "kubevirt_vnc_active_connections{{vmi='{vm_name}'}}"

GO_VERSION_STR = "goversion"
KUBE_VERSION_STR = "kubeversion"
KUBEVIRT_VMI_FILESYSTEM_BYTES = (
    "kubevirt_vmi_filesystem_{capacity_or_used}_bytes{{kubernetes_vmi_label_kubevirt_io_domain='{vm_name}'}}"
)
KUBEVIRT_VMI_FILESYSTEM_BYTES_WITH_MOUNT_POINT = (
    "kubevirt_vmi_filesystem_{capacity_or_used}_bytes{{kubernetes_vmi_label_kubevirt_io_domain='{vm_name}', "
    "mount_point='{mountpoint}'}}"
)
KUBEVIRT_VMI_INFO = "kubevirt_vmi_info{{name='{vm_name}'}}"
KUBEVIRT_VM_INFO = "kubevirt_vm_info{{name='{vm_name}'}}"
KUBEVIRT_VMI_STATUS_ADDRESSES = "kubevirt_vmi_status_addresses{{name='{vm_name}'}}"
KUBEVIRT_VMI_MIGRATION_DATA_PROCESSED_BYTES = "kubevirt_vmi_migration_data_processed_bytes{{name='{vm_name}'}}"
KUBEVIRT_VMI_MIGRATION_DATA_REMAINING_BYTES = "kubevirt_vmi_migration_data_remaining_bytes{{name='{vm_name}'}}"
KUBEVIRT_VMI_MIGRATION_DISK_TRANSFER_RATE_BYTES = "kubevirt_vmi_migration_disk_transfer_rate_bytes{{name='{vm_name}'}}"
KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES = "kubevirt_vmi_migration_dirty_memory_rate_bytes{{name='{vm_name}'}}"
KUBEVIRT_VM_DISK_ALLOCATED_SIZE_BYTES = "kubevirt_vm_disk_allocated_size_bytes{{name='{vm_name}'}}"
KUBEVIRT_VMI_MIGRATIONS_IN_SCHEDULING_PHASE = "kubevirt_vmi_migrations_in_scheduling_phase"
KUBEVIRT_VMI_MIGRATIONS_IN_RUNNING_PHASE = "kubevirt_vmi_migrations_in_running_phase"
KUBEVIRT_VMI_MIGRATION_DATA_TOTAL_BYTES = "kubevirt_vmi_migration_data_total_bytes{{name='{vm_name}'}}"
KUBEVIRT_VMI_PHASE_TRANSITION_TIME_FROM_DELETION_SECONDS_SUM_SUCCEEDED = (
    "kubevirt_vmi_phase_transition_time_from_deletion_seconds_sum{phase='Succeeded'}"
)
BINDING_NAME = "binding_name"
BINDING_TYPE = "binding_type"
