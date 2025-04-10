import logging

import pytest

from tests.virt.node.descheduler.utils import verify_at_least_one_vm_migrated, wait_for_overutilized_soft_taint

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.tier3,
    pytest.mark.post_upgrade,
    pytest.mark.usefixtures(
        "skip_if_1tb_memory_or_more_node",
        "installed_descheduler_operator",
        "descheduler_kubevirt_releave_and_migrate_profile",
    ),
]


@pytest.mark.parametrize(
    "calculated_vm_deployment_for_node_with_least_available_memory",
    [pytest.param(0.80)],
    indirect=True,
)
@pytest.mark.usefixtures(
    "node_labeled_for_test",
    "deployed_vms_on_labeled_node",
    "stress_started_on_vms_for_psi_metrics",
)
class TestDeschedulerLoadAwareRebalancing:
    @pytest.mark.polarion("CNV-11960")
    def test_soft_taint_added_when_node_overloaded(
        self,
        node_labeled_for_test,
    ):
        wait_for_overutilized_soft_taint(node=node_labeled_for_test, taint_expected=True)

    @pytest.mark.polarion("CNV-11961")
    def test_rebalancing_when_node_overloaded(
        self,
        node_labeled_for_test,
        migration_policy_with_allow_auto_converge,
        deployed_vms_on_labeled_node,
        second_node_labeled_labeled_for_migration,
    ):
        verify_at_least_one_vm_migrated(vms=deployed_vms_on_labeled_node, node_before=node_labeled_for_test)

    @pytest.mark.polarion("CNV-11962")
    def test_soft_taint_removed_when_node_not_overloaded(
        self,
        node_labeled_for_test,
    ):
        wait_for_overutilized_soft_taint(node=node_labeled_for_test, taint_expected=False)
