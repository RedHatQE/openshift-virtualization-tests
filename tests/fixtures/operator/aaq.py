import pytest
from ocp_resources.application_aware_resource_quota import ApplicationAwareResourceQuota

from utilities.constants.aaq import AAQ_NAMESPACE_LABEL, ARQ_QUOTA_HARD_SPEC
from utilities.infra import label_project


@pytest.fixture(scope="module")
def updated_namespace_with_aaq_label(admin_client, namespace):
    label_project(name=namespace.name, label=AAQ_NAMESPACE_LABEL, admin_client=admin_client)


@pytest.fixture(scope="class")
def application_aware_resource_quota(admin_client, namespace):
    with ApplicationAwareResourceQuota(
        client=admin_client,
        name="application-aware-resource-quota-for-aaq-test",
        namespace=namespace.name,
        hard=ARQ_QUOTA_HARD_SPEC,
    ) as arq:
        yield arq
