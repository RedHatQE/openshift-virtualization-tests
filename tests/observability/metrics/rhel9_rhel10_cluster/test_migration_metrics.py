"""
Migration Metrics on a Dual-Stream (RHCOS 9 + RHCOS 10) Cluster

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/iuo.md

Markers:
    - mixed_os_nodes
    - rwx_default_storage

Preconditions:
    - Migration bandwidth limited for the under-test VM, so migration metrics are sampled while migration is in progress
"""

import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_VMI_MIGRATION_DATA_PROCESSED_BYTES,
    KUBEVIRT_VMI_MIGRATION_DATA_REMAINING_BYTES,
    KUBEVIRT_VMI_MIGRATION_DATA_TOTAL_BYTES,
    KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_MEMORY_TRANSFER_RATE_BYTES,
)
from tests.observability.metrics.utils import (
    timestamp_to_seconds,
    validate_metric_value_greater_than_initial_value,
)
from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, WINDOWS_LATEST, WINDOWS_LATEST_LABELS
from utilities.constants.cluster import RHCOS9_AFFINITY, RHCOS10_AFFINITY
from utilities.constants.timeouts import TIMEOUT_5MIN
from utilities.jira import is_jira_open
from utilities.monitoring import validate_metrics_value

pytestmark = [
    pytest.mark.mixed_os_nodes,
    pytest.mark.rwx_default_storage,
]

MIGRATION_METRICS = (
    KUBEVIRT_VMI_MIGRATION_DATA_PROCESSED_BYTES,
    KUBEVIRT_VMI_MIGRATION_DATA_REMAINING_BYTES,
    KUBEVIRT_VMI_MIGRATION_MEMORY_TRANSFER_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_DATA_TOTAL_BYTES,
)
# CNV-97013: these two metrics return no data during migration, regardless of pre/post-copy mode.
METRICS_WITH_CNV_97013_BUG = frozenset((
    KUBEVIRT_VMI_MIGRATION_MEMORY_TRANSFER_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES,
))


class TestDualStreamMigrationMetrics:
    @pytest.mark.polarion("CNV-16823")
    @pytest.mark.usefixtures("dual_stream_migration_metrics_policy")
    @pytest.mark.parametrize(
        "dual_stream_migration_metrics_vm, dual_stream_migration_metrics_vmim",
        [
            (
                {"vm_affinity": RHCOS9_AFFINITY},
                {"target_affinity": RHCOS10_AFFINITY},
            ),
        ],
        indirect=True,
    )
    def test_migration_metrics_reported_rhcos9_to_rhcos10(
        self,
        subtests,
        prometheus,
        dual_stream_migration_metrics_vm,
        dual_stream_migration_metrics_vmim,
    ):
        """
        Test that migration metrics are reported when a VM is live migrated from an RHCOS 9 worker node
        to an RHCOS 10 worker node.

        Preconditions:
            - Migratable VM running on an RHCOS 9 worker node

        Steps:
            1. Live migrate the VM to an RHCOS 10 worker node
            2. Query the migration data processed and bandwidth metrics for the under-test VM

        Expected:
            - Migration data processed metric value is greater than zero
            - Migration bandwidth metric value is greater than zero

        Note:
            Also checks the data remaining and dirty memory rate metrics. The bandwidth and dirty memory rate
            metrics are skipped while CNV-97013 is open (they return no data during migration). Migration
            duration is covered separately by TestDualStreamMigrationStartAndEndRhcos9ToRhcos10.
        """
        for metric in MIGRATION_METRICS:
            with subtests.test(msg=metric):
                if metric in METRICS_WITH_CNV_97013_BUG and is_jira_open(jira_id="CNV-97013"):
                    pytest.xfail(reason=f"CNV-97013: {metric} returns no data during migration")
                validate_metric_value_greater_than_initial_value(
                    prometheus=prometheus,
                    metric_name=metric.format(vm_name=dual_stream_migration_metrics_vm.name),
                    initial_value=0,
                )

        dual_stream_migration_metrics_vmim.wait_for_status(
            status=dual_stream_migration_metrics_vmim.Status.SUCCEEDED, timeout=TIMEOUT_5MIN
        )

    @pytest.mark.polarion("CNV-16824")
    @pytest.mark.usefixtures("dual_stream_migration_metrics_policy")
    @pytest.mark.parametrize(
        "dual_stream_migration_metrics_vm, dual_stream_migration_metrics_vmim",
        [
            (
                {"vm_affinity": RHCOS10_AFFINITY},
                {"target_affinity": RHCOS9_AFFINITY},
            ),
        ],
        indirect=True,
    )
    def test_migration_metrics_reported_rhcos10_to_rhcos9(
        self,
        subtests,
        prometheus,
        dual_stream_migration_metrics_vm,
        dual_stream_migration_metrics_vmim,
    ):
        """
        Test that migration metrics are reported when a VM is live migrated from an RHCOS 10 worker node
        to an RHCOS 9 worker node.

        Preconditions:
            - Migratable VM running on an RHCOS 10 worker node

        Steps:
            1. Live migrate the VM to an RHCOS 9 worker node
            2. Query the migration data processed and bandwidth metrics for the under-test VM

        Expected:
            - Migration data processed metric value is greater than zero
            - Migration bandwidth metric value is greater than zero

        Note:
            Also checks the data remaining and dirty memory rate metrics. The bandwidth and dirty memory rate
            metrics are skipped while CNV-97013 is open (they return no data during migration). Migration
            duration is covered separately by TestDualStreamMigrationStartAndEndRhcos10ToRhcos9.
        """
        for metric in MIGRATION_METRICS:
            with subtests.test(msg=metric):
                if metric in METRICS_WITH_CNV_97013_BUG and is_jira_open(jira_id="CNV-97013"):
                    pytest.xfail(reason=f"CNV-97013: {metric} returns no data during migration")
                validate_metric_value_greater_than_initial_value(
                    prometheus=prometheus,
                    metric_name=metric.format(vm_name=dual_stream_migration_metrics_vm.name),
                    initial_value=0,
                )

        dual_stream_migration_metrics_vmim.wait_for_status(
            status=dual_stream_migration_metrics_vmim.Status.SUCCEEDED, timeout=TIMEOUT_5MIN
        )


@pytest.mark.parametrize(
    "golden_image_data_source_for_dual_stream_scope_class, dual_stream_start_end_vm, dual_stream_start_end_migration",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {
                "vm_name": "start-end-rhcos9-to-rhcos10-rhel",
                "template_labels": RHEL_LATEST_LABELS,
                "vm_affinity": RHCOS9_AFFINITY,
            },
            {"target_affinity": RHCOS10_AFFINITY},
            id="RHEL-VM",
        ),
        pytest.param(
            {"os_dict": WINDOWS_LATEST},
            {
                "vm_name": "start-end-rhcos9-to-rhcos10-windows",
                "template_labels": WINDOWS_LATEST_LABELS,
                "vm_affinity": RHCOS9_AFFINITY,
            },
            {"target_affinity": RHCOS10_AFFINITY},
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm, pytest.mark.windows],
            id="WIN-VM",
        ),
    ],
    indirect=True,
)
class TestDualStreamMigrationStartAndEndRhcos9ToRhcos10:
    """
    Tests for migration start/end time metrics reported when a VM is live migrated from an RHCOS 9 worker
    node to an RHCOS 10 worker node.

    STP:
    https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/iuo.md

    Preconditions:
        - Migratable VM running on an RHCOS 9 worker node, migrated to an RHCOS 10 worker node
    """

    @pytest.mark.polarion("CNV-16831")
    def test_metric_kubevirt_vmi_migration_start_time_seconds(self, prometheus, dual_stream_start_end_migration):
        """
        Test that the migration start time metric is reported when a VM is live migrated from an RHCOS 9
        worker node to an RHCOS 10 worker node.

        Steps:
            1. Query the migration start time metric for the under-test VM

        Expected:
            - Migration start time metric value matches the VM's recorded migration start timestamp
        """
        migration_state = dual_stream_start_end_migration.vmi.instance.status.migrationState
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vmi_migration_start_time_seconds{{name='{dual_stream_start_end_migration.name}'}}",
            expected_value=str(timestamp_to_seconds(timestamp=migration_state.startTimestamp)),
        )

    @pytest.mark.polarion("CNV-16832")
    def test_metric_kubevirt_vmi_migration_end_time_seconds(self, prometheus, dual_stream_start_end_migration):
        """
        Test that the migration end time metric is reported when a VM is live migrated from an RHCOS 9
        worker node to an RHCOS 10 worker node.

        Steps:
            1. Query the migration end time metric for the under-test VM

        Expected:
            - Migration end time metric value matches the VM's recorded migration end timestamp
        """
        migration_state = dual_stream_start_end_migration.vmi.instance.status.migrationState
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vmi_migration_end_time_seconds{{name='{dual_stream_start_end_migration.name}'}}",
            expected_value=str(timestamp_to_seconds(timestamp=migration_state.endTimestamp)),
        )


@pytest.mark.parametrize(
    "golden_image_data_source_for_dual_stream_scope_class, dual_stream_start_end_vm, dual_stream_start_end_migration",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {
                "vm_name": "start-end-rhcos10-to-rhcos9-rhel",
                "template_labels": RHEL_LATEST_LABELS,
                "vm_affinity": RHCOS10_AFFINITY,
            },
            {"target_affinity": RHCOS9_AFFINITY},
            id="RHEL-VM",
        ),
        pytest.param(
            {"os_dict": WINDOWS_LATEST},
            {
                "vm_name": "start-end-rhcos10-to-rhcos9-windows",
                "template_labels": WINDOWS_LATEST_LABELS,
                "vm_affinity": RHCOS10_AFFINITY,
            },
            {"target_affinity": RHCOS9_AFFINITY},
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm, pytest.mark.windows],
            id="WIN-VM",
        ),
    ],
    indirect=True,
)
class TestDualStreamMigrationStartAndEndRhcos10ToRhcos9:
    """
    Tests for migration start/end time metrics reported when a VM is live migrated from an RHCOS 10 worker
    node to an RHCOS 9 worker node.

    STP:
    https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/iuo.md

    Preconditions:
        - Migratable VM running on an RHCOS 10 worker node, migrated to an RHCOS 9 worker node
    """

    @pytest.mark.polarion("CNV-16833")
    def test_metric_kubevirt_vmi_migration_start_time_seconds(self, prometheus, dual_stream_start_end_migration):
        """
        Test that the migration start time metric is reported when a VM is live migrated from an RHCOS 10
        worker node to an RHCOS 9 worker node.

        Steps:
            1. Query the migration start time metric for the under-test VM

        Expected:
            - Migration start time metric value matches the VM's recorded migration start timestamp
        """
        migration_state = dual_stream_start_end_migration.vmi.instance.status.migrationState
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vmi_migration_start_time_seconds{{name='{dual_stream_start_end_migration.name}'}}",
            expected_value=str(timestamp_to_seconds(timestamp=migration_state.startTimestamp)),
        )

    @pytest.mark.polarion("CNV-16834")
    def test_metric_kubevirt_vmi_migration_end_time_seconds(self, prometheus, dual_stream_start_end_migration):
        """
        Test that the migration end time metric is reported when a VM is live migrated from an RHCOS 10
        worker node to an RHCOS 9 worker node.

        Steps:
            1. Query the migration end time metric for the under-test VM

        Expected:
            - Migration end time metric value matches the VM's recorded migration end timestamp
        """
        migration_state = dual_stream_start_end_migration.vmi.instance.status.migrationState
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vmi_migration_end_time_seconds{{name='{dual_stream_start_end_migration.name}'}}",
            expected_value=str(timestamp_to_seconds(timestamp=migration_state.endTimestamp)),
        )
