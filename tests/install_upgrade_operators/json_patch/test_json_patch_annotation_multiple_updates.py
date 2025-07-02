import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import Resource

from tests.install_upgrade_operators.json_patch.constants import (
    ALERT_NAME,
    COMPONENT_CDI,
    COMPONENT_KUBEVIRT,
    DISABLE_TLS,
    PATH_CDI,
    PATH_KUBEVIRT,
    QUERY_STRING,
)
from tests.install_upgrade_operators.json_patch.utils import (
    filter_metric_by_component,
    validate_cdi_json_patch,
    validate_kubevirt_json_patch,
    wait_for_alert,
    wait_for_firing_alert_clean_up,
    wait_for_metrics_value_update,
)
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    get_json_patch_annotation_values,
    is_hco_tainted,
    wait_for_hco_conditions,
)

pytestmark = [pytest.mark.arm64]

COMPONENT_DICT = {
    COMPONENT_CDI: {"op": "remove", "value": None, "path": PATH_CDI},
    COMPONENT_KUBEVIRT: {
        "op": "add",
        "value": {DISABLE_TLS: True},
        "path": PATH_KUBEVIRT,
    },
}

LOGGER = logging.getLogger(__name__)


def get_metadata():
    annotation_dict = {}
    for component in COMPONENT_DICT:
        annotation_dict.update(
            get_json_patch_annotation_values(
                component=component,
                op=COMPONENT_DICT[component]["op"],
                value=COMPONENT_DICT[component]["value"],
                path=COMPONENT_DICT[component]["path"],
            )
        )
    return {"metadata": {"annotations": annotation_dict}}


@pytest.fixture(scope="class")
def multiple_json_patched(admin_client, hco_namespace, prometheus, hyperconverged_resource_scope_class):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: get_metadata(),
        },
        list_resource_reconcile=[CDI, KubeVirt],
    ):
        yield

    assert not is_hco_tainted(admin_client=admin_client, hco_namespace=hco_namespace.name)
    wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=ALERT_NAME)


@pytest.mark.usefixtures(
    "kubevirt_all_unsafe_modification_metrics_before_test",
    "kubevirt_alerts_before_test",
    "cdi_feature_gates_scope_class",
    "multiple_json_patched",
)
class TestMultipleJsonPatch:
    @pytest.mark.polarion("CNV-8718")
    @pytest.mark.s390x
    def test_multiple_json_patch(
        self,
        admin_client,
        hco_namespace,
        cdi_feature_gates_scope_class,
        kubevirt_resource,
        cdi_resource_scope_function,
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            expected_conditions={
                **{"TaintedConfiguration": Resource.Condition.Status.TRUE},
            },
        )
        validate_cdi_json_patch(
            cdi_resource=cdi_resource_scope_function,
            before_value=cdi_feature_gates_scope_class,
        )
        validate_kubevirt_json_patch(kubevirt_resource=kubevirt_resource)

    @pytest.mark.polarion("CNV-8720")
    @pytest.mark.s390x
    def test_multiple_json_patch_metrics(self, prometheus, kubevirt_all_unsafe_modification_metrics_before_test):
        component_metrics_dict = {
            component: filter_metric_by_component(
                metrics=kubevirt_all_unsafe_modification_metrics_before_test,
                component_name=component,
                metric_name=QUERY_STRING,
            )
            for component in [COMPONENT_CDI, COMPONENT_KUBEVIRT]
        }
        for component_name in component_metrics_dict:
            LOGGER.info(f"Waiting for metrics: {QUERY_STRING} for component: {component_name}")
            wait_for_metrics_value_update(
                prometheus=prometheus,
                component_name=component_name,
                query_string=QUERY_STRING,
                previous_value=component_metrics_dict[component_name],
            )

    @pytest.mark.polarion("CNV-8813")
    @pytest.mark.s390x
    def test_multiple_json_patch_alert(self, prometheus):
        for component in COMPONENT_DICT.keys():
            LOGGER.info(f"Waiting for alert: {ALERT_NAME} for component: {component}")
            wait_for_alert(prometheus=prometheus, alert_name=ALERT_NAME, component_name=component)
