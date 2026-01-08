import pytest
from ocp_resources.cdi import CDI
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.ssp import SSP
from ocp_resources.volume_snapshot import VolumeSnapshot

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
    golden_images_namespace,
    worker_nodes_architectures,
    hyperconverged_resource_scope_class,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {"spec": {FEATURE_GATES: {"enableMultiArchBootImageImport": True}}}
        },
        list_resource_reconcile=[SSP, CDI, KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield

    # Cleanup: Delete arch annotated leftovers
    for resource_type in [DataVolume, VolumeSnapshot, DataSource]:
        for resource in resource_type.get(client=admin_client, namespace=golden_images_namespace.name):
            if bool(set(resource.name.split("-")) & worker_nodes_architectures):
                resource.delete(wait=True)
    assert verify_boot_sources_reimported(
        admin_client=admin_client, namespace=golden_images_namespace.name, consecutive_checks_count=1
    ), "Failed to reimport boot sources"
