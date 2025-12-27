import pytest
from ocp_resources.cdi import CDI
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.ssp import SSP

from tests.install_upgrade_operators.golden_images.multi_arch.utils import get_arch_annotated_resources_dict
from tests.install_upgrade_operators.golden_images.utils import verify_resource_in_ns
from utilities.constants import FEATURE_GATES
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import get_data_sources_managed_by_data_import_cron, verify_boot_sources_reimported


@pytest.fixture(scope="session")
def default_datasources_managed_by_data_import_cron(admin_client, golden_images_namespace):
    return get_data_sources_managed_by_data_import_cron(
        admin_client=admin_client, namespace=golden_images_namespace.name
    )


@pytest.fixture(scope="class")
def enabled_multi_arch_image_import_feature_gate(
    admin_client,
    default_common_templates_related_resources,
    golden_images_namespace,
    hyperconverged_resource_scope_class,
    worker_nodes_architectures,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {"spec": {FEATURE_GATES: {"enableMultiArchBootImageImport": True}}}
        },
        list_resource_reconcile=[SSP, CDI, KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        arch_annotated_resources_dict = get_arch_annotated_resources_dict(
            admin_client=admin_client,
            golden_images_namespace=golden_images_namespace.name,
            worker_nodes_architectures=worker_nodes_architectures,
        )
        yield

    # Cleanup: Wait for non-arch DataImportCrons to be recreated
    verify_resource_in_ns(
        expected_resource_names=default_common_templates_related_resources.get(DataImportCron.kind),
        namespace=golden_images_namespace.name,
        dyn_client=admin_client,
        resource_type=DataImportCron,
    )
    # delete arch annotated leftovers
    for resource_type, resources in arch_annotated_resources_dict.items():
        if resource_type != DataImportCron.kind:
            for resource in resources:
                resource.delete(wait=True)
    assert verify_boot_sources_reimported(
        admin_client=admin_client, namespace=golden_images_namespace.name, consecutive_checks_count=1
    ), "Failed to reimport boot sources"
