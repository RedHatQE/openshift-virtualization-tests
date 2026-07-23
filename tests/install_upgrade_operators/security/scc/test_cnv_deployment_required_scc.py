"""
Test to verify all HCO deployments have 'openshift.io/required-scc' annotation.
"""

import pytest

from utilities.constants.components import HPP_POOL

REQUIRED_SCC_ANNOTATION = "openshift.io/required-scc"
REQUIRED_SCC_VALUE = "restricted-v2"

pytestmark = [pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


@pytest.fixture(scope="module")
def required_scc_deployment_check(discovered_cnv_deployments):
    missing_required_scc_annotation = []
    incorrect_required_scc_annotation_value = {}

    for deployment in discovered_cnv_deployments:
        if deployment.name.startswith(HPP_POOL):
            continue
        scc = deployment.instance.spec.template.metadata.annotations.get(REQUIRED_SCC_ANNOTATION)

        if scc is None:
            missing_required_scc_annotation.append(deployment.name)
        elif scc != REQUIRED_SCC_VALUE:
            incorrect_required_scc_annotation_value[deployment.name] = scc

    return {
        "missing_required_scc_annotation": missing_required_scc_annotation,
        "incorrect_required_scc_annotation_value": incorrect_required_scc_annotation_value,
    }


@pytest.mark.polarion("CNV-11964")
def test_deployments_missing_required_scc_annotation(required_scc_deployment_check):
    assert not required_scc_deployment_check["missing_required_scc_annotation"], (
        f"Deployments missing {REQUIRED_SCC_ANNOTATION} annotation: "
        f"{required_scc_deployment_check['missing_required_scc_annotation']}"
    )


@pytest.mark.polarion("CNV-11965")
def test_deployments_with_incorrect_required_scc(required_scc_deployment_check):
    assert not required_scc_deployment_check["incorrect_required_scc_annotation_value"], (
        f"Deployments incorrect {REQUIRED_SCC_ANNOTATION} annotation : "
        f"{required_scc_deployment_check['incorrect_required_scc_annotation_value']}"
    )
