import pytest

from tests.observability.constants import KUBEVIRT_VMI_NUMBER_OF_OUTDATED
from tests.observability.utils import validate_metrics_value
from tests.upgrade_params import IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID
from utilities.constants import DEPENDENCY_SCOPE_SESSION


@pytest.mark.cnv_upgrade
class TestUpgradeObservability:
    TEST_METRIC_KUBEVIRT_VMI_NUMBER_OF_OUTDATED_BEFORE_UPGRADE = (
        "test_metric_kubevirt_vmi_number_of_outdated_before_upgrade"
    )
    """Pre-upgrade tests"""

    @pytest.mark.order(before=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID)
    @pytest.mark.dependency(name=TEST_METRIC_KUBEVIRT_VMI_NUMBER_OF_OUTDATED_BEFORE_UPGRADE)
    @pytest.mark.polarion("CNV-11749")
    def test_metric_kubevirt_vmi_number_of_outdated_before_upgrade(self, prometheus, vm_with_node_selector_for_upgrade):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_NUMBER_OF_OUTDATED,
            expected_value="0",
        )

    """Post-upgrade tests"""

    @pytest.mark.polarion("CNV-11758")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID)
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID, TEST_METRIC_KUBEVIRT_VMI_NUMBER_OF_OUTDATED_BEFORE_UPGRADE],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_metric_kubevirt_vmi_number_of_outdated_after_upgrade(self, prometheus, kubevirt_resource_scope_session):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_NUMBER_OF_OUTDATED,
            expected_value=str(kubevirt_resource_scope_session.instance.status.outdatedVirtualMachineInstanceWorkloads),
        )
