import logging

import pytest

from tests.install_upgrade_operators.product_upgrade.utils import (
    verify_upgrade_cnv,
    verify_upgrade_ocp,
)
from tests.install_upgrade_operators.utils import wait_for_install_plan
from tests.upgrade_params import IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID

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
LOGGER = logging.getLogger(__name__)


@pytest.mark.gating
@pytest.mark.cnv_upgrade
@pytest.mark.order("first")
@pytest.mark.polarion("CNV-12451")
@pytest.mark.usefixtures(
    "cnv_upgrade_stream",
    "disabled_default_sources_in_operatorhub",
    "updated_konflux_idms",
    "updated_custom_hco_catalog_source_image",
    "updated_cnv_subscription_source",
)
def test_cnv_upgrade_install_plan_creation(
    admin_client,
    hco_namespace,
    hco_target_csv_name,
    is_production_source,
    cnv_subscription_scope_session,
):
    wait_for_install_plan(
        client=admin_client,
        hco_namespace=hco_namespace.name,
        hco_target_csv_name=hco_target_csv_name,
        is_production_source=is_production_source,
        cnv_subscription=cnv_subscription_scope_session,
    )


class TestUpgrade:
    @pytest.mark.ocp_upgrade
    @pytest.mark.polarion("CNV-8381")
    @pytest.mark.dependency(name=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID)
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

    @pytest.mark.gating
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
        approved_cnv_upgrade_install_plan,
        started_cnv_upgrade,
        created_target_hco_csv,
        related_images_from_target_csv,
        upgraded_cnv,
    ):
        """
        Test the CNV upgrade process. The main steps of the test are:

        1. Approve the upgrade InstallPlan (created by test_cnv_upgrade_install_plan_creation).
        2. Wait until the upgrade has finished:
            2.1. Wait for CSV to be created and reach status SUCCEEDED.
            2.2. Wait for HCO OperatorCondition to reach status Upgradeable=True.
            2.3. Wait until all the pods have been replaced.
            2.4. Wait until HCO is stable and its version is updated.
        """
        verify_upgrade_cnv(
            client=admin_client,
            hco_namespace=hco_namespace,
            expected_images=related_images_from_target_csv.values(),
        )

    @pytest.mark.gating
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
        approved_cnv_upgrade_install_plan,
        started_cnv_upgrade,
        created_target_hco_csv,
        related_images_from_target_csv,
        upgraded_cnv,
    ):
        """
        Test the CNV upgrade process using the production source.
        The main steps are the same as for custom source,
        but source configuration is handled by test_cnv_upgrade_install_plan_creation.
        """
        verify_upgrade_cnv(
            client=admin_client,
            hco_namespace=hco_namespace,
            expected_images=related_images_from_target_csv.values(),
        )
