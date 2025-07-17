import bitmath
import pytest

from tests.observability.metrics.utils import (
    timestamp_to_seconds,
    validate_metrics_value,
)

pytestmark = [
    pytest.mark.usefixtures(
        "enabled_aaq_in_hco_scope_package",
        "updated_namespace_with_aaq_label",
    ),
]


def validate_kube_application_aware_resourcequota_metrics_value(actual_values, expected_values):
    resource_hard_limit, resource_used = expected_values
    for resource in actual_values:
        expected_hard_limit = int(bitmath.parse_string_unsafe(resource_hard_limit.get(resource)).to_Byte().value)
        expected_used = int(bitmath.parse_string_unsafe(resource_used.get(resource)).to_Byte().value)
        actual_hard_limit = actual_values[resource].get("hard")
        actual_used = actual_values[resource].get("used")
        if expected_hard_limit:
            assert actual_hard_limit == expected_hard_limit, (
                f"[HARD LIMIT] Mismatch for {resource}: expected {expected_hard_limit}, got {actual_hard_limit}"
            )

        if expected_used:
            assert actual_used == expected_used, (
                f"[USED] Mismatch for {resource}: expected {expected_used}, got {actual_used}"
            )


@pytest.fixture()
def application_aware_resource_quota_creation_timestamp(application_aware_resource_quota):
    return application_aware_resource_quota.instance.metadata.creationTimestamp


@pytest.fixture()
def aaq_resource_hard_limit_and_used(application_aware_resource_quota):
    application_aware_resource_quota_instance = application_aware_resource_quota.instance
    resource_hard_limit = application_aware_resource_quota_instance.spec.hard
    resource_used = application_aware_resource_quota_instance.status.used
    return resource_hard_limit, resource_used


@pytest.fixture
def values_from_kube_application_aware_resourcequota_metric(prometheus):
    result = {}
    for item in prometheus.query_sampler(query="kube_application_aware_resourcequota"):
        if "value" in item:
            metric = item["metric"]
            resource = metric["resource"]
            metric_type = metric["type"]
            value = item["value"][1]
            if resource not in result:
                result[resource] = {}
            result[resource][metric_type] = int(value) if metric["unit"] == "bytes" else float(value)
    return result


@pytest.mark.polarion("CNV-12183")
def test_kube_application_aware_resourcequota_creation_timestamp(
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
    application_aware_resource_quota,
    vm_for_test_with_resource_limits,
    aaq_resource_hard_limit_and_used,
    values_from_kube_application_aware_resourcequota_metric,
):
    validate_kube_application_aware_resourcequota_metrics_value(
        actual_values=values_from_kube_application_aware_resourcequota_metric,
        expected_values=aaq_resource_hard_limit_and_used,
    )
