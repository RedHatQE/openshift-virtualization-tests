import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.image_stream import ImageStream
from ocp_resources.resource import Resource
from ocp_resources.ssp import SSP
from ocp_resources.volume_snapshot import VolumeSnapshot
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import (
    COMMON_TEMPLATE,
    get_templates_by_type_from_hco_status,
)
from tests.install_upgrade_operators.utils import is_rhel10_beta_resource_and_63351_bug_open
from utilities.constants import (
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_10MIN,
    TIMEOUT_30SEC,
)
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    wait_for_hco_conditions,
)
from utilities.infra import create_ns, delete_resources_from_namespace_by_type
from utilities.storage import get_data_sources_managed_by_data_import_cron

LOGGER = logging.getLogger(__name__)
COMMON_BOOT_IMAGE_NAMESPACE_STR = "commonBootImageNamespace"

pytestmark = [pytest.mark.arm64]


def get_templates_resources_names_dict(templates):
    resource_dict = {}
    for template in templates:
        image_stream_name = template["spec"]["template"]["spec"]["source"]["registry"].get("imageStream")
        if image_stream_name:
            resource_dict.setdefault(ImageStream.kind, set()).add(image_stream_name)
        resource_dict.setdefault(DataImportCron.kind, set()).add(template["metadata"]["name"])
        resource_dict.setdefault(DataSource.kind, set()).add(template["spec"]["managedDataSource"])
    return resource_dict


def verify_resource_not_in_ns(resource_type, namespace, dyn_client):
    resources = resource_type.get(dyn_client=dyn_client, namespace=namespace)
    # skipping rhel10-beta-guest image stream if jira is open
    resources_names = {
        resource.name
        for resource in resources
        if not is_rhel10_beta_resource_and_63351_bug_open(resource_name=resource.name)
    }
    assert not resources_names, f"{resource_type.kind} resources shouldn't exist in {namespace}: {resources_names}"


def verify_resource_in_ns(expected_resource_names, namespace, dyn_client, resource_type, ready_condition=None):
    """
    Verify that resources exist in expected_namespace and in ready status.
    """
    resources = resource_type.get(dyn_client=dyn_client, namespace=namespace)
    resources_names = {resource.name for resource in resources}
    missing_resources_names = expected_resource_names - resources_names
    assert not missing_resources_names, f"Missing {resource_type.kind} in {namespace}: {missing_resources_names}"

    if ready_condition:
        LOGGER.info(f"Verify that {expected_resource_names} are in {ready_condition} condition")
        for resource in resources:
            resource.wait_for_condition(
                condition=ready_condition,
                status=resource.Condition.Status.TRUE,
                timeout=TIMEOUT_10MIN,
            )


def wait_for_any_resource_exists_in_namespace(client, namespace, resource_types):
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_30SEC,
        func=lambda: any(
            list(resource_type.get(dyn_client=client, namespace=namespace)) for resource_type in resource_types
        ),
    ):
        if sample:
            return


def verify_resources_not_reconciled(resources_to_verify, namespace, client):
    delete_resources_from_namespace_by_type(resources_types=resources_to_verify, namespace=namespace, wait=True)
    with pytest.raises(TimeoutExpiredError):
        wait_for_any_resource_exists_in_namespace(
            client=client, namespace=namespace, resource_types=resources_to_verify
        )
        LOGGER.error(f"resources shouldn't reconcile in {namespace} namespace")


def verify_common_template_namespace_updated(common_templates, namespace_name):
    non_updated_templates = []
    for template in common_templates:
        if template["metadata"].get("namespace") != namespace_name:
            non_updated_templates.append(
                f"{template['metadata']['name']} expected namespace: {namespace_name} "
                f"actual: {template['metadata'].get('namespace')}\n"
            )
    assert not non_updated_templates, non_updated_templates


@pytest.fixture(scope="module")
def custom_golden_images_namespace():
    yield from create_ns(name="custom-golden-images-namespace")


@pytest.fixture(scope="class")
def default_common_template_hco_status(hyperconverged_status_templates_scope_class):
    return get_templates_by_type_from_hco_status(
        hco_status_templates=hyperconverged_status_templates_scope_class, template_type=COMMON_TEMPLATE
    )


@pytest.fixture(scope="class")
def default_common_templates_related_resources(default_common_template_hco_status):
    return get_templates_resources_names_dict(templates=default_common_template_hco_status)


@pytest.fixture(scope="class")
def updated_common_template_custom_ns(
    golden_images_namespace,
    hyperconverged_resource_scope_class,
    custom_golden_images_namespace,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {COMMON_BOOT_IMAGE_NAMESPACE_STR: custom_golden_images_namespace.name}
            }
        },
        list_resource_reconcile=[SSP, CDI],
        wait_for_reconcile_post_update=True,
    ):
        yield
    for data_source in get_data_sources_managed_by_data_import_cron(namespace=golden_images_namespace.name):
        if not is_rhel10_beta_resource_and_63351_bug_open(resource_name=data_source.name):
            data_source.wait_for_condition(
                condition=DataSource.Condition.READY,
                status=DataSource.Condition.Status.TRUE,
                timeout=TIMEOUT_10MIN,
            )


@pytest.fixture()
def updated_common_templates_non_existent_ns(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: {"spec": {COMMON_BOOT_IMAGE_NAMESPACE_STR: "non-existent-ns"}}}
    ):
        yield
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        wait_timeout=TIMEOUT_3MIN,
        list_dependent_crs_to_check=[SSP, CDI],
    )


@pytest.mark.gating
@pytest.mark.usefixtures("updated_common_template_custom_ns")
class TestDefaultCommonTemplates:
    @pytest.mark.parametrize(
        "common_templates",
        [
            pytest.param("default_common_template_hco_status", marks=pytest.mark.polarion("CNV-11473")),
            pytest.param("ssp_spec_templates_scope_function", marks=pytest.mark.polarion("CNV-11677")),
        ],
    )
    @pytest.mark.s390x
    def test_custom_namespace_added_to_templates_metadata(
        self,
        request,
        custom_golden_images_namespace,
        common_templates,
    ):
        verify_common_template_namespace_updated(
            common_templates=request.getfixturevalue(common_templates),
            namespace_name=custom_golden_images_namespace.name,
        )

    @pytest.mark.parametrize(
        "resource_type, ready_condition",
        [
            pytest.param(ImageStream, None, marks=pytest.mark.polarion("CNV-11474")),
            pytest.param(DataImportCron, "UpToDate", marks=pytest.mark.polarion("CNV-11475")),
            pytest.param(DataSource, DataSource.Condition.READY, marks=pytest.mark.polarion("CNV-11476")),
        ],
    )
    @pytest.mark.s390x
    def test_resources_in_custom_ns(
        self,
        admin_client,
        custom_golden_images_namespace,
        golden_images_namespace,
        default_common_templates_related_resources,
        resource_type,
        ready_condition,
    ):
        verify_resource_in_ns(
            expected_resource_names=default_common_templates_related_resources[resource_type.kind],
            namespace=custom_golden_images_namespace.name,
            dyn_client=admin_client,
            resource_type=resource_type,
            ready_condition=ready_condition,
        )
        if resource_type != DataSource:
            verify_resource_not_in_ns(
                resource_type=resource_type,
                namespace=golden_images_namespace.name,
                dyn_client=admin_client,
            )

    @pytest.mark.polarion("CNV-11477")
    @pytest.mark.s390x
    def test_boot_sources_not_reconciled_in_default_namespace(self, admin_client, golden_images_namespace):
        verify_resources_not_reconciled(
            resources_to_verify=[DataVolume, VolumeSnapshot],
            namespace=golden_images_namespace.name,
            client=admin_client,
        )


@pytest.mark.polarion("CNV-11631")
@pytest.mark.s390x
def test_non_existent_namespace(
    admin_client,
    hco_namespace,
    updated_common_templates_non_existent_ns,
):
    """
    Verify that HCO is degraded if we set non-existent namespace
    """
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        expected_conditions={
            Resource.Condition.AVAILABLE: Resource.Condition.Status.FALSE,
            Resource.Condition.DEGRADED: Resource.Condition.Status.TRUE,
        },
        wait_timeout=TIMEOUT_3MIN,
    )
