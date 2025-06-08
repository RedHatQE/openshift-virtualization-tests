import logging

import bitmath
import pytest
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import py_config

from tests.observability.metrics.constants import (
    KUBEVIRT_CONSOLE_ACTIVE_CONNECTIONS_BY_VMI,
    KUBEVIRT_VM_ERROR_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
    KUBEVIRT_VM_MIGRATING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
    KUBEVIRT_VM_NON_RUNNING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
    KUBEVIRT_VM_RUNNING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
    KUBEVIRT_VM_STARTING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
    KUBEVIRT_VMI_MEMORY_AVAILABLE_BYTES,
    KUBEVIRT_VMSNAPSHOT_PERSISTENTVOLUMECLAIM_LABELS,
    KUBEVIRT_VNC_ACTIVE_CONNECTIONS_BY_VMI,
)
from tests.observability.metrics.utils import (
    check_vm_last_transition_metric_value,
    check_vmi_count_metric,
    compare_metric_file_system_values_with_vm_file_system_values,
    expected_metric_labels_and_values,
    get_metric_labels_non_empty_value,
    timestamp_to_seconds,
    validate_metric_value_within_range,
    validate_vnic_info,
)
from tests.observability.utils import validate_metrics_value
from tests.os_params import FEDORA_LATEST_LABELS, RHEL_LATEST
from utilities.constants import (
    CAPACITY,
    LIVE_MIGRATE,
    USED,
)

LOGGER = logging.getLogger(__name__)


class TestVMICountMetric:
    @pytest.mark.polarion("CNV-3048")
    def test_vmi_count_metric_increase(
        self,
        prometheus,
        number_of_running_vmis,
        vm_metric_1,
        vm_metric_2,
    ):
        check_vmi_count_metric(expected_vmi_count=number_of_running_vmis + 2, prometheus=prometheus)

    @pytest.mark.polarion("CNV-3589")
    def test_vmi_count_metric_decrease(
        self,
        prometheus,
        number_of_running_vmis,
        vm_metric_1,
        vm_metric_2,
    ):
        vm_metric_2.stop(wait=True)
        check_vmi_count_metric(expected_vmi_count=number_of_running_vmis + 1, prometheus=prometheus)


class TestVMStatusLastTransitionMetricsLinux:
    @pytest.mark.polarion("CNV-9661")
    def test_vm_running_status_metrics(self, prometheus, vm_metric_1):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric=KUBEVIRT_VM_RUNNING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
            vm=vm_metric_1,
        )

    @pytest.mark.polarion("CNV-9662")
    def test_vm_error_status_metrics(self, prometheus, vm_in_error_state):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric=KUBEVIRT_VM_ERROR_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
            vm=vm_in_error_state,
        )

    @pytest.mark.polarion("CNV-9665")
    def test_vm_migrating_status_metrics(
        self, skip_if_no_common_cpu, prometheus, vm_metric_1, migration_policy_with_bandwidth, vm_metric_1_vmim
    ):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric=KUBEVIRT_VM_MIGRATING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
            vm=vm_metric_1,
        )

    @pytest.mark.polarion("CNV-9664")
    def test_vm_non_running_status_metrics(self, prometheus, vm_metric_1, stopped_vm_metric_1):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric=KUBEVIRT_VM_NON_RUNNING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
            vm=vm_metric_1,
        )

    @pytest.mark.polarion("CNV-9751")
    def test_vm_starting_status_metrics(self, prometheus, vm_in_starting_state):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric=KUBEVIRT_VM_STARTING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
            vm=vm_in_starting_state,
        )


@pytest.mark.tier3
class TestVMStatusLastTransitionMetricsWindows:
    @pytest.mark.polarion("CNV-11978")
    def test_vm_running_status_metrics_windows(self, prometheus, windows_vm_for_test):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric=KUBEVIRT_VM_RUNNING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
            vm=windows_vm_for_test,
        )

    @pytest.mark.polarion("CNV-11979")
    def test_vm_error_status_metrics_windows(self, prometheus, windows_vm_for_test_in_error_state):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric=KUBEVIRT_VM_ERROR_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
            vm=windows_vm_for_test_in_error_state,
        )

    @pytest.mark.polarion("CNV-11980")
    def test_vm_migrating_status_metrics_windows(
        self, skip_if_no_common_cpu, prometheus, windows_vm_for_test, windows_vm_vmim
    ):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric=KUBEVIRT_VM_MIGRATING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
            vm=windows_vm_for_test,
        )

    @pytest.mark.polarion("CNV-11981")
    def test_vm_non_running_status_metrics_windows(self, prometheus, windows_vm_for_test):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric=KUBEVIRT_VM_NON_RUNNING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS,
            vm=windows_vm_for_test,
        )

    @pytest.mark.polarion("CNV-11982")
    def test_vm_starting_status_metrics_windows(self, prometheus, windows_vm_for_test):
        check_vm_last_transition_metric_value(
            prometheus=prometheus,
            metric=f"max_over_time({KUBEVIRT_VM_STARTING_STATUS_LAST_TRANSITION_TIMESTAMP_SECONDS}[10m])",
            vm=windows_vm_for_test,
        )


@pytest.mark.parametrize(
    "vm_for_test",
    [pytest.param("console-vm-test")],
    indirect=True,
)
@pytest.mark.usefixtures("vm_for_test")
class TestVmConsolesAndVmCreateDateTimestampMetrics:
    @pytest.mark.polarion("CNV-11024")
    def test_kubevirt_console_active_connections(self, prometheus, vm_for_test, connected_vm_console_successfully):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_CONSOLE_ACTIVE_CONNECTIONS_BY_VMI.format(vm_name=vm_for_test.name),
            expected_value="1",
        )

    @pytest.mark.polarion("CNV-10842")
    def test_kubevirt_vnc_active_connections(self, prometheus, vm_for_test, connected_vnc_console):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VNC_ACTIVE_CONNECTIONS_BY_VMI.format(vm_name=vm_for_test.name),
            expected_value="1",
        )

    @pytest.mark.polarion("CNV-11805")
    def test_metric_kubevirt_vm_create_date_timestamp_seconds(self, prometheus, vm_for_test):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_create_date_timestamp_seconds{{name='{vm_for_test.name}'}}",
            expected_value=str(timestamp_to_seconds(timestamp=vm_for_test.instance.metadata.creationTimestamp)),
        )


class TestVmiMemoryCachedBytes:
    @pytest.mark.parametrize(
        "vm_for_test",
        [pytest.param("test-vm-memory-cached", marks=pytest.mark.polarion("CNV-11031"))],
        indirect=True,
    )
    def test_kubevirt_vmi_memory_cached_bytes(
        self,
        prometheus,
        vm_for_test,
        memory_cached_sum_from_vm_console,
    ):
        validate_metric_value_within_range(
            prometheus=prometheus,
            expected_value=memory_cached_sum_from_vm_console,
            metric_name=f"kubevirt_vmi_memory_cached_bytes{{name='{vm_for_test.name}'}}",
        )


@pytest.mark.parametrize("vm_for_test", [pytest.param("file-system-metrics")], indirect=True)
class TestVmiFileSystemMetrics:
    @pytest.mark.parametrize(
        "file_system_metric_mountpoints_existence, capacity_or_used",
        [
            pytest.param(
                CAPACITY,
                CAPACITY,
                marks=pytest.mark.polarion("CNV-11406"),
                id="test_metric_kubevirt_vmi_filesystem_capacity_bytes",
            ),
            pytest.param(
                USED,
                USED,
                marks=pytest.mark.polarion("CNV-11407"),
                id="test_metric_kubevirt_vmi_filesystem_used_bytes",
            ),
        ],
        indirect=["file_system_metric_mountpoints_existence"],
    )
    def test_metric_kubevirt_vmi_filesystem_capacity_used_bytes(
        self, prometheus, vm_for_test, file_system_metric_mountpoints_existence, dfs_info, capacity_or_used
    ):
        compare_metric_file_system_values_with_vm_file_system_values(
            prometheus=prometheus,
            vm_for_test=vm_for_test,
            mount_point=list(dfs_info.keys())[0],
            capacity_or_used=capacity_or_used,
        )


class TestVmiMemoryAvailableBytes:
    @pytest.mark.parametrize(
        "vm_for_test",
        [pytest.param("available-mem-test", marks=pytest.mark.polarion("CNV-11497"))],
        indirect=True,
    )
    def test_kubevirt_vmi_memory_available_bytes(self, prometheus, vm_for_test, vmi_memory_available_memory):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_MEMORY_AVAILABLE_BYTES.format(vm_name=vm_for_test.name),
            expected_value=vmi_memory_available_memory,
        )


@pytest.mark.usefixtures("vm_with_cpu_spec")
class TestVmResourceRequests:
    @pytest.mark.polarion("CNV-11521")
    def test_metric_kubevirt_vm_resource_requests(
        self,
        prometheus,
        cnv_vm_resource_requests_units_matrix__function__,
        vm_with_cpu_spec,
        modified_vm_cpu_requests,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_resource_requests{{'name'='{vm_with_cpu_spec.name}',"
            f"'unit'='{cnv_vm_resource_requests_units_matrix__function__}'}}",
            expected_value=str(modified_vm_cpu_requests[cnv_vm_resource_requests_units_matrix__function__]),
        )


class TestVmiStatusAddresses:
    @pytest.mark.parametrize(
        "vm_for_test", [pytest.param("vmi-status-addresses", marks=pytest.mark.polarion("CNV-11534"))], indirect=True
    )
    def test_metric_kubevirt_vmi_status_addresses(
        self,
        prometheus,
        vm_for_test,
        metric_validate_metric_labels_values_ip_labels,
        vm_virt_controller_ip_address,
        vm_ip_address,
    ):
        instance_value = metric_validate_metric_labels_values_ip_labels.get("instance").split(":")[0]
        address_value = metric_validate_metric_labels_values_ip_labels.get("address")
        assert instance_value == vm_virt_controller_ip_address, (
            f"Expected value: {vm_virt_controller_ip_address}, Actual: {instance_value}"
        )
        assert address_value == vm_ip_address, f"Expected value: {vm_ip_address}, Actual: {address_value}"


class TestVmSnapshotSucceededTimeStamp:
    @pytest.mark.parametrize(
        "vm_for_test", [pytest.param("vm-snapshot-test", marks=pytest.mark.polarion("CNV-11536"))], indirect=True
    )
    def test_metric_kubevirt_vmsnapshot_succeeded_timestamp_seconds(
        self, prometheus, vm_for_test, vm_for_test_snapshot
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vmsnapshot_succeeded_timestamp_seconds{{name='{vm_for_test.name}'}}",
            expected_value=str(timestamp_to_seconds(timestamp=vm_for_test_snapshot.instance.status.creationTime)),
        )


class TestVmResourceLimits:
    @pytest.mark.polarion("CNV-11601")
    def test_metric_kubevirt_vm_resource_limits(
        self, prometheus, cnv_vm_resources_limits_matrix__function__, vm_for_test_with_resource_limits
    ):
        vm_for_test_with_resource_limits_instance = (
            vm_for_test_with_resource_limits.instance.spec.template.spec.domain.resources.limits
        )
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_resource_limits{{name='{vm_for_test_with_resource_limits.name}', "
            f"resource='{cnv_vm_resources_limits_matrix__function__}'}}",
            expected_value=vm_for_test_with_resource_limits_instance.cpu
            if cnv_vm_resources_limits_matrix__function__ == "cpu"
            else str(int(bitmath.parse_string_unsafe(vm_for_test_with_resource_limits_instance.memory).bytes)),
        )


@pytest.mark.parametrize("vm_for_test", [pytest.param("memory-working-set-vm")], indirect=True)
class TestVmFreeMemoryBytes:
    @pytest.mark.polarion("CNV-11692")
    def test_metric_kubevirt_vm_container_free_memory_bytes_based_on_working_set_bytes(
        self, prometheus, vm_for_test, vm_virt_launcher_pod_requested_memory, vm_memory_working_set_bytes
    ):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_container_free_memory_bytes_based_on_working_set_bytes"
            f"{{pod='{vm_for_test.vmi.virt_launcher_pod.name}'}}",
            expected_value=vm_virt_launcher_pod_requested_memory - vm_memory_working_set_bytes,
        )

    @pytest.mark.polarion("CNV-11693")
    def test_metric_kubevirt_vm_container_free_memory_bytes_based_on_rss(
        self, prometheus, vm_for_test, vm_virt_launcher_pod_requested_memory, vm_memory_rss_bytes
    ):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_container_free_memory_bytes_based_on_rss"
            f"{{pod='{vm_for_test.privileged_vmi.virt_launcher_pod.name}'}}",
            expected_value=vm_virt_launcher_pod_requested_memory - vm_memory_rss_bytes,
        )


class TestKubevirtVmiNonEvictable:
    @pytest.mark.parametrize(
        "data_volume_scope_function, vm_from_template_with_existing_dv",
        [
            pytest.param(
                {
                    "dv_name": "non-evictable-dv",
                    "image": RHEL_LATEST["image_path"],
                    "storage_class": py_config["default_storage_class"],
                    "dv_size": RHEL_LATEST["dv_size"],
                    "access_modes": DataVolume.AccessMode.RWO,
                },
                {
                    "vm_name": "non-evictable-vm",
                    "template_labels": FEDORA_LATEST_LABELS,
                    "ssh": False,
                    "guest_agent": False,
                    "eviction_strategy": LIVE_MIGRATE,
                },
                marks=pytest.mark.polarion("CNV-7484"),
            ),
        ],
        indirect=True,
    )
    def test_kubevirt_vmi_non_evictable(
        self,
        prometheus,
        data_volume_scope_function,
        vm_from_template_with_existing_dv,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_vmi_non_evictable",
            expected_value="1",
        )


class TestVmSnapshotPersistentVolumeClaimLabels:
    @pytest.mark.polarion("CNV-11762")
    def test_metric_kubevirt_vmsnapshot_persistentvolumeclaim_labels(
        self,
        prometheus,
        vm_for_snapshot_for_metrics_test,
        restored_vm_using_snapshot,
        snapshot_labels_for_testing,
    ):
        expected_metric_labels_and_values(
            expected_labels_and_values=snapshot_labels_for_testing,
            values_from_prometheus=get_metric_labels_non_empty_value(
                prometheus=prometheus,
                metric_name=KUBEVIRT_VMSNAPSHOT_PERSISTENTVOLUMECLAIM_LABELS.format(
                    vm_name=vm_for_snapshot_for_metrics_test.name
                ),
            ),
        )


class TestVmDiskAllocatedSize:
    @pytest.mark.polarion("CNV-11817")
    def test_metric_kubevirt_vm_disk_allocated_size_bytes(
        self, prometheus, vm_for_vm_disk_allocation_size_test, pvc_size_bytes
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vm_disk_allocated_size_bytes{{name='{vm_for_vm_disk_allocation_size_test.name}'}}",
            expected_value=pvc_size_bytes,
        )


class TestVmVnicInfo:
    @pytest.mark.parametrize(
        "vnic_info_from_vm_or_vmi, query",
        [
            pytest.param(
                "vm",
                "kubevirt_vm_vnic_info{{name='{vm_name}'}}",
                marks=pytest.mark.polarion("CNV-11812"),
            ),
            pytest.param(
                "vmi",
                "kubevirt_vmi_vnic_info{{name='{vm_name}'}}",
                marks=pytest.mark.polarion("CNV-11811"),
            ),
        ],
        indirect=["vnic_info_from_vm_or_vmi"],
    )
    def test_metric_kubevirt_vm_vnic_info(self, prometheus, running_metric_vm, vnic_info_from_vm_or_vmi, query):
        validate_vnic_info(
            prometheus=prometheus,
            vnic_info_to_compare=vnic_info_from_vm_or_vmi,
            metric_name=query.format(vm_name=running_metric_vm.name),
        )
