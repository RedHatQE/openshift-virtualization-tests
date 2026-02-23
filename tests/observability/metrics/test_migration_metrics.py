import logging
from datetime import UTC, datetime

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
    wait_for_non_empty_metrics_value,
)
from tests.observability.utils import validate_metrics_value

LOGGER = logging.getLogger(__name__)


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
                KUBEVIRT_VMI_MIGRATION_MEMORY_TRANSFER_RATE_BYTES,
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
    @pytest.mark.jira("CNV-76682", run=False)
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
            int(datetime.now(UTC).timestamp())
            - timestamp_to_seconds(
                timestamp=vm_for_migration_metrics_test.vmi.instance.status.migrationState.startTimestamp
            )
        ) // 60
        wait_for_non_empty_metrics_value(
            prometheus=prometheus,
            metric_name=f"last_over_time({query.format(vm_name=vm_for_migration_metrics_test.name)}"
            f"[{max(10, minutes_passed_since_migration_start)}m])",
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
