import logging

import pytest

from tests.virt.node.descheduler.utils import verify_at_least_one_vm_migrated, wait_for_overutilized_soft_taint

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.tier3,
    pytest.mark.descheduler,
    pytest.mark.post_upgrade,
    pytest.mark.usefixtures(
        "descheduler_kubevirt_relieve_and_migrate_profile",
    ),
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
    @pytest.mark.polarion("CNV-11960")
    def test_soft_taint_added_when_node_overloaded(
        self,
        node_to_run_stress,
        stressed_vms_on_one_node,
    ):
        wait_for_overutilized_soft_taint(node=node_to_run_stress, taint_expected=True)

    @pytest.mark.polarion("CNV-11961")
    def test_rebalancing_when_node_overloaded(
        self,
        node_to_run_stress,
        stressed_vms_on_one_node,
    ):
        verify_at_least_one_vm_migrated(vms=stressed_vms_on_one_node, node_before=node_to_run_stress)

    @pytest.mark.polarion("CNV-11962")
    def test_soft_taint_removed_when_node_not_overloaded(
        self,
        node_to_run_stress,
    ):
        wait_for_overutilized_soft_taint(node=node_to_run_stress, taint_expected=False)
