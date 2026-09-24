"""
Migration Metrics on a Dual-Stream (RHCOS 9 + RHCOS 10) Cluster

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/iuo.md

Markers:
    - mixed_os_nodes
    - rwx_default_storage

Preconditions:
    - Migration bandwidth limited for the under-test VM, so migration metrics are sampled while migration
      is in progress. The Windows VM uses a much higher bandwidth cap than RHEL (its guest memory is
      considerably larger), since a plain (unthrottled) migration completes too quickly for metrics to be
      sampled mid-flight.
"""

import logging

import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_VMI_MIGRATION_DATA_PROCESSED_BYTES,
    KUBEVIRT_VMI_MIGRATION_DATA_REMAINING_BYTES,
    KUBEVIRT_VMI_MIGRATION_DATA_TOTAL_BYTES,
    KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_END_TIME_SECONDS,
    KUBEVIRT_VMI_MIGRATION_MEMORY_TRANSFER_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_START_TIME_SECONDS,
)
from tests.observability.metrics.utils import (
    timestamp_to_seconds,
    validate_metric_value_greater_than_initial_value,
)
from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, WINDOWS_LATEST, WINDOWS_LATEST_LABELS
from utilities.constants.cluster import RHCOS9_AFFINITY, RHCOS10_AFFINITY
from utilities.constants.timeouts import TIMEOUT_5MIN
from utilities.constants.virt import MIGRATION_POLICY_VM_LABEL, MIGRATION_POLICY_WINDOWS_VM_LABEL
from utilities.jira import is_jira_open
from utilities.monitoring import validate_metrics_value

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.mixed_os_nodes,
    pytest.mark.rwx_default_storage,
]

MIGRATION_METRICS = [
    KUBEVIRT_VMI_MIGRATION_DATA_PROCESSED_BYTES,
    KUBEVIRT_VMI_MIGRATION_DATA_REMAINING_BYTES,
    KUBEVIRT_VMI_MIGRATION_MEMORY_TRANSFER_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_DATA_TOTAL_BYTES,
    KUBEVIRT_VMI_MIGRATION_START_TIME_SECONDS,
    KUBEVIRT_VMI_MIGRATION_END_TIME_SECONDS,
]

METRICS_WITH_CNV_97013_BUG = [
    KUBEVIRT_VMI_MIGRATION_MEMORY_TRANSFER_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES,
]

# Each migration policy's vmi_selector only matches VMs carrying its corresponding label.
_MIGRATION_POLICY_VM_DICT = {"spec": {"template": {"metadata": {"labels": MIGRATION_POLICY_VM_LABEL}}}}
_MIGRATION_POLICY_WINDOWS_VM_DICT = {"spec": {"template": {"metadata": {"labels": MIGRATION_POLICY_WINDOWS_VM_LABEL}}}}


@pytest.mark.usefixtures("dual_stream_migration_metrics_policy", "dual_stream_migration_metrics_windows_policy")
@pytest.mark.parametrize(
    "golden_image_data_source_for_dual_stream_scope_module, dual_stream_golden_image_vm, dual_stream_migration_metrics_vmim",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {
                "vm_name": "ds-9to10-rhel",
                "template_labels": RHEL_LATEST_LABELS,
                "vm_affinity": RHCOS9_AFFINITY,
                "vm_dict": _MIGRATION_POLICY_VM_DICT,
            },
            {"target_affinity": RHCOS10_AFFINITY},
            id="RHEL-VM",
        ),
        pytest.param(
            {"os_dict": WINDOWS_LATEST},
            {
                "vm_name": "ds-9to10-windows",
                "template_labels": WINDOWS_LATEST_LABELS,
                "vm_affinity": RHCOS9_AFFINITY,
                "vm_dict": _MIGRATION_POLICY_WINDOWS_VM_DICT,
            },
            {"target_affinity": RHCOS10_AFFINITY},
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm, pytest.mark.windows],
            id="WIN-VM",
        ),
    ],
    indirect=True,
)
class TestDualStreamMigrationRhcos9ToRhcos10:
    """
    Tests for migration metrics reported when a VM is live migrated from an RHCOS 9 worker node to an
    RHCOS 10 worker node.

    STP:
    https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/iuo.md

    Preconditions:
        - Migratable VM running on an RHCOS 9 worker node, migrated to an RHCOS 10 worker node
    """

    @pytest.mark.polarion("CNV-16823")
    def test_migration_metrics_reported(
        self,
        subtests,
        prometheus,
        dual_stream_golden_image_vm,
        dual_stream_migration_metrics_vmim,
    ):
        """
        Test that migration metrics are reported when a VM is live migrated from an RHCOS 9 worker node
        to an RHCOS 10 worker node.

        Steps:
        1. For each migration metric (data processed, data remaining, memory transfer rate, dirty
           memory rate, data total, start time, and end time):
           a. Query the metric value from Prometheus for the under-test VM
           b. For timestamp metrics, compare against the VM's recorded migration state timestamps
           c. For data metrics, validate they are greater than zero

        Expected:
        - Migration start time matches the VM's recorded start timestamp
        - Migration end time matches the VM's recorded end timestamp (after completion)
        - Data processed, data remaining, and data total metrics are non-zero
        - Memory transfer rate and dirty memory rate metrics xfail while CNV-97013 is open
          (they return no data during migration)

        Note:
            The memory transfer rate (bandwidth) and dirty memory rate metrics xfail while CNV-97013
            is open (they return no data during migration).
        """
        for metric in MIGRATION_METRICS:
            if metric in METRICS_WITH_CNV_97013_BUG and is_jira_open(jira_id="CNV-97013"):
                LOGGER.warning(f"CNV-97013: {metric} returns no data during migration")
                MIGRATION_METRICS.remove(metric)
            with subtests.test(msg=metric):
                if metric == KUBEVIRT_VMI_MIGRATION_START_TIME_SECONDS:
                    validate_metrics_value(
                        prometheus=prometheus,
                        metric_name=KUBEVIRT_VMI_MIGRATION_START_TIME_SECONDS.format(
                            vm_name=dual_stream_golden_image_vm.name
                        ),
                        expected_value=str(
                            timestamp_to_seconds(
                                timestamp=dual_stream_golden_image_vm.vmi.instance.status.migrationState.startTimestamp
                            )
                        ),
                    )
                elif metric == KUBEVIRT_VMI_MIGRATION_END_TIME_SECONDS:
                    dual_stream_migration_metrics_vmim.wait_for_status(
                        status=dual_stream_migration_metrics_vmim.Status.SUCCEEDED,
                        timeout=TIMEOUT_5MIN,
                    )
                    validate_metrics_value(
                        prometheus=prometheus,
                        metric_name=KUBEVIRT_VMI_MIGRATION_END_TIME_SECONDS.format(
                            vm_name=dual_stream_golden_image_vm.name
                        ),
                        expected_value=str(
                            timestamp_to_seconds(
                                timestamp=dual_stream_golden_image_vm.vmi.instance.status.migrationState.endTimestamp
                            )
                        ),
                    )
                else:
                    validate_metric_value_greater_than_initial_value(
                        prometheus=prometheus,
                        metric_name=metric.format(vm_name=dual_stream_golden_image_vm.name),
                        initial_value=0,
                    )


@pytest.mark.usefixtures("dual_stream_migration_metrics_policy", "dual_stream_migration_metrics_windows_policy")
@pytest.mark.parametrize(
    "golden_image_data_source_for_dual_stream_scope_module, dual_stream_golden_image_vm, dual_stream_migration_metrics_vmim",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {
                "vm_name": "ds-10to9-rhel",
                "template_labels": RHEL_LATEST_LABELS,
                "vm_affinity": RHCOS10_AFFINITY,
                "vm_dict": _MIGRATION_POLICY_VM_DICT,
            },
            {"target_affinity": RHCOS9_AFFINITY},
            id="RHEL-VM",
        ),
        pytest.param(
            {"os_dict": WINDOWS_LATEST},
            {
                "vm_name": "ds-10to9-windows",
                "template_labels": WINDOWS_LATEST_LABELS,
                "vm_affinity": RHCOS10_AFFINITY,
                "vm_dict": _MIGRATION_POLICY_WINDOWS_VM_DICT,
            },
            {"target_affinity": RHCOS9_AFFINITY},
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm, pytest.mark.windows],
            id="WIN-VM",
        ),
    ],
    indirect=True,
)
class TestDualStreamMigrationRhcos10ToRhcos9:
    """
    Tests for migration metrics reported when a VM is live migrated from an RHCOS 10 worker node to an
    RHCOS 9 worker node.

    STP:
    https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/iuo.md

    Preconditions:
        - Migratable VM running on an RHCOS 10 worker node, migrated to an RHCOS 9 worker node
    """

    @pytest.mark.polarion("CNV-16824")
    def test_migration_metrics_reported(
        self,
        subtests,
        prometheus,
        dual_stream_golden_image_vm,
        dual_stream_migration_metrics_vmim,
    ):
        """
        Test that migration metrics are reported when a VM is live migrated from an RHCOS 10 worker node
        to an RHCOS 9 worker node.

        Steps:
        1. For each migration metric (data processed, data remaining, memory transfer rate, dirty
           memory rate, data total, start time, and end time):
           a. Query the metric value from Prometheus for the under-test VM
           b. For timestamp metrics, compare against the VM's recorded migration state timestamps
           c. For data metrics, validate they are greater than zero

        Expected:
        - Migration start time matches the VM's recorded start timestamp
        - Migration end time matches the VM's recorded end timestamp (after completion)
        - Data processed, data remaining, and data total metrics are non-zero
        - Memory transfer rate and dirty memory rate metrics xfail while CNV-97013 is open
          (they return no data during migration)

        Note:
            Also checks the data remaining and dirty memory rate metrics. The bandwidth and dirty memory rate
            metrics are skipped while CNV-97013 is open (they return no data during migration).
        """
        for metric in MIGRATION_METRICS:
            if metric in METRICS_WITH_CNV_97013_BUG and is_jira_open(jira_id="CNV-97013"):
                LOGGER.warning(f"CNV-97013: {metric} returns no data during migration")
                MIGRATION_METRICS.remove(metric)
            with subtests.test(msg=metric):
                if metric == KUBEVIRT_VMI_MIGRATION_START_TIME_SECONDS:
                    validate_metrics_value(
                        prometheus=prometheus,
                        metric_name=KUBEVIRT_VMI_MIGRATION_START_TIME_SECONDS.format(
                            vm_name=dual_stream_golden_image_vm.name
                        ),
                        expected_value=str(
                            timestamp_to_seconds(
                                timestamp=dual_stream_golden_image_vm.vmi.instance.status.migrationState.startTimestamp
                            )
                        ),
                    )
                elif metric == KUBEVIRT_VMI_MIGRATION_END_TIME_SECONDS:
                    dual_stream_migration_metrics_vmim.wait_for_status(
                        status=dual_stream_migration_metrics_vmim.Status.SUCCEEDED,
                        timeout=TIMEOUT_5MIN,
                    )
                    validate_metrics_value(
                        prometheus=prometheus,
                        metric_name=KUBEVIRT_VMI_MIGRATION_END_TIME_SECONDS.format(
                            vm_name=dual_stream_golden_image_vm.name
                        ),
                        expected_value=str(
                            timestamp_to_seconds(
                                timestamp=dual_stream_golden_image_vm.vmi.instance.status.migrationState.endTimestamp
                            )
                        ),
                    )
                else:
                    validate_metric_value_greater_than_initial_value(
                        prometheus=prometheus,
                        metric_name=metric.format(vm_name=dual_stream_golden_image_vm.name),
                        initial_value=0,
                    )
