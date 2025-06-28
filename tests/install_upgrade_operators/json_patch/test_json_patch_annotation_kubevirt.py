import pytest
from ocp_resources.resource import Resource

from tests.install_upgrade_operators.json_patch.constants import (
    ALERT_NAME,
    COMPONENT_KUBEVIRT,
    DISABLE_TLS,
    PATH_KUBEVIRT,
    QUERY_STRING,
)
from tests.install_upgrade_operators.json_patch.utils import (
    filter_metric_by_component,
    validate_kubevirt_json_patch,
    wait_for_alert,
    wait_for_firing_alert_clean_up,
    wait_for_metrics_value_update,
)
from utilities.hco import (
    is_hco_tainted,
    update_hco_annotations,
    wait_for_hco_conditions,
)

pytestmark = [pytest.mark.arm64]


@pytest.fixture(scope="class")
def json_patched_kubevirt(admin_client, hco_namespace, prometheus, hyperconverged_resource_scope_class):
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_class,
        path=PATH_KUBEVIRT,
        value={DISABLE_TLS: True},
        component=COMPONENT_KUBEVIRT,
    ):
        yield
    assert not is_hco_tainted(admin_client=admin_client, hco_namespace=hco_namespace.name)
    wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=ALERT_NAME)


@pytest.mark.usefixtures(
    "kubevirt_all_unsafe_modification_metrics_before_test",
    "kubevirt_alerts_before_test",
    "json_patched_kubevirt",
)
class TestKubevirtJsonPatch:
    @pytest.mark.polarion("CNV-8689")
    @pytest.mark.s390x
    def test_kubevirt_json_patch(
        self,
        admin_client,
        hco_namespace,
        kubevirt_resource,
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            expected_conditions={
                **{"TaintedConfiguration": Resource.Condition.Status.TRUE},
            },
        )
        validate_kubevirt_json_patch(kubevirt_resource=kubevirt_resource)

    @pytest.mark.polarion("CNV-9697")
    @pytest.mark.s390x
    def test_kubevirt_json_patch_metrics(self, prometheus, kubevirt_all_unsafe_modification_metrics_before_test):
        before_value = filter_metric_by_component(
            metrics=kubevirt_all_unsafe_modification_metrics_before_test,
            component_name=COMPONENT_KUBEVIRT,
            metric_name=QUERY_STRING,
        )
        wait_for_metrics_value_update(
            prometheus=prometheus,
            component_name=COMPONENT_KUBEVIRT,
            query_string=QUERY_STRING,
            previous_value=before_value,
        )

    @pytest.mark.polarion("CNV-9698")
    @pytest.mark.s390x
    def test_kubevirt_json_patch_alert(self, prometheus):
        wait_for_alert(
            prometheus=prometheus,
            alert_name=ALERT_NAME,
            component_name=COMPONENT_KUBEVIRT,
        )
