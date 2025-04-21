import logging

import pytest

from tests.upgrade_params import (
    IUO_CNV_ALERT_ORDERING_NODE_ID,
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
    VIRT_NODE_ID_PREFIX,
)
from tests.virt.upgrade_custom.aaq.constants import UPGRADE_QUOTA_FOR_ONE_VMI
from tests.virt.utils import check_arq_status_values, check_pod_in_gated_state
from utilities.constants import DEPENDENCY_SCOPE_SESSION

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.upgrade_custom,
    pytest.mark.cnv_upgrade,
    pytest.mark.ocp_upgrade,
    pytest.mark.usefixtures(
        "enabled_aaq_in_hco_scope_session",
    ),
]


@pytest.mark.sno
class TestUpgradeVirtAAQ:
    """Pre-upgrade tests"""

    @pytest.mark.polarion("CNV-11245")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{VIRT_NODE_ID_PREFIX}::test_arq_before_upgrade")
    def test_arq_before_upgrade(
        self,
        application_aware_resource_quota_upgrade,
        vm_for_arq_upgrade_test,
        vm_for_arq_upgrade_test_in_gated_state,
    ):
        check_arq_status_values(
            current_values=application_aware_resource_quota_upgrade.instance.status.used,
            expected_values=UPGRADE_QUOTA_FOR_ONE_VMI,
        )

    @pytest.mark.polarion("CNV-11428")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{VIRT_NODE_ID_PREFIX}::test_acrq_before_upgrade")
    def test_acrq_before_upgrade(
        self,
        application_aware_cluster_resource_quota_upgrade,
        vm_for_acrq_upgrade_test,
        vm_for_acrq_upgrade_test_in_gated_state,
    ):
        check_arq_status_values(
            current_values=application_aware_cluster_resource_quota_upgrade.instance.status.total.used,
            expected_values=UPGRADE_QUOTA_FOR_ONE_VMI,
        )

    """ Post-upgrade tests """

    @pytest.mark.polarion("CNV-11429")
    @pytest.mark.order(after=[IUO_CNV_ALERT_ORDERING_NODE_ID])
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{VIRT_NODE_ID_PREFIX}::test_arq_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_arq_after_upgrade(
        self,
        application_aware_resource_quota_upgrade,
        vm_for_arq_upgrade_test,
        vm_for_arq_upgrade_test_in_gated_state,
    ):
        check_pod_in_gated_state(pod=vm_for_arq_upgrade_test_in_gated_state.vmi.virt_launcher_pod)
        check_arq_status_values(
            current_values=application_aware_resource_quota_upgrade.instance.status.used,
            expected_values=UPGRADE_QUOTA_FOR_ONE_VMI,
        )

    @pytest.mark.polarion("CNV-11430")
    @pytest.mark.order(after=[IUO_CNV_ALERT_ORDERING_NODE_ID])
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{VIRT_NODE_ID_PREFIX}::test_acrq_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_acrq_after_upgrade(
        self,
        application_aware_cluster_resource_quota_upgrade,
        vm_for_acrq_upgrade_test,
        vm_for_acrq_upgrade_test_in_gated_state,
    ):
        check_pod_in_gated_state(pod=vm_for_acrq_upgrade_test_in_gated_state.vmi.virt_launcher_pod)
        check_arq_status_values(
            current_values=application_aware_cluster_resource_quota_upgrade.instance.status.total.used,
            expected_values=UPGRADE_QUOTA_FOR_ONE_VMI,
        )
