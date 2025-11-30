from kubernetes.dynamic import DynamicClient
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import Resource
from ocp_resources.volume_snapshot import VolumeSnapshot

from utilities.storage import get_data_sources_managed_by_data_import_cron, get_default_storage_class


def get_boot_sources_expected_type() -> VolumeSnapshot | DataVolume:
    return (
        VolumeSnapshot
        if get_default_storage_class().storage_profile.data_import_cron_source_format == "snapshot"
        else DataVolume
    )


def get_arch_annotated_resources_dict(
    admin_client: DynamicClient,
    golden_images_namespace: str,
    worker_nodes_architectures: set[str],
) -> dict[str, set[Resource]]:
    arch_annotated_resources_dict = {
        DataImportCron.kind: set(list(DataImportCron.get(dyn_client=admin_client, namespace=golden_images_namespace))),
        DataSource.kind: set(
            get_data_sources_managed_by_data_import_cron(admin_client=admin_client, namespace=golden_images_namespace)
        ),
    }
    # Add DataVolume/VolumeSnapshot based on the default storage class
    expected_boot_source_type = get_boot_sources_expected_type()
    arch_annotated_resources_dict[expected_boot_source_type.kind] = {
        resource
        for resource in expected_boot_source_type.get(dyn_client=admin_client, namespace=golden_images_namespace)
        if set(resource.name.split("-")) & worker_nodes_architectures
    }
    return arch_annotated_resources_dict


def assert_sets_equal(actual: set, expected: set, context: str = "") -> None:
    """Assert that two sets are equal, with detailed error message on failure."""
    assert actual == expected, (
        f"{context + ': ' if context else ''}\n"
        f"Expected: {expected}\n"
        f"Actual: {actual}\n"
        f"Missing: {expected - actual}\n"
        f"Extra: {actual - expected}"
    )
