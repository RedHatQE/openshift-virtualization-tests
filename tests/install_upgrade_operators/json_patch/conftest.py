import pytest

from tests.install_upgrade_operators.json_patch.constants import (
    ALERT_NAME,
    QUERY_STRING,
)
from utilities.storage import get_hyperconverged_cdi


@pytest.fixture(scope="class")
def kubevirt_alerts_before_test(prometheus):
    return prometheus.get_firing_alerts(alert_name=ALERT_NAME)


@pytest.fixture(scope="class")
def kubevirt_all_unsafe_modification_metrics_before_test(prometheus):
    return prometheus.query_sampler(query=QUERY_STRING)


@pytest.fixture(scope="class")
def cdi_feature_gates_scope_class(admin_client):
    return get_hyperconverged_cdi(admin_client=admin_client).instance.spec.config.get("featureGates")
