"""Monitoring and alerting constants.

Alert severity strings (CRITICAL_STR, WARNING_STR, INFO_STR), operator health
status metric names, and the full list of KubeVirt VMI metrics used in
monitoring tests.
"""

CRITICAL_STR = "critical"
INFO_STR = "info"
WARNING_STR = "warning"
NONE_STRING = "none"

KUBEVIRT_HYPERCONVERGED_OPERATOR_HEALTH_STATUS = "kubevirt_hyperconverged_operator_health_status"
KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS = "kubevirt_hco_hyperconverged_cr_exists"

OPERATOR_HEALTH_IMPACT_VALUES = {
    CRITICAL_STR: "2",
    WARNING_STR: "1",
    NONE_STRING: "0",
}

FIRING_STATE = "firing"
PENDING_STR = "pending"

KUBELET_READY_CONDITION = {"KubeletReady": "True"}

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
