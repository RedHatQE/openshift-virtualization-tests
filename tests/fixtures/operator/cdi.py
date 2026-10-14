import pytest
from ocp_resources.cdi import CDI
from ocp_resources.cdi_config import CDIConfig

from utilities.constants.components import CDI_KUBEVIRT_HYPERCONVERGED


@pytest.fixture(scope="session")
def cdi(admin_client, hco_namespace):
    cdi = CDI(name=CDI_KUBEVIRT_HYPERCONVERGED, client=admin_client)
    assert cdi.instance is not None
    yield cdi


@pytest.fixture(scope="session")
def cdi_config(admin_client):
    cdi_config = CDIConfig(name="config", client=admin_client)
    assert cdi_config.instance is not None
    return cdi_config


@pytest.fixture()
def cdi_spec(cdi):
    return cdi.instance.to_dict()["spec"]
