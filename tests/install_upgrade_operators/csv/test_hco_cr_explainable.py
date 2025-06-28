import shlex

import pytest
from pyhelper_utils.shell import run_command

pytestmark = [pytest.mark.sno, pytest.mark.arm64]


@pytest.mark.polarion("CNV-5884")
@pytest.mark.s390x
def test_hco_cr_explainable(hyperconverged_resource_scope_function):
    """
    This test case ensure that after executing 'oc explain hyperconvergeds'
    return meaningful information about the HCO CR.
    """
    command_output = run_command(command=shlex.split("oc explain hyperconvergeds"), check=False)[1]
    assert "HyperConverged is the Schema for the hyperconvergeds API" in command_output


@pytest.mark.parametrize(
    "fields, description",
    [
        pytest.param(
            "apiVersion",
            "APIVersion defines the versioned schema of this representation of an",
            marks=pytest.mark.polarion("CNV-5886"),
            id="test_hco_cr_explain_apiversion",
        ),
        pytest.param(
            "kind",
            "Kind is a string value representing the REST resource this object",
            marks=pytest.mark.polarion("CNV-5887"),
            id="test_hco_cr_explain_kind",
        ),
        pytest.param(
            "metadata",
            "Standard object's metadata. More info",
            marks=pytest.mark.polarion("CNV-5888"),
            id="test_hco_cr_explain_metadata",
        ),
        pytest.param(
            "spec",
            "HyperConvergedSpec defines the desired state of HyperConverged",
            marks=pytest.mark.polarion("CNV-5889"),
            id="test_hco_cr_explain_spec",
        ),
        pytest.param(
            "status",
            "HyperConvergedStatus defines the observed state of HyperConverged",
            marks=pytest.mark.polarion("CNV-5890"),
            id="test_hco_cr_explain_status",
        ),
    ],
)
@pytest.mark.s390x
def test_hco_cr_fields_explainable(fields, description):
    """
    This test case ensure that after executing 'oc explain hyperconvergeds.{fields}'
    return meaningful information about specific fields of the HCO CR.
    """
    command_output = run_command(command=shlex.split(f"oc explain hyperconvergeds.{fields}"), check=False)[1]
    assert description in command_output
