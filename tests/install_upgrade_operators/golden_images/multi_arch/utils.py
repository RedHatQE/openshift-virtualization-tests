from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from ocp_resources.volume_snapshot import VolumeSnapshot

from utilities.storage import get_default_storage_class


def get_boot_sources_expected_type(client: DynamicClient) -> VolumeSnapshot | DataVolume:
    return (
        VolumeSnapshot
        if get_default_storage_class(client=client).storage_profile.data_import_cron_source_format == "snapshot"
        else DataVolume
    )


def assert_sets_equal(actual: set, expected: set) -> None:
    """Assert that two sets are equal, with detailed error message on failure.

    Args:
        actual: Actual set.
        expected: Expected set..
    """
    assert actual == expected, (
        f"Expected: {expected}\nActual: {actual}\nMissing: {expected - actual}\nExtra: {actual - expected}"
    )
