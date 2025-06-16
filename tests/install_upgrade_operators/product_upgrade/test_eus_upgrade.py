import logging

import pytest

from tests.install_upgrade_operators.product_upgrade.utils import verify_upgrade_cnv
from tests.upgrade_params import IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID
from utilities.infra import get_related_images_name_and_version

LOGGER = logging.getLogger(__name__)


@pytest.mark.product_upgrade_test
@pytest.mark.upgrade
@pytest.mark.upgrade_custom
@pytest.mark.eus_upgrade
class TestEUSToEUSUpgrade:
    @pytest.mark.polarion("CNV-9509")
    @pytest.mark.dependency(name=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID)
    def test_eus_upgrade_process(
        self,
        admin_client,
        hco_namespace,
        eus_target_cnv_version,
        eus_cnv_upgrade_path,
        eus_paused_worker_mcp,
        eus_paused_workload_update,
        source_eus_to_non_eus_ocp_upgraded,
        source_eus_to_non_eus_cnv_upgraded,
        upgraded_odf,
        non_eus_to_target_eus_ocp_upgraded,
        non_eus_to_target_eus_cnv_upgraded,
        eus_created_target_hco_csv,
        eus_unpaused_workload_update,
        eus_unpaused_worker_mcp,
    ):
        LOGGER.info("Validate EUS to EUS upgrade process")
        verify_upgrade_cnv(
            dyn_client=admin_client,
            hco_namespace=hco_namespace,
            expected_images=get_related_images_name_and_version(csv=eus_created_target_hco_csv).values(),
        )
        LOGGER.info("EUS post upgrade validation completed.")
