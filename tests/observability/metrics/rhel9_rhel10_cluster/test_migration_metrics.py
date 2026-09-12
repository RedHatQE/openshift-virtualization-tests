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
    validate_metric_value_greater_than_initial_value,
)
from utilities.constants.cluster import RHCOS9_AFFINITY, RHCOS10_AFFINITY
from utilities.jira import is_jira_open

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
METRICS_WITH_CNV_97013_BUG = [
    KUBEVIRT_VMI_MIGRATION_MEMORY_TRANSFER_RATE_BYTES,
    KUBEVIRT_VMI_MIGRATION_DIRTY_MEMORY_RATE_BYTES,
]


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
            2. Query the migration duration, data processed, and bandwidth metrics for the under-test VM

        Expected:
            - Migration duration metric value is greater than zero
            - Migration data processed metric value is greater than zero
            - Migration bandwidth metric value is greater than zero

        Note:
            Also checks the data remaining and dirty memory rate metrics. The bandwidth and dirty memory rate
            metrics are skipped while CNV-97013 is open (they return no data during migration).
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
            2. Query the migration duration, data processed, and bandwidth metrics for the under-test VM

        Expected:
            - Migration duration metric value is greater than zero
            - Migration data processed metric value is greater than zero
            - Migration bandwidth metric value is greater than zero

        Note:
            Also checks the data remaining and dirty memory rate metrics. The bandwidth and dirty memory rate
            metrics are skipped while CNV-97013 is open (they return no data during migration).
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
