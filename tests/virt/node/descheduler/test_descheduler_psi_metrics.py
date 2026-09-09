import logging

import pytest

from tests.virt.node.descheduler.utils import (
    assert_psi_values_within_threshold,
    verify_at_least_one_vm_migrated,
    wait_for_overutilized_soft_taint,
)
from utilities.constants.timeouts import TIMEOUT_15MIN

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.tier3,
    pytest.mark.descheduler,
    pytest.mark.post_upgrade,
    pytest.mark.data_collector_scope(scope="module"),
]


@pytest.mark.parametrize(
    "calculated_vm_deployment_for_descheduler_test",
    [pytest.param(0.50)],
    indirect=True,
)
@pytest.mark.usefixtures(
    "deployed_vms_for_descheduler_test",
)
class TestDeschedulerLoadAwareRebalancing:
    """
    Tests for load-aware descheduler rebalancing driven by node utilization and pressure (PSI).

    Jira: https://redhat.atlassian.net/browse/CNV-80073

    Preconditions:
        - Descheduler operator installed and configured by autopilot
        - Multiple schedulable worker nodes available for migration
        - Set of running VMs spread across the cluster, sized to consume about half of the
          available memory per node
    """

    @pytest.mark.polarion("CNV-11960")
    def test_soft_taint_added_when_node_overloaded(
        self,
        node_to_run_stress,
        stressed_vms_on_one_node,
    ):
        """
        Test that the descheduler marks an overloaded node with the overutilized soft taint.

        Steps:
            1. Select the node running the most under-test VMs
            2. Generate CPU stress on all under-test VMs located on that node

        Expected:
            - The overutilized soft taint is added to the overloaded node
        """
        wait_for_overutilized_soft_taint(node=node_to_run_stress, taint_expected=True)

    @pytest.mark.polarion("CNV-11961")
    def test_rebalancing_when_node_overloaded(
        self,
        node_to_run_stress,
        stressed_vms_on_one_node,
    ):
        """
        Test that the descheduler rebalances VMs away from an overloaded node.

        Preconditions:
            - Under-test VMs on the selected node are under CPU stress

        Steps:
            1. Wait for the descheduler to act on the overloaded node

        Expected:
            - At least one under-test VM is migrated off the overloaded node
        """
        verify_at_least_one_vm_migrated(vms=stressed_vms_on_one_node, node_before=node_to_run_stress)

    @pytest.mark.polarion("CNV-11962")
    def test_soft_taint_removed_when_node_not_overloaded(
        self,
        node_to_run_stress,
        all_existing_migrations_completed,
    ):
        """
        Test that the descheduler clears the overutilized soft taint once a node is no longer overloaded.

        Preconditions:
            - The node was previously overloaded and rebalancing migrations have completed

        Steps:
            1. Wait for the node utilization and pressure to return below the overutilized threshold

        Expected:
            - The overutilized soft taint is removed from the node
        """
        wait_for_overutilized_soft_taint(node=node_to_run_stress, taint_expected=False, wait_timeout=TIMEOUT_15MIN)

    @pytest.mark.polarion("CNV-12346")
    def test_psi_values_within_threshold(
        self,
        workers_psi_metric_values,
    ):
        """
        Test that worker node PSI values stay within the descheduler deviation threshold.

        Steps:
            1. Query the combined utilization and pressure PSI metric for the worker nodes

        Expected:
            - No worker node PSI value exceeds the deviation threshold
        """
        assert_psi_values_within_threshold(psi_values_dict=workers_psi_metric_values)
