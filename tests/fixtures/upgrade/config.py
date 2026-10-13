import logging

import pytest

from utilities.operator import determine_upgrade_stream

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def cnv_upgrade_stream(admin_client, pytestconfig, cnv_current_version, cnv_target_version):
    """
    Verify if the upgrade can be performed by comparing the current and target versions.

    Args:
        admin_client: The admin client instance.
        pytestconfig: The pytest configuration object.
        cnv_current_version: The current CNV version.
        cnv_target_version: The target CNV version.
    """
    upgrade_stream = determine_upgrade_stream(
        current_version=cnv_current_version,
        target_version=cnv_target_version,
    )

    LOGGER.info(
        f"CNV upgrade:\n"
        f"Current version: {cnv_current_version},\n"
        f"Target version: {cnv_target_version},\n"
        f"Upgrade stream: {upgrade_stream},\n"
    )
    return upgrade_stream


@pytest.fixture(scope="session")
def upgrade_skip_default_sc_setup(pytestconfig):
    return pytestconfig.option.upgrade_skip_default_sc_setup
