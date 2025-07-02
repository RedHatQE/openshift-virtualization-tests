import pytest
from ocp_resources.resource import Resource
from ocp_resources.ssp import SSP

from tests.install_upgrade_operators.constants import TEMPLATE_VALIDATOR
from tests.install_upgrade_operators.json_patch.constants import (
    ALERT_NAME,
    QUERY_STRING,
)
from tests.install_upgrade_operators.json_patch.utils import (
    filter_metric_by_component,
    wait_for_alert,
    wait_for_firing_alert_clean_up,
    wait_for_metrics_value_update,
)
from utilities.hco import (
    is_hco_tainted,
    update_hco_annotations,
    wait_for_hco_conditions,
)

COMPONENT = "ssp"
REPLICAS = 5

pytestmark = [pytest.mark.arm64]


@pytest.fixture(scope="class")
def json_patched_ssp(admin_client, hco_namespace, prometheus, hyperconverged_resource_scope_class):
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_class,
        path=TEMPLATE_VALIDATOR,
        value={"replicas": REPLICAS},
        component=COMPONENT,
        op="replace",
        resource_list=[SSP],
    ):
        yield
    assert not is_hco_tainted(admin_client=admin_client, hco_namespace=hco_namespace.name)
    wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=ALERT_NAME)


@pytest.mark.usefixtures(
    "kubevirt_all_unsafe_modification_metrics_before_test",
    "kubevirt_alerts_before_test",
    "json_patched_ssp",
)
class TestSSPJsonPatch:
    @pytest.mark.polarion("CNV-8690")
    @pytest.mark.s390x
    def test_ssp_json_patch(
        self,
        admin_client,
        hco_namespace,
        ssp_resource_scope_function,
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            expected_conditions={
                **{"TaintedConfiguration": Resource.Condition.Status.TRUE},
            },
        )
        ssp_replicas_current_value = ssp_resource_scope_function.instance.spec.templateValidator.replicas
        assert ssp_replicas_current_value == REPLICAS, (
            f"Unable to json patch ssp to set {TEMPLATE_VALIDATOR}.replicas to {REPLICAS}. "
            f"Current Value: {ssp_replicas_current_value}."
        )

    @pytest.mark.polarion("CNV-8691")
    @pytest.mark.s390x
    def test_ssp_json_patch_metrics(self, prometheus, kubevirt_all_unsafe_modification_metrics_before_test):
        before_value = filter_metric_by_component(
            metrics=kubevirt_all_unsafe_modification_metrics_before_test,
            component_name=COMPONENT,
            metric_name=QUERY_STRING,
        )
        wait_for_metrics_value_update(
            prometheus=prometheus,
            component_name=COMPONENT,
            query_string=QUERY_STRING,
            previous_value=before_value,
        )

    @pytest.mark.polarion("CNV-8714")
    @pytest.mark.s390x
    def test_ssp_json_patch_alert(self, prometheus):
        wait_for_alert(prometheus=prometheus, alert_name=ALERT_NAME, component_name=COMPONENT)
