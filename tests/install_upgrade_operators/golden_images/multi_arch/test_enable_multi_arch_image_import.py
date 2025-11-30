import logging

import pytest
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource

from tests.install_upgrade_operators.golden_images.multi_arch.utils import (
    get_boot_sources_expected_type,
)
from tests.install_upgrade_operators.golden_images.utils import (
    verify_data_import_cron_template_annotation,
    verify_resource_in_ns,
)
from utilities.storage import get_data_sources_managed_by_data_import_cron

LOGGER = logging.getLogger(__name__)

pytestmark = [pytest.mark.gating, pytest.mark.arm64, pytest.mark.s390x]


@pytest.fixture(scope="session")
def kubevirt_default_architecture_configuration(kubevirt_resource_scope_session):
    return kubevirt_resource_scope_session.instance.status.defaultArchitecture


@pytest.fixture(scope="class")
def arch_annotated_resources_dict(admin_client, golden_images_namespace, worker_nodes_architectures):
    arch_annotated_resources_dict = {
        DataImportCron.kind: set(list(DataImportCron.get(client=admin_client, namespace=golden_images_namespace))),
        DataSource.kind: set(
            get_data_sources_managed_by_data_import_cron(admin_client=admin_client, namespace=golden_images_namespace)
        ),
    }
    # Add DataVolume/VolumeSnapshot based on the default storage class
    expected_boot_source_type = get_boot_sources_expected_type(client=admin_client)
    arch_annotated_resources_dict[expected_boot_source_type.kind] = {
        resource
        for resource in expected_boot_source_type.get(client=admin_client, namespace=golden_images_namespace)
        if set(resource.name.split("-")) & worker_nodes_architectures
    }
    return arch_annotated_resources_dict


@pytest.fixture(scope="class")
def expected_resources_with_arch_suffix(
    default_common_templates_related_resources,
    worker_nodes_architectures,
):
    resources_dict = {
        kind: {f"{name}-{arch}" for name in names for arch in worker_nodes_architectures}
        for kind, names in default_common_templates_related_resources.items()
        if kind in (DataImportCron.kind, DataSource.kind)
    }
    return resources_dict


@pytest.mark.usefixtures(
    "default_datasources_managed_by_data_import_cron",
    "enabled_multi_arch_image_import_feature_gate",
)
class TestEnableMultiArchImageImport:
    @pytest.mark.parametrize(
        "common_templates",
        [
            pytest.param("hyperconverged_status_templates_scope_function", marks=pytest.mark.polarion("CNV-12464")),
            pytest.param("ssp_spec_templates_scope_function", marks=pytest.mark.polarion("CNV-12465")),
        ],
    )
    def test_data_import_crons_template_arch_annotation(
        self,
        request,
        worker_nodes_architectures,
        common_templates,
        subtests,
    ):
        for template in request.getfixturevalue(common_templates):
            with subtests.test(
                msg=f"{template['metadata']['name']} dataImportCronTemplate annotated"
                f"with architectures: {worker_nodes_architectures}"
            ):
                verify_data_import_cron_template_annotation(
                    template=template, expected_architectures=worker_nodes_architectures
                )

    @pytest.mark.polarion("CNV-12466")
    def test_arch_annotated_resources(
        self,
        admin_client,
        golden_images_namespace,
        expected_resources_with_arch_suffix,
        arch_annotated_resources_dict,
        subtests,
    ):
        for resource_type in [DataImportCron, DataSource]:
            resource_kind = resource_type.kind
            ready_condition = (
                DataImportCron.Condition.UP_TO_DATE
                if resource_kind == DataImportCron.kind
                else DataSource.Condition.READY
            )
            with subtests.test(msg=f"{resource_kind} resources have arch label"):
                verify_resource_in_ns(
                    expected_resource_names=expected_resources_with_arch_suffix[resource_kind],
                    namespace=golden_images_namespace.name,
                    client=admin_client,
                    resource_type=resource_type,
                    ready_condition=ready_condition,
                    resource_list=arch_annotated_resources_dict[resource_kind],
                )

    @pytest.mark.polarion("CNV-12467")
    def test_resources_have_arch_label(
        self,
        worker_nodes_architectures,
        arch_annotated_resources_dict,
        subtests,
    ):
        for resource_type, resources in arch_annotated_resources_dict.items():
            for resource in resources:
                with subtests.test(msg=f"{resource.name} {resource_type} resource has arch label"):
                    assert resource.labels.get("template.kubevirt.io/architecture") in worker_nodes_architectures, (
                        f"Resource {resource.name} should have arch label"
                    )

    @pytest.mark.polarion("CNV-12468")
    def test_old_data_sources_point_to_arch_annotated_datasource(
        self,
        default_datasources_managed_by_data_import_cron,
        kubevirt_default_architecture_configuration,
        subtests,
    ):
        for data_source in default_datasources_managed_by_data_import_cron:
            with subtests.test(msg=f"{data_source.name} data source points to arch annotated datasource"):
                das_source_name = data_source.instance.spec.source.dataSource.name
                assert das_source_name == f"{data_source.name}-{kubevirt_default_architecture_configuration}", (
                    f"Data source {data_source.name} should point to arch annotated datasource."
                    f"Actual name: {das_source_name}"
                )
                data_source.wait_for_condition(
                    condition=data_source.Condition.READY,
                    status=data_source.Condition.Status.TRUE,
                )
