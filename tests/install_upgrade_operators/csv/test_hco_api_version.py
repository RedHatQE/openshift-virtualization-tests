import pytest
from ocp_resources.resource import Resource

pytestmark = pytest.mark.sno


@pytest.mark.polarion("CNV-5832")
@pytest.mark.s390x
def test_hyperconverged_cr_api_version(hyperconverged_resource_scope_function):
    """
    This test will check the Hyperconverged CR's api_version for v1beta1
    """
    assert Resource.ApiVersion.V1BETA1 in hyperconverged_resource_scope_function.instance.apiVersion
