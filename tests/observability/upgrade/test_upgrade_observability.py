import pytest

from tests.observability.upgrade.utils import wait_for_greater_than_zero_metric_value
from tests.observability.utils import validate_metrics_value
from tests.upgrade_params import IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID, IUO_UPGRADE_TEST_ORDERING_NODE_ID
from utilities.constants import DEPENDENCY_SCOPE_SESSION

KUBEVIRT_VMI_NUMBER_OF_OUTDATED = "kubevirt_vmi_number_of_outdated"


@pytest.mark.upgrade
@pytest.mark.usefixtures("running_vm_with_bridge")
class TestUpgradeObservability:
    """Pre-upgrade tests"""

    @pytest.mark.polarion("CNV-11749")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"test_metric_{KUBEVIRT_VMI_NUMBER_OF_OUTDATED}::before_upgrade")
    def test_metric_kubevirt_vmi_number_of_outdated_before_upgrade(self, prometheus, kubevirt_resource):
        assert kubevirt_resource.instance.status.outdatedVirtualMachineInstanceWorkloads == 0
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_NUMBER_OF_OUTDATED,
            expected_value="0",
        )

    """ Post-upgrade tests """

    @pytest.mark.polarion("CNV-11758")
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID, f"test_metric_{KUBEVIRT_VMI_NUMBER_OF_OUTDATED}::before_upgrade"],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_metric_kubevirt_vmi_number_of_outdated_after_upgrade(self, prometheus):
        wait_for_greater_than_zero_metric_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_NUMBER_OF_OUTDATED,
        )
