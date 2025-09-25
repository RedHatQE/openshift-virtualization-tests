import pytest

from tests.observability.metrics.utils import (
    timestamp_to_seconds,
    validate_values_from_kube_application_aware_resourcequota_metric,
)
from tests.observability.utils import validate_metrics_value

pytestmark = [
    pytest.mark.usefixtures(
        "enabled_aaq_in_hco_scope_module",
        "updated_namespace_with_aaq_label",
    ),
]


class TestAAQMetrics:
    @pytest.mark.polarion("CNV-12183")
    def test_kube_application_aware_resourcequota_creation_timestamp(
        self,
        prometheus,
        application_aware_resource_quota_creation_timestamp,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            expected_value=str(timestamp_to_seconds(timestamp=application_aware_resource_quota_creation_timestamp)),
            metric_name="kube_application_aware_resourcequota_creation_timestamp",
        )

    @pytest.mark.polarion("CNV-12184")
    def test_kube_application_aware_resourcequota_metrics(
        self,
        prometheus,
        application_aware_resource_quota,
        vm_for_test_with_resource_limits,
        aaq_resource_hard_limit_and_used,
    ):
        validate_values_from_kube_application_aware_resourcequota_metric(
            prometheus=prometheus, aaq_resource_hard_limit_and_used=aaq_resource_hard_limit_and_used
        )
