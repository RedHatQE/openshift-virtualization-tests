import pytest
from timeout_sampler import TimeoutSampler

from tests.observability.metrics.utils import (
    timestamp_to_seconds,
    validate_metrics_value,
)
from utilities.constants import (
    TIMEOUT_4MIN,
    TIMEOUT_15SEC,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
)

pytestmark = [
    pytest.mark.usefixtures(
        "enabled_aaq_in_hco_scope_package",
        "updated_namespace_with_aaq_label",
    ),
]


def parse_value(val):
    if isinstance(val, str):
        val = val.strip().lower()
        if val.endswith("gi"):
            return int(float(val.replace("gi", "")) * 1024**3)
        return int(val)
    return val


def get_kube_application_aware_resourcequota_metrics_value(prometheus, metrics_name):
    return prometheus.query(query=metrics_name).get("data", {}).get("result", [])


def validate_kube_application_aware_resourcequota_metrics_value(actual_values, expected_value):
    resource_hard_limit = expected_value[0]
    resource_used = expected_value[1]
    for resource in actual_values:
        expected_hard_limit = parse_value(val=resource_hard_limit.get(resource))
        expected_used = parse_value(val=resource_used.get(resource))

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


@pytest.fixture(scope="class")
def vm_for_aaq_metrics_test(namespace):
    vm_name = "vm-aaq-test"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        cpu_limits=1,
        memory_limits="1Gi",
        body=fedora_vm_body(name=vm_name),
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def aaq_resource_hard_limit_and_used(application_aware_resource_quota):
    resource_hard_limit = application_aware_resource_quota.instance.spec.hard
    resource_used = application_aware_resource_quota.instance.status.used
    return resource_hard_limit, resource_used


@pytest.fixture
def values_from_kube_application_aware_resourcequota_metric(prometheus):
    """
    Fixture to fetch and parse kube_application_aware_resourcequota metrics.
    """
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_4MIN,
        sleep=TIMEOUT_15SEC,
        func=get_kube_application_aware_resourcequota_metrics_value,
        prometheus=prometheus,
        metrics_name="kube_application_aware_resourcequota",
    )

    metric_values = None
    for sample in samples:
        if sample and any(item.get("value") is not None for item in sample):
            metric_values = sample
            break

    if not metric_values:
        raise TimeoutError("Timed out waiting for metric: kube_application_aware_resourcequota")

    result = {}
    for item in metric_values:
        metric = item["metric"]
        resource = metric["resource"]
        typ = metric["type"]
        value = item["value"][1]
        if metric["unit"] == "bytes":
            value = int(value)
        elif metric["unit"] in ("core", "count"):
            value = float(value) if "." in value else int(value)

        if resource not in result:
            result[resource] = {}
        result[resource][typ] = value

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
def test_kube_application_aware_resourcequota(
    prometheus,
    vm_for_aaq_metrics_test,
    aaq_resource_hard_limit_and_used,
    values_from_kube_application_aware_resourcequota_metric,
):
    validate_kube_application_aware_resourcequota_metrics_value(
        actual_values=values_from_kube_application_aware_resourcequota_metric,
        expected_value=aaq_resource_hard_limit_and_used,
    )
