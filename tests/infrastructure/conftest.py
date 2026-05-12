import logging
from pathlib import Path

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from timeout_sampler import TimeoutExpiredError

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
        LOGGER.info(f"Sanity checks skipped because {skip_infra_sanity_check} was provided")
        return

    # Collect markers from infrastructure tests
    infra_root = Path(request.config.rootpath) / "tests" / "infrastructure"
    collected_marker_names = set()

    for item in request.session.items:
        if item.path.is_relative_to(infra_root):
            collected_marker_names.update(marker.name for marker in item.iter_markers())
    LOGGER.info(f"Collected markers from infrastructure tests: '{collected_marker_names}'")

    # Collect all verification failures to report them together
    failed_verifications = []

    for marker in collected_marker_names:
        try:
            match marker:
                case "cpu_manager":
                    LOGGER.info("Running infrastructure sanity check for 'cpu_manager'")
                    verify_cpumanager_workers(schedulable_nodes=schedulable_nodes)

                case "hugepages":
                    LOGGER.info("Running infrastructure sanity check for 'hugepages'")
                    verify_hugepages_1gi(hugepages_gib_values=hugepages_gib_values)

                case "numa":
                    LOGGER.info("Running infrastructure sanity check for 'numa'")
                    verify_numa_enabled(client=admin_client)

                case "rwx_default_storage":
                    LOGGER.info("Running infrastructure sanity check for 'rwx_default_storage'")
                    verify_rwx_default_storage(client=admin_client)

                case "tekton":
                    LOGGER.info("Running infrastructure sanity check for 'tekton'")
                    verify_tekton_operator_installed(client=admin_client)

        except (ResourceNotFoundError, ResourceMissingFieldError, ResourceValueError, TimeoutExpiredError) as error:
            failed_verifications.append((marker, str(error)))

    if failed_verifications:
        lines = [
            "Infrastructure cluster verification failed.",
            "The following requirements are not satisfied:",
        ]
        for marker, message in failed_verifications:
            lines.append(f"  - [{marker}] {message}")
        err_msg = "\n".join(lines)
        LOGGER.error(err_msg)
        exit_pytest_execution(
            log_message=err_msg,
            message="Infrastructure special_infra cluster verification failed",
            return_code=97,
            filename="infrastructure_special_infra_sanity_failure.txt",
            junitxml_property=junitxml_plugin,
            admin_client=admin_client,
        )
