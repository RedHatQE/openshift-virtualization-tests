import logging

import pytest

from tests.install_upgrade_operators.product_upgrade.utils import (
    verify_upgrade_cnv,
    verify_upgrade_ocp,
)
from tests.upgrade_params import IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID

pytestmark = pytest.mark.usefixtures(
    "nodes_taints_before_upgrade",
    "nodes_labels_before_upgrade",
)
LOGGER = logging.getLogger(__name__)


@pytest.mark.product_upgrade_test
@pytest.mark.sno
@pytest.mark.upgrade
@pytest.mark.upgrade_custom
class TestUpgrade:
    @pytest.mark.ocp_upgrade
    @pytest.mark.polarion("CNV-8381")
    @pytest.mark.dependency(name=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID)
    def test_ocp_upgrade_process(
        self,
        admin_client,
        nodes,
        machine_config_pools,
        machine_config_pools_conditions,
        extracted_ocp_version_from_image_url,
        updated_ocp_upgrade_channel,
        fired_alerts_before_upgrade,
        triggered_ocp_upgrade,
    ):
        verify_upgrade_ocp(
            admin_client=admin_client,
            target_ocp_version=extracted_ocp_version_from_image_url,
            machine_config_pools_list=machine_config_pools,
            initial_mcp_conditions=machine_config_pools_conditions,
            nodes=nodes,
        )

    @pytest.mark.cnv_upgrade
    @pytest.mark.polarion("CNV-2991")
    @pytest.mark.dependency(name=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID)
    def test_cnv_upgrade_process(
        self,
        admin_client,
        hco_namespace,
        cnv_target_version,
        cnv_upgrade_stream,
        fired_alerts_before_upgrade,
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
        """
        Test the CNV upgrade process (using OSBS/fbc sources). The main steps of the test are:

        1. Disable the default sources in operatorhub in order to be able to upgrade usg a custom catalog source.
        2. Generate a new ICSP for the IIB image being used.
        3. Update HCO CatalogSource with the image being used.
        4. Update the CNV Subscription source.
        5. Wait for the upgrade InstallPlan to be created and approve it.
        6. Wait until the upgrade has finished:
            6.1. Wait for CSV to be created and reach status SUCCEEDED.
            6.2. Wait for HCO OperatorCondition to reach status Upgradeable=True.
            6.3. Wait until all the pods have been replaced.
            6.4. Wait until HCO is stable and its version is updated.
        """
        verify_upgrade_cnv(
            dyn_client=admin_client,
            hco_namespace=hco_namespace,
            expected_images=related_images_from_target_csv.values(),
        )

    @pytest.mark.cnv_upgrade
    @pytest.mark.polarion("CNV-9933")
    @pytest.mark.dependency(name=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID)
    def test_production_source_cnv_upgrade_process(
        self,
        admin_client,
        hco_namespace,
        cnv_target_version,
        cnv_upgrade_stream,
        fired_alerts_before_upgrade,
        updated_cnv_subscription_source,
        approved_cnv_upgrade_install_plan,
        started_cnv_upgrade,
        created_target_hco_csv,
        related_images_from_target_csv,
        upgraded_cnv,
    ):
        """
        Test the CNV upgrade process using the production source.
        The main steps of the test are the same as for osbs/fbc source,
        but it is not needed to disable the default sources, create a new ICSP or update the HCO CatalogSource.
        """
        verify_upgrade_cnv(
            dyn_client=admin_client,
            hco_namespace=hco_namespace,
            expected_images=related_images_from_target_csv.values(),
        )
