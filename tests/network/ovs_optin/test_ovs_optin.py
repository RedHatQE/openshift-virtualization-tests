import logging

import pytest
from ocp_resources.network_addons_config import NetworkAddonsConfig

from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.network import (
    DEPLOY_OVS,
    verify_ovs_installed_with_annotations,
    wait_for_ovs_daemonset_deleted,
    wait_for_ovs_pods,
    wait_for_ovs_status,
)

LOGGER = logging.getLogger()


def wait_for_ovs_removed(admin_client, ovs_daemonset, network_addons_config):
    wait_for_ovs_status(network_addons_config=network_addons_config, status=False)
    wait_for_ovs_daemonset_deleted(ovs_daemonset=ovs_daemonset)
    wait_for_ovs_pods(
        admin_client=admin_client,
        hco_namespace=ovs_daemonset.namespace,
    )


@pytest.fixture()
def hyperconverged_ovs_annotations_disabled(
    hyperconverged_resource_scope_function,
    hyperconverged_ovs_annotations_enabled_scope_session,
):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: {"metadata": {"annotations": {DEPLOY_OVS: "false"}}}},
        list_resource_reconcile=[NetworkAddonsConfig],
    ):
        yield


@pytest.fixture()
def hyperconverged_ovs_annotations_removed(
    hyperconverged_resource_scope_function,
    hyperconverged_ovs_annotations_enabled_scope_session,
):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: {"metadata": {"annotations": {DEPLOY_OVS: None}}}},
        list_resource_reconcile=[NetworkAddonsConfig],
    ):
        yield


@pytest.mark.sno
class TestOVSOptIn:
    @pytest.mark.polarion("CNV-5520")
    @pytest.mark.single_nic
    @pytest.mark.s390x
    def test_ovs_installed(
        self,
        admin_client,
        network_addons_config_scope_session,
        hyperconverged_ovs_annotations_enabled_scope_session,
        hyperconverged_ovs_annotations_fetched,
    ):
        verify_ovs_installed_with_annotations(
            admin_client=admin_client,
            ovs_daemonset=hyperconverged_ovs_annotations_enabled_scope_session,
            hyperconverged_ovs_annotations_fetched=hyperconverged_ovs_annotations_fetched,
            network_addons_config=network_addons_config_scope_session,
        )

    @pytest.mark.polarion("CNV-5533")
    @pytest.mark.single_nic
    @pytest.mark.s390x
    def test_ovs_not_installed_annotations_removed(
        self,
        admin_client,
        network_addons_config_scope_session,
        hyperconverged_ovs_annotations_enabled_scope_session,
        hyperconverged_ovs_annotations_removed,
    ):
        wait_for_ovs_removed(
            admin_client=admin_client,
            ovs_daemonset=hyperconverged_ovs_annotations_enabled_scope_session,
            network_addons_config=network_addons_config_scope_session,
        )

    @pytest.mark.polarion("CNV-5531")
    @pytest.mark.single_nic
    @pytest.mark.s390x
    def test_ovs_not_installed_annotations_disabled(
        self,
        admin_client,
        network_addons_config_scope_session,
        hyperconverged_ovs_annotations_enabled_scope_session,
        hyperconverged_ovs_annotations_disabled,
    ):
        wait_for_ovs_removed(
            admin_client=admin_client,
            ovs_daemonset=hyperconverged_ovs_annotations_enabled_scope_session,
            network_addons_config=network_addons_config_scope_session,
        )
