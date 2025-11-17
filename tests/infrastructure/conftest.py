import logging
from pathlib import Path

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError

from tests.infrastructure.utils import (
    verify_numa_enabled,
    verify_tekton_operator_installed,
)
from tests.utils import verify_cpumanager_workers, verify_hugepages_1gi, verify_rwx_default_storage
from utilities.exceptions import ResourceMissingFieldError, ResourceValueError
from utilities.pytest_utils import exit_pytest_execution

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def hugepages_gib_max(hugepages_gib_values):
    """Return the maximum 1Gi hugepage size, capped at 64Gi."""
    if not hugepages_gib_values:
        raise ResourceValueError("Cluster does not report any 1Gi hugepages")
    return min(max(hugepages_gib_values), 64)


@pytest.fixture(scope="session", autouse=True)
def infrastructure_special_infra_sanity(
    request,
    admin_client,
    junitxml_plugin,
    schedulable_nodes,
    hugepages_gib_values,
):
    """
    Validates infrastructure requirements based on test markers.
    """
    skip_infra_sanity_check = "--skip-infra-sanity-check"

    if request.session.config.getoption(skip_infra_sanity_check):
        LOGGER.warning(f"Skipping infrastructure special infra sanity because {skip_infra_sanity_check} was passed")
        return

    verifications = {
        "cpu_manager": lambda: verify_cpumanager_workers(schedulable_nodes=schedulable_nodes),
        "hugepages": lambda: verify_hugepages_1gi(hugepages_gib_values=hugepages_gib_values),
        "numa": lambda: verify_numa_enabled(client=admin_client),
        "rwx_default_storage": lambda: verify_rwx_default_storage(client=admin_client),
    }

    # Collect markers only from infrastructure tests to avoid running checks for other suites
    infra_root = Path(request.config.rootpath) / "tests" / "infrastructure"
    infrastructure_items = [
        item
        for item in request.session.items
        if infra_root in Path(str(item.fspath)).parents or Path(str(item.fspath)) == infra_root
    ]
    # collect markers from infrastructure directory
    collected_marker_names = {marker.name for item in infrastructure_items for marker in item.iter_markers()}
    LOGGER.info(f"Collected markers from {infra_root}: '{collected_marker_names}'")

    # Add tekton verification only if tier3 marker is present
    if "tier3" in collected_marker_names:
        verifications["tekton"] = lambda: verify_tekton_operator_installed(client=admin_client)

    # Run verifications for markers that are present
    failed_verifications = []
    for marker, verify_func in verifications.items():
        if marker in collected_marker_names:
            try:
                LOGGER.info(f"Running infrastructure sanity check for '{marker}'")
                verify_func()
            except (ResourceNotFoundError, ResourceMissingFieldError, ResourceValueError) as error:
                failed_verifications.append(str(error))

    # Handle failures if any
    if failed_verifications:
        err_msg = "\n".join(failed_verifications)
        LOGGER.error(f"Infrastructure cluster verification failed! Missing components:\n{err_msg}")
        exit_pytest_execution(
            message=err_msg,
            return_code=98,
            filename="infrastructure_special_infra_sanity_failure.txt",
            junitxml_property=junitxml_plugin,
        )
