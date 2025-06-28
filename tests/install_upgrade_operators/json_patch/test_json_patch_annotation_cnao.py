import pytest
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.resource import Resource

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

pytestmark = [pytest.mark.arm64]

PATH = "selfSignConfiguration"
COMPONENT = "cnao"


@pytest.fixture(scope="class")
def json_patched_cnao(
    admin_client,
    hco_namespace,
    prometheus,
    hyperconverged_resource_scope_class,
):
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_class,
        path=PATH,
        op="replace",
        value=None,
        component=COMPONENT,
        resource_list=[NetworkAddonsConfig],
    ):
        yield
    assert not is_hco_tainted(admin_client=admin_client, hco_namespace=hco_namespace.name)
    wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=ALERT_NAME)


@pytest.mark.usefixtures(
    "kubevirt_all_unsafe_modification_metrics_before_test",
    "kubevirt_alerts_before_test",
    "json_patched_cnao",
)
class TestCNAOJsonPatch:
    @pytest.mark.polarion("CNV-8715")
    @pytest.mark.s390x
    def test_cnao_json_patch(
        self,
        admin_client,
        hco_namespace,
        cnao_resource,
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            expected_conditions={
                **{"TaintedConfiguration": Resource.Condition.Status.TRUE},
            },
        )
        cnao_spec = cnao_resource.instance.spec
        assert not cnao_spec.get(PATH), f"Unable to replace {PATH} from CNAO via json patch. Current value: {cnao_spec}"

    @pytest.mark.polarion("CNV-9713")
    @pytest.mark.s390x
    def test_cnao_json_patch_metrics(self, prometheus, kubevirt_all_unsafe_modification_metrics_before_test):
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

    @pytest.mark.polarion("CNV-9712")
    @pytest.mark.s390x
    def test_cnao_json_patch_alert(self, prometheus):
        wait_for_alert(prometheus=prometheus, alert_name=ALERT_NAME, component_name=COMPONENT)
