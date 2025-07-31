import pytest
from ocp_resources.cdi import CDI
from ocp_resources.resource import Resource

from tests.install_upgrade_operators.json_patch.constants import (
    ALERT_NAME,
    COMPONENT_CDI,
    PATH_CDI,
    QUERY_STRING,
)
from tests.install_upgrade_operators.json_patch.utils import (
    filter_metric_by_component,
    validate_cdi_json_patch,
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
def json_patched_cdi(admin_client, hco_namespace, prometheus, hyperconverged_resource_scope_class):
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_class,
        path=PATH_CDI,
        op="remove",
        component=COMPONENT_CDI,
        resource_list=[CDI],
    ):
        yield
    assert not is_hco_tainted(admin_client=admin_client, hco_namespace=hco_namespace.name)
    wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=ALERT_NAME)


@pytest.mark.usefixtures(
    "kubevirt_all_unsafe_modification_metrics_before_test",
    "kubevirt_alerts_before_test",
    "cdi_feature_gates_scope_class",
    "json_patched_cdi",
)
class TestKubevirtJsonPatch:
    @pytest.mark.polarion("CNV-8717")
    @pytest.mark.s390x
    def test_cdi_json_patch(
        self,
        admin_client,
        hco_namespace,
        cdi_feature_gates_scope_class,
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

    @pytest.mark.polarion("CNV-9707")
    @pytest.mark.s390x
    def test_cdi_json_patch_metrics(self, prometheus, kubevirt_all_unsafe_modification_metrics_before_test):
        before_value = filter_metric_by_component(
            metrics=kubevirt_all_unsafe_modification_metrics_before_test,
            component_name=COMPONENT_CDI,
            metric_name=QUERY_STRING,
        )
        wait_for_metrics_value_update(
            prometheus=prometheus,
            component_name=COMPONENT_CDI,
            query_string=QUERY_STRING,
            previous_value=before_value,
        )

    @pytest.mark.polarion("CNV-9706")
    @pytest.mark.s390x
    def test_cdi_json_patch_alert(self, prometheus):
        wait_for_alert(prometheus=prometheus, alert_name=ALERT_NAME, component_name=COMPONENT_CDI)
