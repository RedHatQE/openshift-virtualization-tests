import logging
import os

import pytest

from utilities.artifactory import get_http_image_url
from utilities.constants import Images
from utilities.exceptions import MissingEnvironmentVariableError

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def artifactory_setup(pytestconfig):
    LOGGER.info("Checking for artifactory credentials:")
    if pytestconfig.option.skip_artifactory_check:
        LOGGER.warning("Explicitly skipping artifactory setup check due to use of --skip-artifactory-check")
        return
    if not (os.environ.get("ARTIFACTORY_TOKEN") and os.environ.get("ARTIFACTORY_USER")):
        raise MissingEnvironmentVariableError("Please set ARTIFACTORY_USER and ARTIFACTORY_TOKEN environment variables")


@pytest.fixture(scope="session")
def rhel9_http_image_url():
    return get_http_image_url(image_directory=Images.Rhel.DIR, image_name=Images.Rhel.RHEL9_4_IMG)
