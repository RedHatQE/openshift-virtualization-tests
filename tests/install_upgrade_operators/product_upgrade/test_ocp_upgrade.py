import logging

import pytest

from tests.install_upgrade_operators.product_upgrade.utils import (
    verify_upgrade_ocp,
)
from tests.upgrade_params import IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID

pytestmark = [
    pytest.mark.usefixtures(
        "nodes_taints_before_upgrade",
        "nodes_labels_before_upgrade",
    ),
    pytest.mark.product_upgrade_test,
    pytest.mark.sno,
    pytest.mark.upgrade,
    pytest.mark.upgrade_custom,
    pytest.mark.dependency(name=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID),
]
LOGGER = logging.getLogger(__name__)


@pytest.mark.ocp_upgrade
class TestUpgradeOCP:
    @pytest.mark.polarion("CNV-8381")
    def test_ocp_upgrade_process(
        self,
        admin_client,
        nodes,
        active_machine_config_pools,
        machine_config_pools_conditions,
        extracted_ocp_version_from_image_url,
        updated_ocp_upgrade_channel,
        fired_alerts_before_upgrade,
        triggered_ocp_upgrade,
    ):
        verify_upgrade_ocp(
            admin_client=admin_client,
            target_ocp_version=extracted_ocp_version_from_image_url,
            machine_config_pools_list=active_machine_config_pools,
            initial_mcp_conditions=machine_config_pools_conditions,
            nodes=nodes,
        )
