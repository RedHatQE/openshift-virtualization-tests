import logging
from datetime import datetime, timezone

import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_VMI_MIGRATION_DATA_PROCESSED_BYTES,
    KUBEVIRT_VMI_MIGRATION_DATA_REMAINING_BYTES,
    KUBEVIRT_VMI_MIGRATION_DATA_TOTAL_BYTES,
    KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_DISK_TRANSFER_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATIONS_IN_RUNNING_PHASE,
    KUBEVIRT_VMI_MIGRATIONS_IN_SCHEDULING_PHASE,
)
from tests.observability.metrics.utils import (
    timestamp_to_seconds,
    wait_for_expected_metric_value_sum,
    wait_for_non_empty_metrics_value,
)
from tests.observability.utils import validate_metrics_value

LOGGER = logging.getLogger(__name__)


class TestMigrationMetrics:
    @pytest.mark.polarion("CNV-8480")
    @pytest.mark.s390x
    def test_migration_metrics_scheduling(
        self,
        admin_client,
        namespace,
        prometheus,
        initial_migration_metrics_values,
        vm_with_node_selector,
        vm_with_node_selector_vmim,
    ):
        wait_for_expected_metric_value_sum(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_MIGRATIONS_IN_SCHEDULING_PHASE,
            expected_value=initial_migration_metrics_values[KUBEVIRT_VMI_MIGRATIONS_IN_SCHEDULING_PHASE] + 1,
            check_times=1,
        )

    @pytest.mark.polarion("CNV-8481")
    @pytest.mark.s390x
    def test_migration_metrics_running(
        self,
        prometheus,
        initial_migration_metrics_values,
        migration_policy_with_bandwidth,
        vm_for_migration_metrics_test,
        vm_migration_metrics_vmim,
    ):
        wait_for_expected_metric_value_sum(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_MIGRATIONS_IN_RUNNING_PHASE,
            expected_value=initial_migration_metrics_values[KUBEVIRT_VMI_MIGRATIONS_IN_RUNNING_PHASE] + 1,
            check_times=1,
        )


class TestKubevirtVmiMigrationMetrics:
    @pytest.mark.parametrize(
        "query",
        [
            pytest.param(KUBEVIRT_VMI_MIGRATION_DATA_PROCESSED_BYTES, marks=(pytest.mark.polarion("CNV-11417"))),
            pytest.param(
                KUBEVIRT_VMI_MIGRATION_DATA_REMAINING_BYTES,
                marks=(pytest.mark.polarion("CNV-11600")),
            ),
            pytest.param(
                KUBEVIRT_VMI_MIGRATION_DISK_TRANSFER_RATE_BYTES,
                marks=(pytest.mark.polarion("CNV-11598")),
            ),
            pytest.param(
                KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES,
                marks=(pytest.mark.polarion("CNV-11599")),
            ),
            pytest.param(
                KUBEVIRT_VMI_MIGRATION_DATA_TOTAL_BYTES,
                marks=(pytest.mark.polarion("CNV-11802")),
            ),
        ],
    )
    @pytest.mark.jira("CNV-57777", run=False)
    @pytest.mark.s390x
    def test_kubevirt_vmi_migration_metrics(
        self,
        prometheus,
        namespace,
        admin_client,
        migration_policy_with_bandwidth_scope_class,
        vm_for_migration_metrics_test,
        vm_migration_metrics_vmim_scope_class,
        query,
    ):
        minutes_passed_since_migration_start = (
            int(datetime.now(timezone.utc).timestamp())
            - timestamp_to_seconds(
                timestamp=vm_for_migration_metrics_test.vmi.instance.status.migrationState.startTimestamp
            )
        ) // 60
        wait_for_non_empty_metrics_value(
            prometheus=prometheus,
            metric_name=f"last_over_time({query.format(vm_name=vm_for_migration_metrics_test.name)}"
            f"[{minutes_passed_since_migration_start if minutes_passed_since_migration_start > 10 else 10}m])",
        )


class TestKubevirtVmiMigrationStartAndEnd:
    @pytest.mark.polarion("CNV-11809")
    @pytest.mark.s390x
    def test_metric_kubevirt_vmi_migration_start_time_seconds(
        self,
        prometheus,
        vm_for_migration_metrics_test,
        vm_migration_metrics_vmim_scope_class,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vmi_migration_start_time_seconds{{name='{vm_for_migration_metrics_test.name}'}}",
            expected_value=str(
                timestamp_to_seconds(
                    timestamp=vm_for_migration_metrics_test.vmi.instance.status.migrationState.startTimestamp
                ),
            ),
        )

    @pytest.mark.polarion("CNV-11810")
    @pytest.mark.s390x
    def test_metric_kubevirt_vmi_migration_end_time_seconds(
        self,
        prometheus,
        vm_for_migration_metrics_test,
        vm_migration_metrics_vmim_scope_class,
        migration_succeeded_scope_class,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=f"kubevirt_vmi_migration_end_time_seconds{{name='{vm_for_migration_metrics_test.name}'}}",
            expected_value=str(
                timestamp_to_seconds(
                    timestamp=vm_for_migration_metrics_test.vmi.instance.status.migrationState.endTimestamp
                )
            ),
        )
