import logging

import pytest

from tests.install_upgrade_operators.product_upgrade.utils import (
    process_alerts_fired_during_upgrade,
    verify_nodes_labels_after_upgrade,
    verify_nodes_taints_after_upgrade,
)
from tests.upgrade_params import (
    IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID,
    IUO_CNV_ALERT_ORDERING_NODE_ID,
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
)
from utilities.constants import DEPENDENCY_SCOPE_SESSION
from utilities.data_collector import collect_alerts_data

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.upgrade,
    pytest.mark.upgrade_custom,
    pytest.mark.cnv_upgrade,
    pytest.mark.ocp_upgrade,
    pytest.mark.sno,
]


class TestUpgradeIUO:
    """Post-upgrade tests"""

    @pytest.mark.polarion("CNV-9081")
    @pytest.mark.dependency(
        name=IUO_CNV_ALERT_ORDERING_NODE_ID,
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_alerts_fired_during_upgrade(
        self,
        prometheus_scope_function,
        fired_alerts_during_upgrade,
    ):
        LOGGER.info("Verify if any alerts were fired during upgrade")
        process_alerts_fired_during_upgrade(
            prometheus=prometheus_scope_function,
            fired_alerts_during_upgrade=fired_alerts_during_upgrade,
        )
        if fired_alerts_during_upgrade:
            collect_alerts_data()
            raise AssertionError(f"Following alerts were fired during upgrade: {fired_alerts_during_upgrade}")

    @pytest.mark.eus_upgrade
    @pytest.mark.polarion("CNV-6866")
    @pytest.mark.order(before=IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID, after=IUO_CNV_ALERT_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_nodes_taints_after_upgrade(self, admin_client, nodes, nodes_taints_before_upgrade):
        LOGGER.info("Verify nodes taints after upgrade.")
        verify_nodes_taints_after_upgrade(nodes=nodes, nodes_taints_before_upgrade=nodes_taints_before_upgrade)

    @pytest.mark.eus_upgrade
    @pytest.mark.polarion("CNV-6924")
    @pytest.mark.order(before=IMAGE_UPDATE_AFTER_UPGRADE_NODE_ID, after=IUO_CNV_ALERT_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_nodes_labels_after_upgrade(
        self,
        admin_client,
        nodes,
        nodes_labels_before_upgrade,
        cnv_upgrade,
    ):
        LOGGER.info("Verify nodes labels after upgrade.")
        verify_nodes_labels_after_upgrade(
            nodes=nodes,
            nodes_labels_before_upgrade=nodes_labels_before_upgrade,
            cnv_upgrade=cnv_upgrade,
        )
