import logging

import pytest

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def smbios_from_kubevirt_config(kubevirt_config_scope_module):
    """Extract SMBIOS default from kubevirt CR."""
    return kubevirt_config_scope_module["smbios"]
