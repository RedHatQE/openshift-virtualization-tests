import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.resource import ResourceEditor

from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CUSTOM_HCO_CR_SPEC,
)
from tests.install_upgrade_operators.strict_reconciliation.utils import (
    get_resource_object,
    get_resource_version_from_related_object,
    wait_for_hco_related_object_version_change,
    wait_for_resource_version_update,
)
from tests.utils import wait_for_cr_labels_change
from utilities.constants import HCO_BEARER_AUTH, TIMEOUT_1MIN, VERSION_LABEL_KEY
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.jira import is_jira_open

LOGGER = logging.getLogger(__name__)
DISABLED_KUBEVIRT_FEATUREGATES_IN_SNO = ["LiveMigration", "SRIOVLiveMigration"]


@pytest.fixture()
def deleted_stanza_on_hco_cr(request, hyperconverged_resource_scope_function, admin_client, hco_namespace):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: request.param["rpatch"]},
        action="replace",
        list_resource_reconcile=request.param.get("list_resource_reconcile"),
        wait_for_reconcile_post_update=request.param.get("wait_for_reconcile", True),
    ):
        yield


@pytest.fixture()
def hco_cr_custom_values(hyperconverged_resource_scope_function, admin_client, hco_namespace):
    """
    This fixture updates HCO CR with custom values for spec.CertConfig, spec.liveMigrationConfig and
    spec.featureGates and cleans those up at the end.
    Note: This is needed for tests that modifies such fields to default values

    Args:
        hyperconverged_resource_scope_function (HyperConverged): HCO CR

    """
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: CUSTOM_HCO_CR_SPEC.copy()},
        list_resource_reconcile=[CDI, KubeVirt, NetworkAddonsConfig],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def updated_cdi_cr(request, cdi_resource_scope_function, admin_client, hco_namespace):
    """
    Attempts to update cdi, however, since these changes get reconciled to values propagated by hco cr, we don't need
    to restore these.
    """
    with ResourceEditorValidateHCOReconcile(
        patches={
            cdi_resource_scope_function: request.param["patch"],
        },
        list_resource_reconcile=[CDI],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def updated_cnao_cr(request, cnao_resource, admin_client, hco_namespace):
    """
    Attempts to update cnao, however, since these changes get reconciled to values propagated by hco cr, we don't need
    to restore these.
    """
    with ResourceEditorValidateHCOReconcile(
        patches={cnao_resource: request.param["patch"]},
        list_resource_reconcile=[NetworkAddonsConfig],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def updated_kv_with_feature_gates(request, admin_client, hco_namespace, kubevirt_resource):
    kv_dict = kubevirt_resource.instance.to_dict()
    fgs = kv_dict["spec"]["configuration"]["developerConfiguration"]["featureGates"].copy()
    fgs.extend(request.param)

    with ResourceEditorValidateHCOReconcile(
        patches={kubevirt_resource: {"spec": {"configuration": {"developerConfiguration": {"featureGates": fgs}}}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def updated_cdi_with_feature_gates(request, cdi_resource_scope_function, admin_client, hco_namespace):
    cdi_dict = cdi_resource_scope_function.instance.to_dict()
    fgs = cdi_dict["spec"]["config"]["featureGates"].copy()
    fgs.extend(request.param)
    with ResourceEditorValidateHCOReconcile(
        patches={cdi_resource_scope_function: {"spec": {"config": {"featureGates": fgs}}}},
        list_resource_reconcile=[CDI],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def hco_with_non_default_feature_gates(
    request,
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
):
    new_fgs = request.param["fgs"]
    hco_fgs = hyperconverged_resource_scope_function.instance.to_dict()["spec"]["featureGates"]

    for fg in new_fgs:
        hco_fgs[fg] = True
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: {"spec": {"featureGates": hco_fgs}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def cr_func_map(
    hco_spec,
    kubevirt_hyperconverged_spec_scope_function,
    cdi_spec,
    network_addons_config_scope_session,
):
    yield {
        "hco": hco_spec,
        "kubevirt": kubevirt_hyperconverged_spec_scope_function,
        "cdi": cdi_spec,
        "cnao": network_addons_config_scope_session.instance.to_dict(),
    }


@pytest.fixture()
def hco_status_related_objects_scope_function(hyperconverged_resource_scope_function):
    """
    Gets HCO.status.relatedObjects list
    """
    return hyperconverged_resource_scope_function.instance.status.relatedObjects


@pytest.fixture()
def reconciled_cr_post_hco_update(
    request,
    admin_client,
    hco_namespace,
    hco_status_related_objects_scope_function,
):
    resource = get_resource_object(
        resource=request.param["resource_class"],
        resource_name=request.param["resource_name"],
        resource_namespace=hco_namespace.name,
    )

    start_resource_version = get_resource_version_from_related_object(
        hco_related_objects=hco_status_related_objects_scope_function, resource=resource
    )
    assert start_resource_version is not None, (
        f"For resource: {resource.name}, no resource version found from hco.status.relatedObject"
    )
    LOGGER.info(
        f"For resource: {resource.name}, kind: {resource.kind}, starting resource version: {start_resource_version}"
    )
    wait_for_resource_version_update(resource=resource, pre_update_resource_version=start_resource_version)
    wait_for_hco_related_object_version_change(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        resource=resource,
        resource_kind=resource.kind,
    )
    yield resource


@pytest.fixture()
def pre_update_resource_version(related_object_from_hco_status):
    return related_object_from_hco_status["resourceVersion"]


@pytest.fixture()
def updated_resource_labels(ocp_resource_by_name):
    expected_labels = ocp_resource_by_name.labels
    expected_labels.custom_label = ocp_resource_by_name.name
    with ResourceEditor(
        patches={
            ocp_resource_by_name: {
                "metadata": {
                    "labels": {VERSION_LABEL_KEY: None, "custom_label": ocp_resource_by_name.name},
                }
            }
        }
    ):
        wait_for_cr_labels_change(expected_value=expected_labels, component=ocp_resource_by_name, timeout=TIMEOUT_1MIN)
        yield expected_labels


@pytest.fixture()
def xfail_if_hco_bearer_token_bug_open(ocp_resource_by_name):
    if ocp_resource_by_name.name == HCO_BEARER_AUTH and is_jira_open(jira_id="CNV-71826"):
        pytest.xfail(f"{HCO_BEARER_AUTH} resource is not reconciled due to CNV-71826 bug")
