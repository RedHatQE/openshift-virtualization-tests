import logging

import pytest
from ocp_resources.secret import Secret

from utilities.bitwarden import get_cnv_tests_secret_by_name
from utilities.constants.cluster import RHSM_SECRET_NAME
from utilities.data_utils import base64_encode_str

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def rhsm_credentials_from_bitwarden():
    return get_cnv_tests_secret_by_name(secret_name="RHSM_CREDENTIALS")


@pytest.fixture(scope="module")
def rhsm_created_secret(rhsm_credentials_from_bitwarden, namespace):
    with Secret(
        name=RHSM_SECRET_NAME,
        namespace=namespace.name,
        data_dict={
            "username": base64_encode_str(text=rhsm_credentials_from_bitwarden["user"]),
            "password": base64_encode_str(text=rhsm_credentials_from_bitwarden["password"]),
        },
    ) as secret:
        yield secret
