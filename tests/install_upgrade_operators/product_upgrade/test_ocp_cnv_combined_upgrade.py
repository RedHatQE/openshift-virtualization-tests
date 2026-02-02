import logging

import pytest

from tests.install_upgrade_operators.product_upgrade.utils import verify_upgrade_cnv, verify_upgrade_ocp
from tests.upgrade_params import CNV_PHASE_NODE_ID, OCP_PHASE_NODE_ID

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.product_upgrade_test,
    pytest.mark.sno,
    pytest.mark.upgrade,
    pytest.mark.upgrade_custom,
    pytest.mark.usefixtures(
        "nodes_taints_before_upgrade",
        "nodes_labels_before_upgrade",
    ),
]


@pytest.mark.ocp_cnv_upgrade
class TestOCPCNVCombinedUpgrade:
    @pytest.mark.polarion("CNV-XXXX")
    @pytest.mark.dependency(name=OCP_PHASE_NODE_ID)
    def test_ocp_upgrade_phase(
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
        """Phase 1: Upgrade OCP and verify completion"""
        LOGGER.info("Starting OCP upgrade phase", extra={"phase": "ocp"})
        verify_upgrade_ocp(
            admin_client=admin_client,
            target_ocp_version=extracted_ocp_version_from_image_url,
            machine_config_pools_list=active_machine_config_pools,
            initial_mcp_conditions=machine_config_pools_conditions,
            nodes=nodes,
        )
        LOGGER.info("OCP upgrade phase completed successfully", extra={"phase": "ocp"})

    @pytest.mark.gating
    @pytest.mark.polarion("CNV-YYYY")
    @pytest.mark.dependency(name=CNV_PHASE_NODE_ID, depends=[OCP_PHASE_NODE_ID])
    def test_cnv_upgrade_phase(
        self,
        admin_client,
        hco_namespace,
        cnv_target_version,
        cnv_upgrade_stream,
        post_ocp_tests_completed,
        disabled_default_sources_in_operatorhub,
        updated_image_content_source_policy,
        updated_custom_hco_catalog_source_image,
        updated_cnv_subscription_source,
        approved_cnv_upgrade_install_plan,
        started_cnv_upgrade,
        created_target_hco_csv,
        related_images_from_target_csv,
        upgraded_cnv,
    ):
        """Phase 2: Upgrade CNV and verify completion"""
        LOGGER.info("Starting CNV upgrade phase", extra={"phase": "cnv"})
        verify_upgrade_cnv(
            client=admin_client,
            hco_namespace=hco_namespace,
            expected_images=related_images_from_target_csv.values(),
        )
        LOGGER.info("CNV upgrade phase completed successfully", extra={"phase": "cnv"})
