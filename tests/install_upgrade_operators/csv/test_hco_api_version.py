import pytest
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.resource import Resource

pytestmark = [pytest.mark.sno, pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


@pytest.mark.polarion("CNV-5832")
def test_hyperconverged_cr_api_version(hyperconverged_resource_scope_function):
    """
    This test will check the Hyperconverged CR's api_version for v1
    """
    expected_api_version = f"{HyperConverged.ApiGroup.HCO_KUBEVIRT_IO}/{Resource.ApiVersion.V1}"
    assert hyperconverged_resource_scope_function.instance.apiVersion == expected_api_version, (
        f"Expected HyperConverged apiVersion {expected_api_version}, "
        f"got {hyperconverged_resource_scope_function.instance.apiVersion}"
    )
