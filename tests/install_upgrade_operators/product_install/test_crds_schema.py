# -*- coding: utf-8 -*-
import pytest
from ocp_resources.custom_resource_definition import CustomResourceDefinition


@pytest.fixture(scope="module")
def crd_operator_resources(request, admin_client):
    """
    Returns list of CustomResourceDefinitions Resources.

    Args:
        request (fixture): Info from request.param
        admin_client:  DynamicClient

    Returns:
        list: A list of CRD resources based on the info from request param.
    """
    return list(CustomResourceDefinition.get(dyn_client=admin_client, group=request.param))


@pytest.mark.parametrize(
    "crd_operator_resources",
    [
        pytest.param(
            "kubevirt.io",
            marks=(pytest.mark.polarion("CNV-4695")),
        ),
        pytest.param(
            "networkaddonsoperator.network.kubevirt.io",
            marks=(pytest.mark.polarion("CNV-6522")),
        ),
        pytest.param(
            "nmstate.io",
            marks=(pytest.mark.polarion("CNV-6523")),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_check_crd_non_structural_schema(crd_operator_resources):
    failed_crds = [
        crd_resource.name
        for crd_resource in crd_operator_resources
        if any(
            resource_condition["NonStructuralSchema"] for resource_condition in crd_resource.instance.status.conditions
        )
    ]

    assert not failed_crds, f"CRDs with Non Structural Schema {failed_crds}"
