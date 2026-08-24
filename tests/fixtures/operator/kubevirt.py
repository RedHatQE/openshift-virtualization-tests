import pytest

from utilities.constants.hco import FEATURE_GATES
from utilities.virt import get_hyperconverged_kubevirt, get_kubevirt_hyperconverged_spec


@pytest.fixture()
def kubevirt_hyperconverged_spec_scope_function(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_kubevirt_hyperconverged_spec(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="module")
def kubevirt_hyperconverged_spec_scope_module(admin_client, hco_namespace):
    return get_kubevirt_hyperconverged_spec(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def kubevirt_config(kubevirt_hyperconverged_spec_scope_function):
    return kubevirt_hyperconverged_spec_scope_function["configuration"]


@pytest.fixture(scope="module")
def kubevirt_config_scope_module(kubevirt_hyperconverged_spec_scope_module):
    return kubevirt_hyperconverged_spec_scope_module["configuration"]


@pytest.fixture()
def kubevirt_feature_gates(kubevirt_config):
    return kubevirt_config["developerConfiguration"][FEATURE_GATES]


@pytest.fixture(scope="module")
def kubevirt_feature_gates_scope_module(kubevirt_config_scope_module):
    return kubevirt_config_scope_module["developerConfiguration"][FEATURE_GATES]


@pytest.fixture(scope="session")
def kubevirt_resource_scope_session(admin_client, installing_cnv, hco_namespace):
    if not installing_cnv:
        return get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="module")
def machine_type_from_kubevirt_config(kubevirt_config_scope_module, nodes_cpu_architecture):
    """Extract machine type default from kubevirt CR."""
    return kubevirt_config_scope_module["architectureConfiguration"][nodes_cpu_architecture]["machineType"]


@pytest.fixture(scope="module")
def smbios_from_kubevirt_config(kubevirt_config_scope_module):
    """Extract SMBIOS default from kubevirt CR."""
    return kubevirt_config_scope_module["smbios"]
