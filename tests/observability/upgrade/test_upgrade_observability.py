import pytest

from tests.observability.constants import KUBEVIRT_VMI_NUMBER_OF_OUTDATED
from tests.observability.utils import validate_metrics_value
from tests.upgrade_params import IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID, NETWORK_NODE_ID_PREFIX
from utilities.constants.pytest import DEPENDENCY_SCOPE_SESSION


@pytest.mark.cnv_upgrade
class TestUpgradeObservability:
    TEST_METRIC_KUBEVIRT_VMI_NUMBER_OF_OUTDATED_BEFORE_UPGRADE = (
        "test_metric_kubevirt_vmi_number_of_outdated_before_upgrade"
    )
    TEST_OUTDATED_VMIS_COUNT_MATCHES = "test_outdated_vmis_count_matches_kubevirt_status_after_upgrade"
    """Pre-upgrade tests"""

    @pytest.mark.order(
        before=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
        after=[
            f"{NETWORK_NODE_ID_PREFIX}::test_vm_have_2_interfaces_before_upgrade",
            f"{NETWORK_NODE_ID_PREFIX}::test_linux_bridge_before_upgrade",
            f"{NETWORK_NODE_ID_PREFIX}::test_kubemacpool_disabled_ns_before_upgrade",
            f"{NETWORK_NODE_ID_PREFIX}::test_kubemacpool_before_upgrade",
            f"{NETWORK_NODE_ID_PREFIX}::test_vm_connectivity_with_macspoofing_before_upgrade",
        ],
    )
    @pytest.mark.dependency(name=TEST_METRIC_KUBEVIRT_VMI_NUMBER_OF_OUTDATED_BEFORE_UPGRADE)
    @pytest.mark.polarion("CNV-11749")
    def test_metric_kubevirt_vmi_number_of_outdated_before_upgrade(self, prometheus, vm_with_node_selector_for_upgrade):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_NUMBER_OF_OUTDATED,
            expected_value="0",
        )

    """Post-upgrade tests"""

    @pytest.mark.polarion("CNV-11757")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID)
    @pytest.mark.dependency(
        name=TEST_OUTDATED_VMIS_COUNT_MATCHES,
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_outdated_vmis_count_matches_kubevirt_status_after_upgrade(self, outdated_vmis_count):
        """
        Verify that VMIs with outdatedLauncherImage label exist after upgrade.
        """
        assert outdated_vmis_count > 0, "No VMIs with outdatedLauncherImage label found after upgrade"

    @pytest.mark.polarion("CNV-11758")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            TEST_METRIC_KUBEVIRT_VMI_NUMBER_OF_OUTDATED_BEFORE_UPGRADE,
            TEST_OUTDATED_VMIS_COUNT_MATCHES,
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_metric_kubevirt_vmi_number_of_outdated_after_upgrade(self, prometheus, outdated_vmis_count):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_NUMBER_OF_OUTDATED,
            expected_value=str(outdated_vmis_count),
        )
